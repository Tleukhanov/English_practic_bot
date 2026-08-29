"""Общая логика одной «практики» — используется текстовым и голосовым хэндлерами."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import Settings
from core.models import PracticeResult
from core.characters import character_prompt
from core.practice import PracticeParseError, PracticeService
from core.profile import ProfileService, profile_update_due, to_profile_snippet
from core.weak_areas import WeakAreaService
from storage.repo import Repository, UserProfile, UserRow

from .formatters import format_practice_result, format_practice_soft, format_reveal
from .keyboards import reveal_keyboard

logger = logging.getLogger(__name__)

router = Router()


@dataclass
class PracticeTurn:
    reply: str  # готовый HTML-ответ для пользователя
    result: PracticeResult  # структурированный результат (нужен для TTS)
    message_id: int = 0  # id фразы пользователя в БД (для кнопки «Показать ошибку»)


def issues_to_json(result) -> str:
    payload = [
        {
            "category": issue.category,
            "problem": issue.problem,
            "suggestion": issue.suggestion,
            "correction": issue.correction,
        }
        for issue in result.issues
    ]
    return json.dumps(payload, ensure_ascii=False)


def practice_markup(
    result: PracticeResult,
    base_markup: InlineKeyboardMarkup | None = None,
    message_id: int = 0,
) -> InlineKeyboardMarkup | None:
    """Клавиатура к ответу практики: при ошибке предлагаем кнопку «Показать ошибку».

    Внутри урока (base_markup задан) добавляем кнопку «Показать ошибку» к клавиатуре урока.
    message_id — id фразы в БД, чтобы «Показать ошибку» показывала разбор именно этой фразы.
    """
    if not result.is_correct and base_markup is not None:
        existing_rows = [row[:] for row in base_markup.inline_keyboard]
        data = f"practice:reveal:{message_id}" if message_id else "practice:reveal"
        existing_rows.insert(0, [InlineKeyboardButton(text="🔍 Показать ошибку", callback_data=data)])
        return InlineKeyboardMarkup(inline_keyboard=existing_rows)
    if not result.is_correct and base_markup is None:
        return reveal_keyboard(message_id)
    return base_markup


async def get_or_create_user(message: Message, repo: Repository) -> UserRow:
    return await repo.get_or_create_user(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )


# Сериализуем фоновые обновления профиля: два параллельных перезаписывают друг друга
# из устаревших снапшотов (last-write-wins теряет данные).
_PROFILE_LOCKS: dict[int, asyncio.Lock] = {}


def _profile_lock(user_id: int) -> asyncio.Lock:
    lock = _PROFILE_LOCKS.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _PROFILE_LOCKS[user_id] = lock
    return lock


async def _update_profile_background(
    user_id: int,
    history: list[dict[str, str]],
    text: str,
    repo: Repository,
    profile_service: ProfileService,
) -> None:
    """Фоновое обновление профиля пользователя (Фаза 4).

    Базой для диффа берём профиль на МОМЕНТ запуска задачи (свежий), а не
    снапшот на момент реплики. Лок на юзера не даёт гонкам перезаписать друг друга.
    Ошибки не роняют основной поток.
    """
    try:
        async with _profile_lock(user_id):
            previous = await repo.get_profile(user_id)
            dialogue = history + [{"role": "user", "content": text}]
            updated = await profile_service.update(user_id, previous, dialogue)
            await repo.save_profile(updated)
            logger.info("Профиль обновлён: user=%s", user_id)
    except Exception:
        logger.exception("Не удалось обновить профиль пользователя %s", user_id)


async def run_practice(
    message: Message,
    repo: Repository,
    practice: PracticeService,
    settings: Settings,
    text: str,
    *,
    prefix: str = "",
    profile_service: ProfileService | None = None,
    lesson_id: int | None = None,
) -> PracticeTurn:
    """Проводит практику по переданному тексту, сохраняет в БД и возвращает ответ.

    Поднимает исключение при сбое LLM — хэндлер решает, что показать пользователю.
    lesson_id — сессия урока, к которой относится реплика (для заметок урока, Фаза 5).
    """
    user = await get_or_create_user(message, repo)
    profile = await repo.get_profile(user.id)
    # Профиль должен существовать, иначе новичок потеряет и интересы, и слабые места.
    if profile is None:
        profile = UserProfile(user_id=user.id)
        await repo.save_profile(profile)
    snippet = to_profile_snippet(profile) or None
    char_prompt = character_prompt(profile.character if profile else "")
    history = await repo.get_history(user.id, settings.max_context_messages)

    weak_svc = WeakAreaService(repo)
    weak_areas_prompt = await weak_svc.get_top_for_prompt(user.id)

    await message.bot.send_chat_action(message.chat.id, action="typing")
    result = await practice.analyze(
        text, history, profile=snippet, character_prompt=char_prompt,
        weak_areas_prompt=weak_areas_prompt,
    )

    msg_id = await repo.add_user_message(
        user.id,
        text,
        is_correct=result.is_correct,
        issues_json=issues_to_json(result),
        corrected_text=result.corrected_text,
        lesson_id=lesson_id,
    )

    await weak_svc.update_from_practice(user.id, result.issues, result.is_correct, result.corrected_text)
    await weak_svc.decay(user.id)

    reply = format_practice_soft(result)
    if prefix:
        reply = f"{prefix}\n\n{reply}"
    await repo.add_assistant_message(user.id, format_practice_result(result, html=True))

    if profile_service is not None and profile_update_due(profile):
        asyncio.create_task(
            _update_profile_background(user.id, history, text, repo, profile_service)
        )

    return PracticeTurn(reply=reply, result=result, message_id=msg_id)


async def answer_practice(
    message: Message,
    repo: Repository,
    practice: PracticeService,
    settings: Settings,
    text: str,
    *,
    prefix: str = "",
    reply_markup=None,
    profile_service: ProfileService | None = None,
    lesson_id: int | None = None,
) -> None:
    """Запускает практику и сама отвечает пользователю, обрабатывая ошибки LLM.

    Удобный путь для хэндлеров, которым не нужен PracticeTurn (например, текст).
    """
    try:
        turn = await run_practice(
            message,
            repo,
            practice,
            settings,
            text,
            prefix=prefix,
            profile_service=profile_service,
            lesson_id=lesson_id,
        )
    except PracticeParseError as exc:
        logger.warning("Не удалось разобрать ответ LLM: %s", exc)
        await message.answer("🤔 Не смог разобрать ответ модели. Попробуй сформулировать ещё раз.")
        return
    except Exception as exc:
        logger.exception("Ошибка при обращении к LLM: %s", exc)
        await message.answer(
            "⚠️ Что-то пошло не так при обращении к модели. "
            "Попробуй ещё раз через пару минут."
        )
        return
    await message.answer(turn.reply, reply_markup=practice_markup(turn.result, reply_markup, turn.message_id))


@router.callback_query(F.data == "practice:reveal")
@router.callback_query(F.data.startswith("practice:reveal:"))
async def cb_practice_reveal(callback: CallbackQuery, repo: Repository) -> None:
    """Кнопка «Показать ошибку»: разбор конкретной фразы (без id — последней)."""
    try:
        user = await repo.get_or_create_user(
            callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
        )
        parts = callback.data.split(":")
        message_id = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 0
        if message_id:
            correction = await repo.get_user_message(user.id, message_id)
        else:
            correction = await repo.get_last_correction(user.id)
        if not correction:
            try:
                await callback.answer("Нет ошибок")
            except Exception:
                pass
            return

        issues: list[dict] = []
        if correction.get("issues_json"):
            try:
                parsed = json.loads(correction["issues_json"])
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                issues = [i for i in parsed if isinstance(i, dict)]

        try:
            await callback.answer()
        except Exception:
            pass
        await callback.message.answer(format_reveal(correction.get("corrected_text", ""), issues))
    except Exception:
        try:
            await callback.answer("Устарело, отправь фразу заново")
        except Exception:
            pass
