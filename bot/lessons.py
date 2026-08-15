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
from aiogram.types import CallbackQuery, Message

from core.lesson_notes import LessonNoteService
from core.lessons import (
    LESSON_STEPS,
    LessonService,
    lesson_content_from_json,
    lesson_content_to_json,
)
from core.profile import merge_weak_areas, to_profile_snippet
from storage.repo import LessonNote, Repository

from .formatters import format_lesson_note, format_lesson_step
from .keyboards import lesson_keyboard, main_menu
from .utils import escape

router = Router()
logger = logging.getLogger(__name__)


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


async def _merge_note_into_profile(repo: Repository, user_id: int, content, note: LessonNote | None) -> None:
    """Итоги урока попадают в слабые места профиля (Фаза 5 -> Фаза 4)."""
    if note is None:
        return
    try:
        profile = await repo.get_profile(user_id)
        if profile is None:
            return
        grammar_rule = content.grammar.rule if content.grammar else ""
        new_weak = merge_weak_areas(profile, grammar_rule, note.mistakes)
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
        content = await lesson_service.generate(
            topic, level=user.level, profile=to_profile_snippet(profile) or None
        )
    except Exception as exc:
        logger.exception("Ошибка генерации урока: %s", exc)
        await status.edit_text("⚠️ Не удалось составить урок. Проверь LLM_API_KEY в .env и попробуй ещё раз.")
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


@router.callback_query(F.data == "lesson_start")
async def cb_lesson_start(callback: CallbackQuery, repo: Repository, lesson_service: LessonService) -> None:
    await callback.answer()
    await _start_lesson(callback.message, repo, lesson_service, None, callback.from_user)


@router.callback_query(F.data == "lesson:next")
async def cb_lesson_next(
    callback: CallbackQuery,
    repo: Repository,
    note_service: LessonNoteService,
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
    step_name = LESSON_STEPS[session.step]

    # Внутри шага "tasks" перебираем задания по одному.
    if step_name == "tasks" and session.task_index + 1 < len(content.tasks):
        await repo.update_lesson(session.id, task_index=session.task_index + 1)
        session.task_index += 1
        text = format_lesson_step("tasks", content, session.task_index)
        await callback.message.edit_text(text, reply_markup=lesson_keyboard())
        return

    new_step, new_task_index, finished = next_lesson_position(session.step, session.task_index, len(content.tasks))
    if finished:
        note = await _create_lesson_note(user.id, session.id, content, repo, note_service)
        await repo.finish_active_lessons(user.id)
        await _merge_note_into_profile(repo, user.id, content, note)
        await callback.message.edit_text(_finished_text(content, note), reply_markup=main_menu())
        return

    await repo.update_lesson(session.id, step=new_step, task_index=new_task_index)
    text = format_lesson_step(LESSON_STEPS[new_step], content, new_task_index)
    await callback.message.edit_text(text, reply_markup=lesson_keyboard())


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
    await callback.message.edit_text(text, reply_markup=lesson_keyboard())


@router.callback_query(F.data == "lesson:end")
async def cb_lesson_end(
    callback: CallbackQuery,
    repo: Repository,
    note_service: LessonNoteService,
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
    note = await _create_lesson_note(user.id, session.id, content, repo, note_service)
    await repo.finish_active_lessons(user.id)
    await _merge_note_into_profile(repo, user.id, content, note)
    await callback.message.edit_text(_finished_text(content, note), reply_markup=main_menu())
