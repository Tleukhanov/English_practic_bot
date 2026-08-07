"""Текстовая практика: пользователь пишет по-английски, бот проверяет."""

from __future__ import annotations

import json
import logging

from aiogram import F, Router
from aiogram.types import Message

from bot.config import Settings
from core.practice import PracticeParseError, PracticeService
from storage.repo import Repository

from ..formatters import format_practice_result
from ..utils import is_mostly_cyrillic

router = Router()
logger = logging.getLogger(__name__)


def _issues_to_json(result) -> str:
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


@router.message(F.text, ~F.text.startswith("/"))
async def on_text(
    message: Message,
    repo: Repository,
    practice: PracticeService,
    settings: Settings,
) -> None:
    text = message.text.strip()

    if is_mostly_cyrillic(text):
        await message.answer("😉 Пиши, пожалуйста, по-английски! Я репетитор английского и отвечаю на английском.")
        return

    user = await repo.get_or_create_user(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    history = await repo.get_history(user.id, settings.max_context_messages)

    await message.bot.send_chat_action(message.chat.id, action="typing")
    try:
        result = await practice.analyze(text, history)
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

    await repo.add_user_message(
        user.id,
        text,
        is_correct=result.is_correct,
        issues_json=_issues_to_json(result),
        corrected_text=result.corrected_text,
    )

    reply = format_practice_result(result, html=True)
    await repo.add_assistant_message(user.id, format_practice_result(result, html=False))
    await message.answer(reply)
