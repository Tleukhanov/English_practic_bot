"""Текстовая практика: пользователь пишет по-английски, бот проверяет.

Если у пользователя идёт диагностика уровня — сообщение уходит в диагностику.
Если идёт структурированный урок — сообщение уходит в урок.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.config import Settings
from core.diagnostic import DiagnosticService
from core.practice import PracticeService
from core.profile import ProfileService
from storage.repo import Repository

from core.lessons import LESSON_STEPS
from ..diagnostic import process_diagnostic_answer
from ..flow import answer_practice, get_or_create_user
from ..keyboards import lesson_keyboard, lesson_recap_keyboard
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
    state: FSMContext,
) -> None:
    text = message.text.strip()

    current_state = await state.get_state()
    if current_state and "ReviewState" in current_state:
        return

    if is_mostly_cyrillic(text):
        await message.answer("😉 Пиши, пожалуйста, по-английски! Я репетитор английского и отвечаю на английском.")
        return

    user = await get_or_create_user(message, repo)
    if await process_diagnostic_answer(message, repo, diagnostic_service, text):
        return

    session = await repo.get_active_lesson(user.id)
    if session is not None:
        if session.updated_at:
            from datetime import datetime, timezone
            try:
                updated = datetime.fromisoformat(session.updated_at.replace("Z", "+00:00"))
                age_hours = (datetime.now(timezone.utc) - updated).total_seconds() / 3600
                if age_hours > 1:
                    await repo.abort_active_lessons(user.id)
                    await message.answer(
                        "⏰ Урок устарел (прошло больше часа) и был завершён.\n"
                        "Начни новый: /lesson",
                    )
                    session = None
            except (ValueError, TypeError):
                pass

    if session is not None:
        kb = lesson_recap_keyboard() if LESSON_STEPS[session.step] == "recap" else lesson_keyboard()
        await answer_practice(
            message, repo, practice, settings, text,
            reply_markup=kb, profile_service=profile_service, lesson_id=session.id,
        )
        return

    await answer_practice(message, repo, practice, settings, text, profile_service=profile_service)
