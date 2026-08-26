"""Структурированные уроки (Фаза 1): команда /lesson, навигация по шагам.

Состояние урока хранится в БД (lesson_sessions), поэтому переживает рестарты.
Пользователь идёт по шагам: intro -> vocabulary -> slides -> grammar -> tasks -> recap.
Текст/голос во время урока обрабатываются как практика (см. handlers/text.py, voice.py).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from core.characters import character_prompt
from core.lesson_notes import LessonNoteService
from core.progress import ProgressService
from core.srs import SRSService
from core.lessons import (
    LESSON_STEPS,
    LessonService,
    lesson_content_from_json,
    lesson_content_to_json,
)
from core.profile import merge_weak_areas, to_profile_snippet
from storage.repo import LessonNote, Repository, TopicProposal

from .formatters import format_lesson_note, format_lesson_step
from .keyboards import lesson_keyboard, lesson_recap_keyboard, main_menu, topic_proposals_keyboard
from .utils import escape

router = Router()
logger = logging.getLogger(__name__)


class LessonNav(StatesGroup):
    processing = State()


def _finished_text(content, note: LessonNote | None = None) -> str:
    parts = [f"🎉 <b>Урок завершён!</b>\n\nТема: {escape(content.topic)}\n\n"]
    if note is not None:
        parts.append(format_lesson_note(note))
        parts.append("\n\n")
    parts.append("Загляни в /stats, чтобы увидеть свой прогресс. Хочешь новую тему? Жми /lesson!")
    return "".join(parts)


async def _create_lesson_note(
    user_id: int,
    session_id: int,
    content,
    repo: Repository,
    note_service: LessonNoteService,
) -> LessonNote | None:
    """Генерирует и сохраняет заметку урока. Ошибки не ломают завершение урока."""
    try:
        answers = await repo.get_lesson_messages(session_id)
        note = await note_service.generate(user_id, session_id, content, answers)
        await repo.add_lesson_note(note)
        logger.info("Заметка урока: user=%s lesson=%s answers=%s", user_id, session_id, len(answers))
        return note
    except Exception:
        logger.exception("Не удалось создать заметку урока user=%s lesson=%s", user_id, session_id)
        return None


async def _save_lesson_vocabulary(repo: Repository, user_id: int, content, session_id: int, srs=None) -> None:
    """Сохраняет слова урока в SRS (Фаза 13)."""
    if srs is None or not content.vocabulary:
        return
    try:
        words = [
            {"word": w.word, "translation": w.translation, "example": w.example}
            for w in content.vocabulary
        ]
        added = await srs.add_words(user_id, words, lesson_id=session_id)
        if added:
            logger.info("SRS: добавлено %d слов из урока user=%s", added, user_id)
    except Exception:
        logger.exception("Не удалось сохранить слова урока в SRS user=%s", user_id)


async def _merge_note_into_profile(repo: Repository, user_id: int, content, note: LessonNote | None) -> None:
    """Итоги урока попадают в слабые места профиля (Фаза 5 -> Фаза 4)."""
    if note is None:
        return
    try:
        profile = await repo.get_profile(user_id)
        if profile is None:
            return
        grammar_rule = content.grammar.rule if content.grammar else ""
        new_weak = await merge_weak_areas(profile, grammar_rule, note.mistakes, repo=repo)
        if new_weak != profile.weak_areas:
            profile.weak_areas = new_weak
            profile.updated_at = datetime.now(timezone.utc).isoformat()
            await repo.save_profile(profile)
            logger.info("Слабые места профиля обновлены: user=%s", user_id)
    except Exception:
        logger.exception("Не удалось обновить слабые места профиля user=%s", user_id)


def next_lesson_position(step: int, task_index: int, total_tasks: int) -> tuple[int, int, bool]:
    """Позиция после нажатия «Дальше»: (step, task_index, finished).

    Внутри шага "tasks" перебираем задания по одному; после последнего переходим
    к следующему шагу. С последнего шага (recap) урок считается завершённым.
    """
    step_name = LESSON_STEPS[step]
    if step_name == "tasks":
        if task_index + 1 < total_tasks:
            return step, task_index + 1, False
        step += 1
        return step, 0, step >= len(LESSON_STEPS)
    step += 1
    return step, 0, step >= len(LESSON_STEPS)


async def _start_lesson(target, repo: Repository, lesson_service: LessonService, topic: str | None, user_from) -> None:
    user = await repo.get_or_create_user(
        user_from.id,
        username=user_from.username,
        first_name=user_from.first_name,
    )
    if await repo.get_active_lesson(user.id):
        await target.answer(
            "📚 У тебя уже идёт урок! Продолжай: жми «➡️ Дальше» в последнем сообщении, "
            "или «⏹️ Завершить», чтобы закрыть его."
        )
        return
    if await repo.get_active_diagnostic(user.id):
        await target.answer(
            "🎯 Сначала заверши диагностику уровня: ответь на текущее задание "
            "или нажми «⏹️ Завершить досрочно», затем возвращайся к уроку."
        )
        return

    status = await target.answer("⏳ Составляю структурированный урок...")
    try:
        profile = await repo.get_profile(user.id)
        recent_notes = await repo.get_lesson_notes(user.id, limit=50)
        recent_topics = list(reversed([n.topic for n in recent_notes])) if recent_notes else None
        char_prompt = character_prompt(profile.character if profile else "")

        if topic is None:
            proposals = await lesson_service.generate_proposals(
                level=user.level,
                profile=to_profile_snippet(profile) or None,
                recent_topics=recent_topics,
            )
            if not proposals:
                await status.edit_text("⚠️ Не удалось подобрать темы. Попробуй снова: /lesson")
                return
            await repo.save_topic_proposals(
                user.id,
                [TopicProposal(topic=p["topic"], description=p["description"]) for p in proposals],
            )
            kb = topic_proposals_keyboard(proposals)
            await status.edit_text(
                "📚 Выбери тему для урока:\n\n"
                + "\n".join(f"* {p['topic']} — {p['description']}" for p in proposals),
                reply_markup=kb,
            )
            return

        content = await lesson_service.generate(
            topic,
            level=user.level,
            profile=to_profile_snippet(profile) or None,
            recent_topics=recent_topics,
            character_prompt=char_prompt,
        )
    except Exception as exc:
        logger.exception("Ошибка генерации урока: %s", exc)
        await status.edit_text("⚠️ Не удалось составить урок. Попробуй ещё раз: /lesson")
        return

    session = await repo.start_lesson(user.id, content.topic, lesson_content_to_json(content))
    intro = format_lesson_step("intro", content)
    if user.level is None:
        intro = "🎯 Совет: пройди /diagnostic — тогда уроки будут точно под твой уровень.\n\n" + intro
    await status.edit_text(intro, reply_markup=lesson_keyboard())
    logger.info("Урок начат: user=%s topic=%s session=%s level=%s", user.id, content.topic, session.id, user.level)


@router.message(Command("lesson"))
async def cmd_lesson(message: Message, repo: Repository, lesson_service: LessonService) -> None:
    topic = message.text.removeprefix("/lesson").strip() or None
    await _start_lesson(message, repo, lesson_service, topic, message.from_user)


@router.callback_query(F.data.startswith("lesson:select_topic:"))
async def cb_select_topic(
    callback: CallbackQuery,
    repo: Repository,
    lesson_service: LessonService,
) -> None:
    user = await repo.get_or_create_user(
        callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    idx = int(callback.data.split(":")[-1])
    proposals = await repo.get_topic_proposals(user.id)
    if idx >= len(proposals):
        await callback.answer("Предложение устарело, начни заново: /lesson")
        return
    selected = proposals[idx]
    await callback.answer()
    await repo.delete_topic_proposals(user.id)

    status = await callback.message.answer("⏳ Составляю урок...")
    try:
        profile = await repo.get_profile(user.id)
        recent_notes = await repo.get_lesson_notes(user.id, limit=50)
        recent_topics = list(reversed([n.topic for n in recent_notes])) if recent_notes else None
        char_prompt = character_prompt(profile.character if profile else "")
        content = await lesson_service.generate(
            selected.topic,
            level=user.level,
            profile=to_profile_snippet(profile) or None,
            recent_topics=recent_topics,
            character_prompt=char_prompt,
        )
    except Exception as exc:
        logger.exception("Ошибка генерации урока: %s", exc)
        await status.edit_text("⚠️ Не удалось составить урок. Попробуй снова: /lesson")
        return

    session = await repo.start_lesson(user.id, content.topic, lesson_content_to_json(content))
    intro = format_lesson_step("intro", content)
    if user.level is None:
        intro = "🎯 Совет: пройди /diagnostic — тогда уроки будут точно под твой уровень.\n\n" + intro
    await status.edit_text(intro, reply_markup=lesson_keyboard())
    logger.info("Урок начат: user=%s topic=%s session=%s level=%s", user.id, content.topic, session.id, user.level)


@router.callback_query(F.data == "lesson_start")
async def cb_lesson_start(callback: CallbackQuery, repo: Repository, lesson_service: LessonService) -> None:
    await callback.answer()
    await _start_lesson(callback.message, repo, lesson_service, None, callback.from_user)


@router.callback_query(F.data == "lesson:next")
async def cb_lesson_next(
    callback: CallbackQuery,
    repo: Repository,
    note_service: LessonNoteService,
    srs: SRSService = None,
    state: FSMContext = None,
) -> None:
    if state:
        current = await state.get_state()
        if current and "LessonNav" in current:
            await callback.answer()
            return
        await state.set_state(LessonNav.processing)

    user = await repo.get_or_create_user(
        callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    session = await repo.get_active_lesson(user.id)
    if session is None:
        await callback.answer("Урок уже завершён")
        return
    await callback.answer()

    content = lesson_content_from_json(session.content_json)
    step_name = LESSON_STEPS[session.step]

    # Внутри шага "tasks" перебираем задания по одному.
    if step_name == "tasks" and session.task_index + 1 < len(content.tasks):
        await repo.update_lesson(session.id, task_index=session.task_index + 1)
        session.task_index += 1
        text = format_lesson_step("tasks", content, session.task_index)
        if state:
            await state.clear()
        await callback.message.edit_text(text, reply_markup=lesson_keyboard())
        return

    new_step, new_task_index, finished = next_lesson_position(session.step, session.task_index, len(content.tasks))
    if finished:
        await callback.message.bot.send_chat_action(callback.message.chat.id, action="typing")
        note = await _create_lesson_note(user.id, session.id, content, repo, note_service)
        await repo.finish_active_lessons(user.id)
        await _merge_note_into_profile(repo, user.id, content, note)
        await _save_lesson_vocabulary(repo, user.id, content, session.id, srs)
        if state:
            await state.clear()
        await callback.message.edit_text(_finished_text(content, note), reply_markup=main_menu())

        from core.achievements import check_achievements
        progress_svc = ProgressService(repo)
        progress = await progress_svc.get_progress(user.id, level=user.level)
        achievements = check_achievements(progress)
        earned = [a for a in achievements if a.earned]
        if earned:
            ach_text = "\n".join(f"{a.emoji} {a.name}" for a in earned[:3])
            await callback.message.answer(
                f"<b>Ваши достижения!</b>\n\n{ach_text}",
                reply_markup=main_menu(),
            )
        return

    await repo.update_lesson(session.id, step=new_step, task_index=new_task_index)
    text = format_lesson_step(LESSON_STEPS[new_step], content, new_task_index)
    kb = lesson_recap_keyboard() if LESSON_STEPS[new_step] == "recap" else lesson_keyboard()
    if state:
        await state.clear()
    await callback.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "lesson:repeat")
async def cb_lesson_repeat(callback: CallbackQuery, repo: Repository) -> None:
    user = await repo.get_or_create_user(
        callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    session = await repo.get_active_lesson(user.id)
    if session is None:
        await callback.answer("Урок уже завершён")
        return
    await callback.answer()
    content = lesson_content_from_json(session.content_json)
    text = format_lesson_step(LESSON_STEPS[session.step], content, session.task_index)
    kb = lesson_recap_keyboard() if LESSON_STEPS[session.step] == "recap" else lesson_keyboard()
    await callback.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "lesson:end")
async def cb_lesson_end(
    callback: CallbackQuery,
    repo: Repository,
    note_service: LessonNoteService,
    srs: SRSService = None,
) -> None:
    user = await repo.get_or_create_user(
        callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    session = await repo.get_active_lesson(user.id)
    if session is None:
        await callback.answer("Урок уже завершён")
        return
    await callback.answer()

    content = lesson_content_from_json(session.content_json)
    await callback.message.bot.send_chat_action(callback.message.chat.id, action="typing")
    note = await _create_lesson_note(user.id, session.id, content, repo, note_service)
    await repo.finish_active_lessons(user.id)
    await _merge_note_into_profile(repo, user.id, content, note)
    await _save_lesson_vocabulary(repo, user.id, content, session.id, srs)
    await callback.message.edit_text(_finished_text(content, note), reply_markup=main_menu())
