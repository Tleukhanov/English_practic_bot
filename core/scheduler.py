"""Фаза 11 — Напоминания по расписанию (APScheduler).

Каждые 24 часа проверяет пользователей без практики
и отправляет персонализированное напоминание.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from core.retention import RetentionService
from storage.repo import Repository

logger = logging.getLogger(__name__)


def _build_reminder_message(name: str, info) -> str | None:
    """Строит текст напоминания для пользователя."""
    if info.last_practice_hours is None:
        return None

    if info.last_practice_hours < 24:
        return None

    weak_line = ""
    if info.weak_areas:
        weak_line = "📝 Твои слабые темы: " + ", ".join(info.weak_areas[:3]) + ".\n"

    streak_line = ""
    if info.streak_days > 1:
        streak_line = f"🔥 Серия: {info.streak_days} дней подряд!\n"

    return (
        f"👋 Привет, {name}!\n\n"
        f"⏰ Ты не занимался уже {info.last_practice_hours}ч.\n"
        f"{weak_line}"
        f"{streak_line}"
        "Хочешь продолжить? Нажми /start"
    )


async def check_and_send_reminders(bot: Bot, repo: Repository) -> None:
    """Проверяет всех пользователей и отправляет напоминания."""
    users = await repo.get_all_users()
    retention_service = RetentionService(repo)

    sent = 0
    for user in users:
        try:
            info = await retention_service.get_retention_info(user.id)
            name = user.first_name or "друг"
            message = _build_reminder_message(name, info)

            if message:
                await bot.send_message(user.tg_id, message)
                sent += 1
                logger.info("Reminder sent to user %s", user.tg_id)
        except Exception:
            logger.warning("Failed to send reminder to user %s", user.tg_id, exc_info=True)

    logger.info("Reminders sent: %d / %d users", sent, len(users))


def setup_scheduler(bot: Bot, repo: Repository, interval_hours: int = 24) -> AsyncIOScheduler:
    """Создаёт и настраивает планировщик напоминаний."""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_and_send_reminders,
        trigger=IntervalTrigger(hours=interval_hours),
        args=[bot, repo],
        id="send_reminders",
        replace_existing=True,
    )
    return scheduler
