"""Точка входа бота.

Запуск: python -m bot.main
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from core.diagnostic import DiagnosticService
from core.lessons import LessonService
from core.practice import PracticeService
from core.profile import ProfileService
from providers import create_llm, create_stt, create_tts
from storage.sqlite import SQLiteRepository

from .config import get_settings
from .diagnostic import router as diagnostic_router
from .flow import router as practice_router
from .handlers import menu, profile, start, text, voice
from .lessons import router as lessons_router

logger = logging.getLogger(__name__)

COMMANDS = [
    BotCommand(command="start", description="Начать практику"),
    BotCommand(command="lesson", description="Структурированный урок"),
    BotCommand(command="diagnostic", description="🎯 Определить уровень"),
    BotCommand(command="stats", description="Моя статистика"),
    BotCommand(command="profile", description="🧠 Мой профиль"),
    BotCommand(command="help", description="Помощь"),
]


async def main() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN не задан в .env")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    if not settings.llm_ready:
        logger.warning(
            "LLM не настроен полностью: LLM_PROVIDER=%s, LLM_API_KEY пуст. "
            "Практика начнёт работать после заполнения .env.",
            settings.llm_provider,
        )

    repo = SQLiteRepository(settings.database_path)
    await repo.connect()

    llm = create_llm(settings)
    stt = create_stt(settings)
    tts = create_tts(settings)
    practice = PracticeService(llm, max_history=settings.max_context_messages)
    lessons = LessonService(llm)
    diagnostic = DiagnosticService(llm)
    profile_service = ProfileService(llm)

    bot = Bot(
        settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp["repo"] = repo
    dp["practice"] = practice
    dp["lesson_service"] = lessons
    dp["diagnostic_service"] = diagnostic
    dp["profile_service"] = profile_service
    dp["stt"] = stt
    dp["tts"] = tts
    dp["settings"] = settings

    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(profile.router)
    dp.include_router(practice_router)
    dp.include_router(lessons_router)
    dp.include_router(diagnostic_router)
    dp.include_router(text.router)
    dp.include_router(voice.router)

    await bot.set_my_commands(COMMANDS)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await repo.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
