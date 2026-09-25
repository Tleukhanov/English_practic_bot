"""API уроков Mini App: генерация деки, ответы квиза и финализация.

Модуль собирает собственное ``aiohttp``-приложение, которое :func:`bot.webapp.
create_webapp` монтирует как под-приложение на ``/api``. Зависимости (repo,
llm, quota, srs, plan_service, tts) передаются словарём ``deps`` и читаются
из ``request.app`` — поэтому в тестах подменяются без сети и Telegram.

Контракт с фронтом (``web/app.js``) — все POST шлют ``initData`` в теле,
в query и заголовке; ``user_id`` берётся только из подписанного initData.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Mapping

from aiohttp import web
from aiogram import Bot

from core.analytics import track_event
from core.characters import character_prompt
from core.deck import DECK_PRESETS, Deck, deck_from_json, generate_deck
from core.lesson_plan import PLAN_LESSON_COUNT, LessonPlan, next_plan_index
from core.profile import to_profile_snippet
from core.progress import ProgressService
from core.srs import SRSService
from storage.repo import LessonNote, LessonPlanRow

from .config import Settings
from .quota import QUOTA_EXCEEDED_TEXT, QuotaExceeded
from .webapp import (
    BOT_KEY,
    DEPS_KEY,
    SETTINGS_KEY,
    authenticate,
    dependency,
    error_response,
    ok_response,
    read_json,
)

logger = logging.getLogger(__name__)

routes = web.RouteTableDef()
DEFAULT_PRESET = "mixed"
VOICE_RESERVED_NOTE = "Голосовой ответ приходит отдельным этапом."


# ---------- утилиты разбора тела ----------


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except (TypeError, ValueError):
            return None
    return None


def _first_int(payload: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = _int_or_none(payload.get(key))
        if value is not None:
            return value
    return None


def _text_or_none(payload: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _preset_or_default(value: Any) -> str:
    if isinstance(value, str) and value.strip().lower() in DECK_PRESETS:
        return value.strip().lower()
    return DEFAULT_PRESET


def quota_error_response() -> web.Response:
    """Единый ответ при исчерпанной квоте: фронт показывает апселл."""
    return error_response("quota", status=429, message=QUOTA_EXCEEDED_TEXT, quota=True)


def _deck_generator(deps: Any):
    """Генератор деки: из deps (тесты) или штатный generate_deck."""
    if isinstance(deps, Mapping):
        generator = deps.get("deck_generator")
    else:
        generator = getattr(deps, "deck_generator", None)
    return generator or generate_deck


# ---------- контекст генерации (как в bot/lessons.py) ----------


async def _lesson_context(request: web.Request, user) -> dict[str, Any]:
    """Профиль, персонаж и недавние темы — те же источники, что у чат-урока."""
    repo = dependency(request, "repo")
    profile = await repo.get_profile(user.id)
    recent_notes = await repo.get_lesson_notes(user.id, limit=50)
    recent_topics = list(reversed([note.topic for note in recent_notes])) if recent_notes else None
    return {
        "level": user.level,
        "profile": to_profile_snippet(profile) or None,
        "recent_topics": recent_topics,
        "character_prompt": character_prompt(profile.character if profile else ""),
    }


async def _planned_topic(request: web.Request, user) -> tuple[str | None, str | None]:
    """Тема и plan_hint из плана уроков (когда фронт не прислал тему)."""
    repo = dependency(request, "repo")
    try:
        completed = await repo.count_finished_lessons(user.id)
        row = await repo.get_lesson_plan(user.id)
        if row is None:
            return None, None
        plan = LessonPlan.from_json(row.plan_json)
        idx = next_plan_index(row.based_on_lessons, completed, row.horizon)
        if idx is None or idx >= len(plan.lessons):
            return None, None
        planned = plan.lessons[idx]
        hint = f"Plan lesson {idx + 1}/{row.horizon}: {planned.topic}. Focus: {planned.focus}"
        return planned.topic, hint
    except Exception:
        logger.warning("Не удалось применить план уроков user=%s", user.id, exc_info=True)
        return None, None


# ---------- POST /api/deck/new ----------


@routes.post("/deck/new")
async def deck_new(request: web.Request) -> web.Response:
    """Новый урок: квота → одна LLM-генерация деки → session."""
    payload = await read_json(request)
    tg_user_id, error = await authenticate(request, payload)
    if error is not None:
        return error

    repo = dependency(request, "repo")
    quota = dependency(request, "quota")
    llm = dependency(request, "llm")
    if repo is None or llm is None:
        return error_response("service_unavailable", status=503)

    try:
        user = await repo.get_or_create_user(tg_user_id)
    except Exception:
        logger.exception("Не удалось найти пользователя: tg=%s", tg_user_id)
        return error_response("user_not_found", status=500)

    topic = _text_or_none(payload, "topic", "theme", "title")
    plan_hint = None
    if not topic:
        topic, plan_hint = await _planned_topic(request, user)
    preset = _preset_or_default(payload.get("preset"))

    # Квота проверяется ДО генерации: при исчерпанной лимите LLM не дёргаем.
    if quota is not None:
        try:
            await quota.check(user.id)
        except QuotaExceeded:
            return quota_error_response()

    try:
        context = await _lesson_context(request, user)
        deck = await _generator_call(request, llm, topic, plan_hint, preset, **context)
    except Exception:
        logger.exception("Ошибка генерации деки: user=%s topic=%s", user.id, topic)
        return error_response("generation_failed", status=502)
    if deck is None:
        return error_response("generation_failed", status=502)

    if quota is not None:
        try:
            await quota.consume(user.id, cost=1)
        except QuotaExceeded:
            logger.warning("Гонка квоты при списании деки: user=%s", user.id)

    try:
        session = await repo.start_mini_lesson(user.id, deck.topic, deck.to_json(), deck.preset)
    except Exception:
        logger.exception("Не удалось сохранить сессию урока: user=%s", user.id)
        return error_response("save_failed", status=500)

    await track_event(repo, user.id, "miniapp_deck_new", {"preset": deck.preset})
    logger.info("Mini App урок: user=%s topic=%s session=%s", user.id, deck.topic, session.id)
    return ok_response(
        {
            "deck": deck.to_dict(),
            "session_id": session.id,
            "preset": deck.preset,
            "topic": deck.topic,
            "plan_hint": plan_hint,
        }
    )


async def _generator_call(
    request: web.Request,
    llm: Any,
    topic: str | None,
    plan_hint: str | None,
    preset: str,
    **context: Any,
) -> Deck | None:
    """Один вызов генератора деки (штатного или подменённого в тестах)."""
    generator = _deck_generator(request.app.get(DEPS_KEY))
    return await generator(
        llm,
        topic=topic,
        plan_hint=plan_hint,
        preset=preset,
        **context,
    )


# ---------- POST /api/deck/answer ----------


@routes.post("/deck/answer")
async def deck_answer(request: web.Request) -> web.Response:
    """Мгновенная проверка ответа квиза. В БД не пишем — итог приходит в finish."""
    payload = await read_json(request)
    tg_user_id, error = await authenticate(request, payload)
    if error is not None:
        return error

    session, error = await _active_session(request, tg_user_id)
    if error is not None:
        return error

    quiz_index = _first_int(payload, "quiz_index", "question_index", "index")
    chosen = _first_int(payload, "chosen", "answer_index", "selected_index")
    if quiz_index is None or chosen is None:
        return error_response("bad_answer")

    deck = deck_from_json(session.content_json)
    if deck is None:
        return error_response("corrupt_deck", status=409)
    if not 0 <= quiz_index < len(deck.quiz):
        return error_response("bad_question")
    item = deck.quiz[quiz_index]
    return ok_response(
        {
            "correct": chosen == item.answer_index,
            "answer_index": item.answer_index,
            "explanation": item.explanation_ru,
            "explanation_ru": item.explanation_ru,
        }
    )


async def _active_session(request: web.Request, tg_user_id: int):
    """Активная mini-сессия пользователя; (session, error_response)."""
    repo = dependency(request, "repo")
    try:
        user = await repo.get_or_create_user(tg_user_id)
        session = await repo.get_active_mini_lesson(user.id)
    except Exception:
        logger.exception("Не удалось загрузить сессию урока: tg=%s", tg_user_id)
        return None, error_response("session_unavailable", status=500)
    if session is None:
        return None, error_response("session_not_found", status=404)
    return session, None


# ---------- POST /api/deck/finish ----------


def _quiz_results(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Нормализует ответы фронта в [{quiz_index, chosen, correct}] для score_json."""
    raw = payload.get("quiz_answers") or payload.get("answers") or []
    results: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return results
    for position, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        quiz_index = _first_int(item, "quiz_index", "question_index", "index")
        if quiz_index is None:
            quiz_index = position
        chosen = _first_int(item, "chosen", "answer_index", "selected_index")
        results.append(
            {
                "quiz_index": quiz_index,
                "chosen": chosen,
                "correct": bool(item.get("correct")),
            }
        )
    return results


def _repeat_words(payload: Mapping[str, Any]) -> list[str]:
    """Слова, отмеченные фронтом как «повторю» (для ответа и SRS-подсказки)."""
    raw = payload.get("flashcards") or payload.get("words") or {}
    if not isinstance(raw, dict):
        return []
    return [str(word).strip() for word, known in raw.items() if known is False and str(word).strip()]


@routes.post("/deck/finish")
async def deck_finish(request: web.Request) -> web.Response:
    """Финал урока: score_json, SRS, заметка/XP, план. Никогда не отдаёт 500 из-за сбоя."""
    payload = await read_json(request)
    tg_user_id, error = await authenticate(request, payload)
    if error is not None:
        return error

    repo = dependency(request, "repo")
    if repo is None:
        return error_response("service_unavailable", status=503)
    try:
        user = await repo.get_or_create_user(tg_user_id)
    except Exception:
        logger.exception("Не удалось найти пользователя: tg=%s", tg_user_id)
        return error_response("user_not_found", status=500)

    score = _first_int(payload, "score") or 0
    preset = _preset_or_default(payload.get("preset"))
    results = _quiz_results(payload)
    score_json = json.dumps(results, ensure_ascii=False)
    session_id = _first_int(payload, "session_id")

    session = None
    try:
        session = await repo.get_active_mini_lesson(user.id)
    except Exception:
        logger.exception("Не удалось прочитать mini-сессию: user=%s", user.id)

    if session is not None and session_id is not None and session.id != session_id:
        # Фронт повторно отправил финал уже закрытой сессии — не мешаем закрытию.
        logger.info("Mini App финал: session %s уже не активна (активна %s)", session_id, session.id)
    deck = deck_from_json(session.content_json) if session is not None else None

    repeat = _repeat_words(payload)

    if session is not None:
        try:
            await repo.finish_mini_lesson(session.id, score_json)
        except Exception:
            logger.exception("Не удалось закрыть mini-сессию: %s", session.id)

    try:
        await _save_vocabulary(request, user.id, deck, session.id if session else 0)
    except Exception:
        logger.exception("Не удалось сохранить слова урока в SRS: user=%s", user.id)

    xp = 0
    try:
        xp = await _finalize_progress(request, user, session, deck, score)
    except Exception:
        logger.exception("Не удалось начислить итоги урока: user=%s", user.id)

    next_topic = ""
    try:
        next_topic = await _maybe_generate_plan(request, user)
    except Exception:
        logger.exception("Не удалось обновить план уроков: user=%s", user.id)

    await track_event(
        repo,
        user.id,
        "miniapp_deck_finish",
        {"score": score, "preset": preset, "correct": sum(1 for item in results if item["correct"])},
    )
    logger.info(
        "Mini App финал: user=%s session=%s score=%s xp=%s",
        user.id,
        session.id if session else None,
        score,
        xp,
    )
    return ok_response(
        {
            "score": score,
            "xp": xp,
            "next_topic": next_topic,
            "preset": preset,
            "repeat_words": repeat,
        }
    )


async def _save_vocabulary(
    request: web.Request, user_id: int, deck: Deck | None, session_id: int
) -> int:
    """Слова деки → SRS (как _save_lesson_vocabulary в bot/lessons.py)."""
    if deck is None or not deck.vocabulary:
        return 0
    srs = dependency(request, "srs")
    if srs is None:
        srs = SRSService(dependency(request, "repo"))
    words = [
        {"word": card.word, "translation": card.translation, "example": card.example}
        for card in deck.vocabulary
        if card.word
    ]
    if not words:
        return 0
    added = await srs.add_words(user_id, words, lesson_id=session_id)
    if added:
        logger.info("SRS: добавлено %d слов из деки user=%s", added, user_id)
    return added


async def _finalize_progress(
    request: web.Request, user, session, deck: Deck | None, score: int
) -> int:
    """Заметка урока → прогресс/XP/достижения. Возвращает НОВЫЙ XP (дельта)."""
    repo = dependency(request, "repo")
    service = ProgressService(repo)
    before = (await service.get_progress(user.id, level=user.level)).xp
    if session is not None and deck is not None:
        note = _build_note(user.id, session, deck, score)
        await repo.add_lesson_note(note)
    after = (await service.get_progress(user.id, level=user.level)).xp
    return max(after - before, 0)


def _build_note(user_id: int, session, deck: Deck, score: int) -> LessonNote:
    """Заметка урока по деке — без LLM-вызова (квота уже списана за деку)."""
    words = [card.word for card in deck.vocabulary if card.word]
    vocabulary = f"+{len(words)} новых слов"
    if words:
        vocabulary += ": " + ", ".join(words[:10])
    return LessonNote(
        user_id=user_id,
        lesson_id=session.id,
        topic=session.topic or deck.topic,
        vocabulary=vocabulary,
        grammar="",
        speaking="",
        mistakes="",
        recommendation=f"Mini App: квиз {score}/{len(deck.quiz)}. Повтори слова и пройди новую тему.",
        created_at=datetime.now(timezone.utc).isoformat(),
    )


async def _maybe_generate_plan(request: web.Request, user) -> str:
    """Логика _maybe_generate_plan из bot/lessons.py, но без сообщения в чат.

    Возвращает тему следующего урока из плана (пустая строка — плана нет).
    """
    repo = dependency(request, "repo")
    plan_service = dependency(request, "plan_service")
    quota = dependency(request, "quota")
    next_topic = ""
    try:
        row = await repo.get_lesson_plan(user.id)
        if row is not None:
            plan = LessonPlan.from_json(row.plan_json)
            completed = await repo.count_finished_lessons(user.id)
            idx = next_plan_index(row.based_on_lessons, completed, row.horizon)
            if idx is not None and idx < len(plan.lessons):
                next_topic = plan.lessons[idx].topic
    except Exception:
        logger.warning("Не удалось прочитать план уроков user=%s", user.id, exc_info=True)

    if plan_service is None:
        return next_topic
    try:
        completed = await repo.count_finished_lessons(user.id)
        if completed < PLAN_LESSON_COUNT:
            return next_topic
        row = await repo.get_lesson_plan(user.id)
        if row is not None and row.based_on_lessons + row.horizon > completed:
            return next_topic  # план ещё актуален
        if quota is not None:
            await quota.check(user.id)
        recent_notes = await repo.get_lesson_notes(user.id, limit=50)
        recent_topics = list(reversed([note.topic for note in recent_notes])) if recent_notes else []
        profile = await repo.get_profile(user.id)
        plan = await plan_service.generate(
            level=user.level,
            profile=to_profile_snippet(profile) or None,
            recent_topics=recent_topics,
            completed_lessons=completed,
        )
        if not plan.lessons:
            return next_topic
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
        idx = next_plan_index(completed, completed, PLAN_LESSON_COUNT)
        next_topic = plan.lessons[idx or 0].topic if plan.lessons else next_topic
        logger.info(
            "План уроков сгенерирован после Mini App урока: user=%s completed=%s", user.id, completed
        )
    except QuotaExceeded:
        logger.debug("План урока пропущен (квота исчерпана): user=%s", user.id)
    except Exception:
        logger.exception("Не удалось сгенерировать план уроков user=%s", user.id)
    return next_topic


# ---------- зарезервированный голосовой этап ----------


@routes.post("/voice/answer")
async def voice_answer(request: web.Request) -> web.Response:
    """Заглушка голосового этапа (STT + оценка фразы) — следующий шаг MINI_APP.md."""
    payload = await read_json(request)
    _, error = await authenticate(request, payload)
    if error is not None:
        return error
    return error_response("not_implemented", status=501, message=VOICE_RESERVED_NOTE)


# ---------- сборка под-приложения ----------


def build_app(settings: Settings, bot: Bot, deps: Mapping[str, Any] | Any) -> web.Application:
    """Под-приложение с роутами уроков; монтируется на /api."""
    app = web.Application()
    app[SETTINGS_KEY] = settings
    app[BOT_KEY] = bot
    app[DEPS_KEY] = deps
    app.add_routes(routes)
    return app
