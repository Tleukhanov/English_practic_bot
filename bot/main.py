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
from core.lesson_notes import LessonNoteService
from core.lessons import LessonService
from core.practice import PracticeService
from core.profile import ProfileService
from core.srs import SRSService
from providers import create_llm, create_stt, create_tts
from storage.sqlite import SQLiteRepository

from .config import get_settings
from .diagnostic import router as diagnostic_router
from .flow import router as practice_router
from .handlers import menu, profile, start, text, voice
from .handlers.character import router as character_router
from .handlers.interests import router as interests_router
from .handlers.progress import router as progress_router
from .handlers.achievements import router as achievements_router
from .handlers.review import router as review_router
from .handlers.onboarding import router as onboarding_router
from .handlers.leaderboard import router as leaderboard_router
from .lessons import router as lessons_router

logger = logging.getLogger(__name__)

COMMANDS = [
    BotCommand(command="start", description="Начать практику"),
    BotCommand(command="lesson", description="Структурированный урок"),
    BotCommand(command="character", description="🎭 Выбрать персонажа"),
    BotCommand(command="interests", description="🎯 Мои интересы"),
    BotCommand(command="diagnostic", description="🎯 Определить уровень"),
    BotCommand(command="review", description="📚 Повторить слова"),
    BotCommand(command="stats", description="Моя статистика"),
    BotCommand(command="progress", description="📊 Мой прогресс"),
    BotCommand(command="achievements", description="🎮 Достижения"),
    BotCommand(command="leaderboard", description="🏅 Рейтинг"),
    BotCommand(command="reset", description="🔄 Сбросить состояние"),
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
    note_service = LessonNoteService(llm)
    srs_service = SRSService(repo)

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
    dp["note_service"] = note_service
    dp["srs"] = srs_service
    dp["stt"] = stt
    dp["tts"] = tts
    dp["settings"] = settings

    dp.include_router(onboarding_router)
    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(character_router)
    dp.include_router(interests_router)
    dp.include_router(progress_router)
    dp.include_router(achievements_router)
    dp.include_router(leaderboard_router)
    dp.include_router(profile.router)
    dp.include_router(practice_router)
    dp.include_router(lessons_router)
    dp.include_router(diagnostic_router)
    dp.include_router(review_router)
    dp.include_router(text.router)
    dp.include_router(voice.router)

    from aiogram.types import ErrorEvent
    @dp.error()
    async def global_error_handler(event: ErrorEvent) -> None:
        logger.exception("Unhandled error: %s", event.exception)
        try:
            if hasattr(event.update, "message") and event.update.message:
                await event.update.message.answer(
                    "⚠️ Произошла ошибка. Попробуй ещё раз или нажми /start."
                )
            elif hasattr(event.update, "callback_query") and event.update.callback_query:
                await event.update.callback_query.message.answer(
                    "⚠️ Произошла ошибка. Попробуй ещё раз или нажми /start."
                )
        except Exception:
            pass

    await bot.set_my_commands(COMMANDS)

    from core.scheduler import setup_scheduler
    scheduler = setup_scheduler(bot, repo, interval_hours=24)
    scheduler.start()
    logger.info("Scheduler started: reminders every %d hours", 24)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await repo.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
