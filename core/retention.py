"""Фаза 9 — Удержание.

Анализирует слабые темы и время последней практики,
чтобы сформировать персонализированное напоминание.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from storage.repo import Repository


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


def _get_streak_days(notes_created_at: list[str]) -> int:
    """Считает серию дней подряд (streak) по timestamps уроков."""
    if not notes_created_at:
        return 0

    dates = []
    for ts in notes_created_at:
        dt = _parse_created_at(ts)
        if dt:
            dates.append(dt.date())

    if not dates:
        return 0

    dates = sorted(set(dates), reverse=True)
    today = datetime.now(timezone.utc).date()

    if dates[0] != today and dates[0] != today - timedelta(days=1):
        return 0

    streak = 1
    for i in range(len(dates) - 1):
        if dates[i] - dates[i + 1] == timedelta(days=1):
            streak += 1
        else:
            break

    return streak


def _get_weak_areas(notes: list) -> list[str]:
    """Извлекает слабые темы из последних уроков, считая частоту."""
    from collections import Counter

    all_areas: list[str] = []
    for note in notes:
        if hasattr(note, "mistakes") and note.mistakes:
            for area in note.mistakes.split(","):
                area = area.strip()
                if area:
                    all_areas.append(area)

    counter = Counter(all_areas)
    return [area for area, count in counter.most_common(5)]


class RetentionService:
    """Собирает данные для персонализированных напоминаний."""

    def __init__(self, repo: Repository):
        self._repo = repo

    async def get_retention_info(self, user_id: int) -> RetentionInfo:
        """Собирает информацию для напоминания."""
        notes = await self._repo.get_lesson_notes(user_id, limit=10)
        profile = await self._repo.get_profile(user_id)

        weak_areas = _get_weak_areas(notes) if notes else []
        recent_topics = [n.topic for n in notes[:3] if n.topic] if notes else []

        last_practice_hours = None
        if notes and notes[0].created_at:
            dt = _parse_created_at(notes[0].created_at)
            if dt:
                delta = datetime.now(timezone.utc) - dt
                last_practice_hours = int(delta.total_seconds() // 3600)

        streak = _get_streak_days([n.created_at for n in notes]) if notes else 0

        return RetentionInfo(
            last_practice_hours=last_practice_hours,
            weak_areas=weak_areas,
            recent_topics=recent_topics,
            total_lessons=len(notes),
            streak_days=streak,
        )
