"""Текстовая практика: пользователь пишет по-английски, бот проверяет."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import Message

from bot.config import Settings
from core.practice import PracticeParseError, PracticeService
from storage.repo import Repository

from ..flow import run_practice
from ..utils import is_mostly_cyrillic

router = Router()
logger = logging.getLogger(__name__)


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

    try:
        reply = await run_practice(message, repo, practice, settings, text)
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

    await message.answer(reply)
