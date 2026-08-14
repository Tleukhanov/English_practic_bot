"""Текстовая практика: пользователь пишет по-английски, бот проверяет.

Если у пользователя идёт диагностика уровня — сообщение уходит в диагностику.
Если идёт структурированный урок — сообщение уходит в урок.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import Message

from bot.config import Settings
from core.diagnostic import DiagnosticService
from core.practice import PracticeService
from core.profile import ProfileService
from storage.repo import Repository

from ..diagnostic import process_diagnostic_answer
from ..flow import answer_practice, get_or_create_user
from ..keyboards import lesson_keyboard
from ..utils import is_mostly_cyrillic

router = Router()
logger = logging.getLogger(__name__)


@router.message(F.text, ~F.text.startswith("/"))
async def on_text(
    message: Message,
    repo: Repository,
    practice: PracticeService,
    diagnostic_service: DiagnosticService,
    profile_service: ProfileService,
    settings: Settings,
) -> None:
    text = message.text.strip()

    if is_mostly_cyrillic(text):
        await message.answer("😉 Пиши, пожалуйста, по-английски! Я репетитор английского и отвечаю на английском.")
        return

    user = await get_or_create_user(message, repo)
    if await process_diagnostic_answer(message, repo, diagnostic_service, text):
        return

    session = await repo.get_active_lesson(user.id)
    if session is not None:
        await answer_practice(
            message, repo, practice, settings, text,
            reply_markup=lesson_keyboard(), profile_service=profile_service,
        )
        return

    await answer_practice(message, repo, practice, settings, text, profile_service=profile_service)
