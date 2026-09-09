"""Фаза 11 — Напоминания по расписанию (APScheduler).

Каждые 24 часа проверяет пользователей без практики
и отправляет персонализированное напоминание.
"""

from __future__ import annotations

import html
import logging
from datetime import datetime, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from core.retention import RetentionService
from storage.repo import Repository


class ReminderDedupe:
    """Tracks users already reminded today to avoid duplicate messages.

    Resets automatically when the UTC date changes.
    """

    def __init__(self) -> None:
        self._reminded: dict[int, str] = {}
        self._date: str | None = None

    def should_send(self, user_id: int, expires_at: str) -> bool:
        today = datetime.now(timezone.utc).date().isoformat()
        if self._date != today:
            self._reminded.clear()
            self._date = today
        if self._reminded.get(user_id) == expires_at:
            return False
        self._reminded[user_id] = expires_at
        return True

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
            name = html.escape(user.first_name or "друг")
            message = _build_reminder_message(name, info)

            if message:
                await bot.send_message(user.tg_id, message)
                sent += 1
                logger.info("Reminder sent to user %s", user.tg_id)
        except Exception:
            logger.warning("Failed to send reminder to user %s", user.tg_id, exc_info=True)

    logger.info("Reminders sent: %d / %d users", sent, len(users))


async def reminder_wheel_misses(bot: Bot, repo: Repository) -> None:
    """Напоминает пользователям о неиспользованной крутке Колеса удачи."""
    users = await repo.get_all_users()
    today = datetime.now(timezone.utc).date().isoformat()
    sent = 0
    for user in users:
        try:
            last_spin = await repo.get_last_spin_date(user.id)
            if last_spin == today:
                continue
            text = "🎡 У тебя сегодня неиспользованная крутка удачи! Загляни: /wheel"
            await bot.send_message(user.tg_id, text)
            sent += 1
            logger.info("Wheel reminder sent to user %s", user.tg_id)
        except Exception:
            logger.warning("Failed to send wheel reminder to user %s", user.tg_id, exc_info=True)
    logger.info("Wheel reminders sent: %d / %d users", sent, len(users))


_expiry_reminder_dedupe = ReminderDedupe()


def _build_expiry_message(expires_at_str: str, days: int) -> str:
    """Строит текст напоминания об истечении подписки."""
    try:
        expires = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        expires = None
    date = expires.date().isoformat() if expires else expires_at_str
    return (
        f"⏳ Твоя подписка истекает завтра ({date}).\n"
        f"Текущий план: {days} дн. Продлить: /premium"
    )


async def subscription_expiry_reminders(bot: Bot, repo: Repository) -> None:
    """Предупреждает пользователей об истечении подписки в ближайшие 24 часа."""
    users = await repo.get_all_users()
    now = datetime.now(timezone.utc)
    sent = 0
    for user in users:
        try:
            sub = await repo.get_subscription(user.id)
            if sub is None or not sub.is_active or not sub.expires_at:
                continue
            expires = datetime.fromisoformat(sub.expires_at.replace("Z", "+00:00"))
            if expires <= now or (expires - now).total_seconds() > 86400:
                continue
            if not _expiry_reminder_dedupe.should_send(user.id, sub.expires_at):
                continue
            text = _build_expiry_message(sub.expires_at, sub.plan_days)
            await bot.send_message(user.tg_id, text)
            sent += 1
            logger.info("Expiry reminder sent to user %s", user.tg_id)
        except Exception:
            logger.warning("Failed to send expiry reminder to user %s", user.tg_id, exc_info=True)
    logger.info("Expiry reminders sent: %d / %d users", sent, len(users))


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
    scheduler.add_job(
        reminder_wheel_misses,
        trigger=IntervalTrigger(hours=interval_hours),
        args=[bot, repo],
        id="reminder_wheel_misses",
        replace_existing=True,
    )
    scheduler.add_job(
        subscription_expiry_reminders,
        trigger=IntervalTrigger(hours=interval_hours),
        args=[bot, repo],
        id="subscription_expiry_reminders",
        replace_existing=True,
    )
    return scheduler
