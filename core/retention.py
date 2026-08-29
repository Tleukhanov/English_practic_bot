"""Фаза 9 — Удержание.

Анализирует слабые темы и время последней практики,
чтобы сформировать персонализированное напоминание.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from storage.repo import Repository

from .progress import ProgressService


@dataclass
class RetentionInfo:
    """Информация для формирования напоминания."""

    last_practice_hours: int | None = None
    weak_areas: list[str] | None = None
    recent_topics: list[str] | None = None
    total_lessons: int = 0
    streak_days: int = 0


def _parse_created_at(created_at: str | None) -> datetime | None:
    """Парсит created_at из SQLite (ISO format)."""
    if not created_at:
        return None
    try:
        return datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


class RetentionService:
    """Собирает данные для персонализированных напоминаний."""

    def __init__(self, repo: Repository):
        self._repo = repo

    async def get_retention_info(self, user_id: int) -> RetentionInfo:
        """Собирает информацию для напоминания."""
        notes = await self._repo.get_lesson_notes(user_id, limit=10)
        practice_dates = await self._repo.get_practice_dates(user_id, limit=50)

        weak_areas = ProgressService._get_weak_areas(notes) if notes else []
        recent_topics = [n.topic for n in notes[:3] if n.topic] if notes else []

        # Активность считаем по ВСЕМ действиям (реплики свободной практики +
        # завершённые уроки), иначе тот, кто каждый день пишет в чат, никогда
        # не получит напоминание — last_practice_hours будет None.
        last_practice_hours = None
        last_activity = await self._repo.get_last_activity(user_id)
        dt = _parse_created_at(last_activity) if last_activity else None
        if dt is None and notes and notes[0].created_at:
            dt = _parse_created_at(notes[0].created_at)
        if dt:
            delta = datetime.now(timezone.utc) - dt
            last_practice_hours = int(delta.total_seconds() // 3600)

        streak = ProgressService._get_streak(notes, practice_dates) if notes else 0

        return RetentionInfo(
            last_practice_hours=last_practice_hours,
            weak_areas=weak_areas,
            recent_topics=recent_topics,
            total_lessons=len(notes),
            streak_days=streak,
        )
