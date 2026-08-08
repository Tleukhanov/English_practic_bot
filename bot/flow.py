"""Общая логика одной «практики» — используется текстовым и голосовым хэндлерами."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from aiogram.types import Message

from bot.config import Settings
from core.models import PracticeResult
from core.practice import PracticeParseError, PracticeService
from storage.repo import Repository, UserRow

from .formatters import format_practice_result

logger = logging.getLogger(__name__)


@dataclass
class PracticeTurn:
    reply: str  # готовый HTML-ответ для пользователя
    result: PracticeResult  # структурированный результат (нужен для TTS)


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


async def get_or_create_user(message: Message, repo: Repository) -> UserRow:
    return await repo.get_or_create_user(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )


async def run_practice(
    message: Message,
    repo: Repository,
    practice: PracticeService,
    settings: Settings,
    text: str,
    *,
    prefix: str = "",
) -> PracticeTurn:
    """Проводит практику по переданному тексту, сохраняет в БД и возвращает ответ.

    Поднимает исключение при сбое LLM — хэндлер решает, что показать пользователю.
    """
    user = await get_or_create_user(message, repo)
    history = await repo.get_history(user.id, settings.max_context_messages)

    await message.bot.send_chat_action(message.chat.id, action="typing")
    result = await practice.analyze(text, history)

    await repo.add_user_message(
        user.id,
        text,
        is_correct=result.is_correct,
        issues_json=issues_to_json(result),
        corrected_text=result.corrected_text,
    )

    reply = format_practice_result(result, html=True)
    if prefix:
        reply = f"{prefix}\n\n{reply}"
    await repo.add_assistant_message(user.id, format_practice_result(result, html=False))
    return PracticeTurn(reply=reply, result=result)


async def answer_practice(
    message: Message,
    repo: Repository,
    practice: PracticeService,
    settings: Settings,
    text: str,
    *,
    prefix: str = "",
    reply_markup=None,
) -> None:
    """Запускает практику и сама отвечает пользователю, обрабатывая ошибки LLM.

    Удобный путь для хэндлеров, которым не нужен PracticeTurn (например, текст).
    """
    try:
        turn = await run_practice(message, repo, practice, settings, text, prefix=prefix)
    except PracticeParseError as exc:
        logger.warning("Не удалось разобрать ответ LLM: %s", exc)
        await message.answer("🤔 Не смог разобрать ответ модели. Попробуй сформулировать ещё раз.")
        return
    except Exception as exc:
        logger.exception("Ошибка при обращении к LLM: %s", exc)
        await message.answer(
            "⚠️ Что-то пошло не так при обращении к модели. "
            "Проверь LLM_API_KEY и LLM_PROVIDER в .env и попробуй ещё раз."
        )
        return
    await message.answer(turn.reply, reply_markup=reply_markup)
