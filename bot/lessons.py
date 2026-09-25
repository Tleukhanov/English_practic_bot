"""Структурированные уроки (Фаза 1): команда /lesson, навигация по шагам.

Состояние урока хранится в БД (lesson_sessions), поэтому переживает рестарты.
Пользователь идёт по шагам: intro -> vocabulary -> slides -> grammar -> tasks -> recap.
Текст/голос во время урока обрабатываются как практика (см. handlers/text.py, voice.py).

Квота (QuotaGuard): урок генерируется за 3 LLM-вызова, поэтому списывается
cost=3 только после успешной генерации. Фоновые заметки урока (в конце урока)
пропускаются при QuotaExceeded, чтобы не тратить квоту впустую.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from core.characters import character_prompt
from core.lesson_notes import LessonNoteService
from core.lesson_plan import (
    PLAN_LESSON_COUNT,
    LessonPlan,
    LessonPlanService,
    next_plan_index,
)
from core.srs import SRSService
from core.lessons import (
    LESSON_STEPS,
    LESSON_TYPES,
    LessonService,
    lesson_content_from_json,
    lesson_content_to_json,
)
from core.progress import ProgressService
from core.profile import merge_weak_areas, to_profile_snippet
from storage.repo import LessonNote, LessonPlanRow, Repository, TopicProposal, UserProfile

from .formatters import format_lesson_note, format_lesson_plan, format_lesson_step, format_return_hook
from .keyboards import (
    get_webapp_url,
    lesson_keyboard,
    lesson_recap_keyboard,
    main_menu,
    miniapp_lesson_keyboard,
    premium_upsell_keyboard,
    topic_proposals_keyboard,
)
from .quota import QUOTA_EXCEEDED_TEXT, QuotaExceeded, QuotaGuard
from .utils import escape
from .achievements import announce_new_achievements

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


_CORRUPT_LESSON_TEXT = (
    "⚠️ Урок повреждён и не может быть продолжен.\n"
    "Я закрыл его — начни новый: /lesson"
)


async def _close_corrupt_lesson(callback: CallbackQuery, repo: Repository, user_id: int) -> None:
    """Закрывает сессию урока с битым content_json: finish + вежливое сообщение + меню."""
    try:
        await repo.finish_active_lessons(user_id)
    except Exception:
        logger.exception("Не удалось закрыть повреждённый урок user=%s", user_id)
    try:
        await callback.message.edit_text(_CORRUPT_LESSON_TEXT, reply_markup=main_menu())
    except Exception:
        try:
            await callback.message.answer(_CORRUPT_LESSON_TEXT, reply_markup=main_menu())
        except Exception:
            logger.exception("Не удалось сообщить о повреждённом уроке user=%s", user_id)
    logger.warning("Урок повреждён (битый content_json), закрыт: user=%s", user_id)


async def _send_return_hook(callback: CallbackQuery, user, repo: Repository, srs) -> None:
    """Крючок возврата после урока: стрик и очередь повторения."""
    try:
        progress = await ProgressService(repo).get_progress(user.id, level=user.level)
        due_words = 0
        if srs is not None:
            try:
                due_words = len(await srs.get_due_words(user.id, limit=100))
            except Exception:
                due_words = 0
        text = format_return_hook(progress.streak_days, due_words)
        await callback.message.answer(text)
    except Exception:
        logger.exception("Не удалось отправить крючок возврата user=%s", user.id)


async def _create_lesson_note(
    user_id: int,
    session_id: int,
    content,
    repo: Repository,
    note_service: LessonNoteService,
    quota: QuotaGuard | None = None,
) -> LessonNote | None:
    """Генерирует и сохраняет заметку урока. Ошибки не ломают завершение урока.

    Фоновая генерация: если квота исчерпана (QuotaExceeded), пропускаем заметку.
    В противном случае списываем квоту после успешной генерации.
    """
    try:
        if quota is not None:
            await quota.check(user_id)
        answers = await repo.get_lesson_messages(session_id)
        note = await note_service.generate(user_id, session_id, content, answers)
        await repo.add_lesson_note(note)
        if quota is not None:
            await quota.consume(user_id)
        logger.info("Заметка урока: user=%s lesson=%s answers=%s", user_id, session_id, len(answers))
        return note
    except QuotaExceeded:
        logger.debug("Заметка урока пропущена (квота исчерпана): user=%s lesson=%s", user_id, session_id)
        return None
    except Exception:
        logger.exception("Не удалось создать заметку урока user=%s lesson=%s", user_id, session_id)
        return None


async def _maybe_generate_plan(
    message: Message,
    user,
    repo: Repository,
    plan_service: LessonPlanService | None = None,
    quota: QuotaGuard | None = None,
) -> None:
    """Генерирует план после каждых 12 завершённых уроков. Ошибки не ломают завершение урока.

    Фоновая генерация: при QuotaExceeded план пропускается (self-heal при следующем уроке).
    """
    try:
        if plan_service is None:
            return
        completed = await repo.count_finished_lessons(user.id)
        if completed < PLAN_LESSON_COUNT:
            return
        row = await repo.get_lesson_plan(user.id)
        if row is not None and row.based_on_lessons + row.horizon <= completed:
            pass  # план исчерпан — регенерация
        elif row is not None:
            return  # план ещё актуален
        # row is None -> генерируем (само-хил после фейла)
        if quota is not None:
            await quota.check(user.id)
        recent_notes = await repo.get_lesson_notes(user.id, limit=50)
        recent_topics = list(reversed([n.topic for n in recent_notes])) if recent_notes else []
        profile = await repo.get_profile(user.id)
        plan = await plan_service.generate(
            level=user.level,
            profile=to_profile_snippet(profile) or None,
            recent_topics=recent_topics,
            completed_lessons=completed,
        )
        if not plan.lessons:
            return
        await repo.save_lesson_plan(
            LessonPlanRow(
                user_id=user.id,
                plan_json=plan.to_json(),
                horizon=PLAN_LESSON_COUNT,
                based_on_lessons=completed,
                generated_at=datetime.now(timezone.utc).isoformat(),
            )
        )
        if quota is not None:
            await quota.consume(user.id, cost=1)
        await message.answer(format_lesson_plan(plan, completed=completed), reply_markup=main_menu())
        logger.info("План уроков сгенерирован: user=%s completed=%s lessons=%s", user.id, completed, len(plan.lessons))
    except QuotaExceeded:
        logger.debug("План урока пропущен (квота исчерпана): user=%s", user.id)
    except Exception:
        logger.exception("Не удалось сгенерировать план уроков user=%s", user.id)


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
            profile = UserProfile(user_id=user_id)
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


_LAST_LESSON_TYPE: str | None = None

MINIAPP_OFFER_TEXT = (
    "🚀 <b>Интерактивный урок в Mini App</b>\n\n"
    "Презентация, карточки слов с озвучкой, квиз с мгновенной проверкой и живой диалог "
    "с персонажем — прямо в Telegram.\n\n"
    "Или оставь классический урок в чате — как раньше."
)

MINIAPP_DISABLED_TEXT = "📱 Mini App пока не настроен на сервере. Урок в чате: /lesson"


async def _answer_miniapp_offer(message: Message, settings=None) -> bool:
    """Предлагает Mini App или классический урок. False — Mini App выключен."""
    url = getattr(settings, "webapp_url", "") or get_webapp_url()
    keyboard = miniapp_lesson_keyboard(url)
    if keyboard is None:
        return False
    await message.answer(MINIAPP_OFFER_TEXT, reply_markup=keyboard)
    return True


@router.message(Command("app"))
async def cmd_app(message: Message, settings=None) -> None:
    """Явный вход в Mini App (основной путь — /lesson)."""
    if not await _answer_miniapp_offer(message, settings):
        await message.answer(MINIAPP_DISABLED_TEXT, reply_markup=main_menu())


def _pick_lesson_type() -> str:
    """Выбирает формат урока так, чтобы подряд не повторялся один и тот же."""
    global _LAST_LESSON_TYPE
    options = [t for t in LESSON_TYPES if t != _LAST_LESSON_TYPE]
    chosen = random.choice(options)
    _LAST_LESSON_TYPE = chosen
    return chosen


async def _plan_hint_for_topic(repo: Repository, user, topic: str) -> str | None:
    """plan_hint для выбранной вручную темы — только если она совпадает с плановой."""
    try:
        row = await repo.get_lesson_plan(user.id)
        if row is None:
            return None
        completed = await repo.count_finished_lessons(user.id)
        idx = next_plan_index(row.based_on_lessons, completed, row.horizon)
        if idx is None:
            return None
        lp = LessonPlan.from_json(row.plan_json)
        if idx >= len(lp.lessons) or lp.lessons[idx].topic != topic:
            return None
        return f"Plan lesson {idx + 1}/{row.horizon}: {topic}. Focus: {lp.lessons[idx].focus}"
    except Exception:
        logger.warning("Не удалось получить plan_hint user=%s", user.id, exc_info=True)
        return None


async def _start_lesson(target, repo: Repository, lesson_service: LessonService, topic: str | None, user_from, quota: QuotaGuard | None = None) -> None:
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

    if quota is not None:
        try:
            await quota.check(user.id)
        except QuotaExceeded:
            await target.answer(QUOTA_EXCEEDED_TEXT, reply_markup=premium_upsell_keyboard())
            return

    plan_hint: str | None = None
    plan_status_line = ""
    if topic is None:
        try:
            completed = await repo.count_finished_lessons(user.id)
            row = await repo.get_lesson_plan(user.id)
            if row is not None:
                lp = LessonPlan.from_json(row.plan_json)
                idx = next_plan_index(row.based_on_lessons, completed, row.horizon)
                if idx is not None and idx < len(lp.lessons):
                    topic = lp.lessons[idx].topic
                    plan_hint = f"Plan lesson {idx + 1}/{row.horizon}: {topic}. Focus: {lp.lessons[idx].focus}"
                    plan_status_line = f"📖 Продолжаю по плану: урок {idx + 1}/{row.horizon}\n"
        except Exception:
            logger.warning("Не удалось применить план уроков user=%s", user.id, exc_info=True)
    else:
        plan_hint = await _plan_hint_for_topic(repo, user, topic)

    status = await target.answer(f"{plan_status_line}⏳ Составляю структурированный урок...")
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
            if quota is not None:
                try:
                    await quota.consume(user.id, cost=1)
                except QuotaExceeded:
                    logger.warning(
                        "Гонка квоты при списании за темы: user=%s — списание пропущено", user.id
                    )
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
            lesson_type=_pick_lesson_type(),
            plan_hint=plan_hint,
        )
    except Exception as exc:
        logger.exception("Ошибка генерации урока: %s", exc)
        await status.edit_text("⚠️ Не удалось составить урок. Попробуй ещё раз: /lesson")
        return

    if quota is not None:
        try:
            await quota.consume(user.id, cost=3)
        except QuotaExceeded:
            logger.warning(
                "Гонка квоты при списании урока: user=%s — урок начат, списание пропущено", user.id
            )

    session = await repo.start_lesson(user.id, content.topic, lesson_content_to_json(content))
    intro = format_lesson_step("intro", content)
    if user.level is None:
        intro = "🎯 Совет: пройди /diagnostic — тогда уроки будут точно под твой уровень.\n\n" + intro
    await status.edit_text(intro, reply_markup=lesson_keyboard())
    logger.info("Урок начат: user=%s topic=%s session=%s level=%s", user.id, content.topic, session.id, user.level)


@router.message(Command("lesson"))
async def cmd_lesson(
    message: Message,
    repo: Repository,
    lesson_service: LessonService,
    quota: QuotaGuard | None = None,
    settings=None,
) -> None:
    topic = message.text.removeprefix("/lesson").strip() or None
    if topic is None:
        # Без явной темы предлагаем Mini App + классический урок (не ломая /lesson <тема>).
        if await _answer_miniapp_offer(message, settings):
            return
    await _start_lesson(message, repo, lesson_service, topic, message.from_user, quota)


@router.callback_query(F.data.startswith("lesson:select_topic:"))
async def cb_select_topic(
    callback: CallbackQuery,
    repo: Repository,
    lesson_service: LessonService,
    quota: QuotaGuard | None = None,
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

    if quota is not None:
        try:
            await quota.check(user.id)
        except QuotaExceeded:
            await callback.message.answer(QUOTA_EXCEEDED_TEXT, reply_markup=premium_upsell_keyboard())
            return

    status = await callback.message.answer("⏳ Составляю урок...")
    try:
        profile = await repo.get_profile(user.id)
        recent_notes = await repo.get_lesson_notes(user.id, limit=50)
        recent_topics = list(reversed([n.topic for n in recent_notes])) if recent_notes else None
        char_prompt = character_prompt(profile.character if profile else "")
        plan_hint = await _plan_hint_for_topic(repo, user, selected.topic)
        content = await lesson_service.generate(
            selected.topic,
            level=user.level,
            profile=to_profile_snippet(profile) or None,
            recent_topics=recent_topics,
            character_prompt=char_prompt,
            lesson_type=_pick_lesson_type(),
            plan_hint=plan_hint,
        )
    except Exception as exc:
        logger.exception("Ошибка генерации урока: %s", exc)
        await status.edit_text("⚠️ Не удалось составить урок. Попробуй снова: /lesson")
        return

    if quota is not None:
        try:
            await quota.consume(user.id, cost=3)
        except QuotaExceeded:
            logger.warning(
                "Гонка квоты при списании урока: user=%s — урок начат, списание пропущено", user.id
            )

    session = await repo.start_lesson(user.id, content.topic, lesson_content_to_json(content))
    intro = format_lesson_step("intro", content)
    if user.level is None:
        intro = "🎯 Совет: пройди /diagnostic — тогда уроки будут точно под твой уровень.\n\n" + intro
    await status.edit_text(intro, reply_markup=lesson_keyboard())
    logger.info("Урок начат: user=%s topic=%s session=%s level=%s", user.id, content.topic, session.id, user.level)


@router.callback_query(F.data == "lesson_start")
async def cb_lesson_start(callback: CallbackQuery, repo: Repository, lesson_service: LessonService, quota: QuotaGuard | None = None) -> None:
    await callback.answer()
    await _start_lesson(callback.message, repo, lesson_service, None, callback.from_user, quota)


@router.callback_query(F.data == "lesson:next")
async def cb_lesson_next(
    callback: CallbackQuery,
    repo: Repository,
    note_service: LessonNoteService,
    srs: SRSService = None,
    state: FSMContext = None,
    quota: QuotaGuard | None = None,
    plan_service: LessonPlanService | None = None,
) -> None:
    nav_owned = False
    if state:
        current = await state.get_state()
        if current and "ReviewState" in current:
            # Пользователь на середине /review: не трогаем его FSM и не ведём в урок.
            await callback.answer("📖 Сейчас идёт повторение слов — ответь текстом или заверши его (⏹️).")
            return
        if current and "LessonNav" in current:
            await callback.answer()
            return
        await state.set_state(LessonNav.processing)
        nav_owned = True
    try:
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
        if content is None:
            await _close_corrupt_lesson(callback, repo, user.id)
            return
        step_name = LESSON_STEPS[session.step]

        # Внутри шага "tasks" перебираем задания по одному.
        if step_name == "tasks" and session.task_index + 1 < len(content.tasks):
            await repo.update_lesson(session.id, task_index=session.task_index + 1)
            session.task_index += 1
            await callback.message.edit_text(
                format_lesson_step("tasks", content, session.task_index),
                reply_markup=lesson_keyboard(),
            )
            return

        new_step, new_task_index, finished = next_lesson_position(session.step, session.task_index, len(content.tasks))
        if finished:
            # Завершаем урок ДО генерации заметки: повторный тап не создаст дубль.
            await repo.finish_active_lessons(user.id)
            await callback.message.bot.send_chat_action(callback.message.chat.id, action="typing")
            note = await _create_lesson_note(user.id, session.id, content, repo, note_service, quota=quota)
            await _merge_note_into_profile(repo, user.id, content, note)
            await _save_lesson_vocabulary(repo, user.id, content, session.id, srs)
            await callback.message.edit_text(_finished_text(content, note), reply_markup=main_menu())

            await _send_return_hook(callback, user, repo, srs)
            await announce_new_achievements(callback.message, user, repo, reply_markup=main_menu())
            await _maybe_generate_plan(callback.message, user, repo, plan_service, quota)
            return

        await repo.update_lesson(session.id, step=new_step, task_index=new_task_index)
        text = format_lesson_step(LESSON_STEPS[new_step], content, new_task_index)
        kb = lesson_recap_keyboard() if LESSON_STEPS[new_step] == "recap" else lesson_keyboard()
        await callback.message.edit_text(text, reply_markup=kb)
    finally:
        # Чистим только свой LessonNav: state.clear() затёр бы чужой FSM (например, ReviewState).
        if state and nav_owned:
            current = await state.get_state()
            if current and "LessonNav" in current:
                await state.clear()


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
    if content is None:
        await _close_corrupt_lesson(callback, repo, user.id)
        return
    text = format_lesson_step(LESSON_STEPS[session.step], content, session.task_index)
    kb = lesson_recap_keyboard() if LESSON_STEPS[session.step] == "recap" else lesson_keyboard()
    await callback.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "lesson:end")
async def cb_lesson_end(
    callback: CallbackQuery,
    repo: Repository,
    note_service: LessonNoteService,
    srs: SRSService = None,
    state: FSMContext = None,
    quota: QuotaGuard | None = None,
    plan_service: LessonPlanService | None = None,
) -> None:
    nav_owned = False
    if state:
        current = await state.get_state()
        if current and "ReviewState" in current:
            # Пользователь на середине /review: не трогаем его FSM и не ведём в урок.
            await callback.answer("📖 Сейчас идёт повторение слов — ответь текстом или заверши его (⏹️).")
            return
        if current and "LessonNav" in current:
            await callback.answer()
            return
        await state.set_state(LessonNav.processing)
        nav_owned = True
    try:
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
        if content is None:
            await _close_corrupt_lesson(callback, repo, user.id)
            return
        # Завершаем урок ДО генерации заметки: повторный тап не создаст дубль.
        await repo.finish_active_lessons(user.id)
        await callback.message.bot.send_chat_action(callback.message.chat.id, action="typing")
        note = await _create_lesson_note(user.id, session.id, content, repo, note_service, quota=quota)
        await _merge_note_into_profile(repo, user.id, content, note)
        await _save_lesson_vocabulary(repo, user.id, content, session.id, srs)
        await callback.message.edit_text(_finished_text(content, note), reply_markup=main_menu())

        await _send_return_hook(callback, user, repo, srs)
        await announce_new_achievements(callback.message, user, repo, reply_markup=main_menu())
        await _maybe_generate_plan(callback.message, user, repo, plan_service, quota)
    finally:
        # Чистим только свой LessonNav: state.clear() затёр бы чужой FSM (например, ReviewState).
        if state and nav_owned:
            current = await state.get_state()
            if current and "LessonNav" in current:
                await state.clear()
