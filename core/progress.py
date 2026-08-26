"""Фаза 10 — Прогресс.

Агрегирует данные о прогрессе пользователя: уровень, статистику,
слабые темы, серию дней (streak), XP.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import Counter

from storage.repo import Repository


@dataclass
class ProgressData:
    """Полная статистика прогресса пользователя."""

    level: str = "—"
    total_lessons: int = 0
    total_turns: int = 0
    correct: int = 0
    errors: int = 0
    accuracy: float = 0.0
    weak_areas: list[str] = field(default_factory=list)
    strong_areas: list[str] = field(default_factory=list)
    streak_days: int = 0
    xp: int = 0
    character: str = "default"
    interests: str = ""


class ProgressService:
    """Собирает данные прогресса из разных источников."""

    def __init__(self, repo: Repository):
        self._repo = repo

    async def get_progress(self, user_id: int) -> ProgressData:
        """Собирает полную статистику прогресса."""
        profile = await self._repo.get_profile(user_id)
        stats = await self._repo.get_stats(user_id)
        notes = await self._repo.get_lesson_notes(user_id, limit=50)
        practice_dates = await self._repo.get_practice_dates(user_id, limit=50)

        level = ""
        character = profile.character if profile and profile.character else "default"
        interests = profile.interests if profile and profile.interests else ""

        total_lessons = len(notes)
        total_turns = stats.total_turns
        correct = stats.correct
        errors = stats.errors
        accuracy = (correct / total_turns * 100) if total_turns > 0 else 0.0

        weak_areas = self._get_weak_areas(notes)
        strong_areas = self._get_strong_areas(notes)

        streak_days = self._get_streak(notes, practice_dates)

        xp = self._calculate_xp(total_lessons, correct, errors)

        return ProgressData(
            level=level,
            total_lessons=total_lessons,
            total_turns=total_turns,
            correct=correct,
            errors=errors,
            accuracy=accuracy,
            weak_areas=weak_areas,
            strong_areas=strong_areas,
            streak_days=streak_days,
            xp=xp,
            character=character,
            interests=interests,
        )

    @staticmethod
    def _get_weak_areas(notes: list) -> list[str]:
        """Извлекает слабые темы из последних уроков по частоте."""
        if not notes:
            return []

        all_areas: list[str] = []
        for note in notes:
            if hasattr(note, "mistakes") and note.mistakes:
                for area in note.mistakes.split(","):
                    area = area.strip()
                    if area:
                        all_areas.append(area)

        counter = Counter(all_areas)
        return [area for area, _ in counter.most_common(5)]

    @staticmethod
    def _get_strong_areas(notes: list) -> list[str]:
        """Извлекает сильные темы (topics без ошибок)."""
        if not notes:
            return []

        topics_with_mistakes = set()
        topics_without_mistakes = set()

        for note in notes:
            if note.topic:
                if note.mistakes and note.mistakes.strip():
                    topics_with_mistakes.add(note.topic)
                else:
                    topics_without_mistakes.add(note.topic)

        return list(topics_without_mistakes - topics_with_mistakes)[:5]

    @staticmethod
    def _get_streak(notes: list, practice_dates: list[str] | None = None) -> int:
        """Считает серию дней подряд из lesson_notes + practice dates (messages)."""
        from datetime import datetime, timezone, timedelta

        dates_set: set = set()

        for note in notes:
            if note.created_at:
                try:
                    dt = datetime.fromisoformat(note.created_at.replace("Z", "+00:00"))
                    dates_set.add(dt.date())
                except (ValueError, TypeError):
                    continue

        if practice_dates:
            for day_str in practice_dates:
                try:
                    dates_set.add(datetime.strptime(day_str, "%Y-%m-%d").date())
                except (ValueError, TypeError):
                    continue

        if not dates_set:
            return 0

        dates = sorted(dates_set, reverse=True)
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

    @staticmethod
    def _calculate_xp(total_lessons: int, correct: int, errors: int) -> int:
        """Простая XP-система: +10 за урок, +5 за правильную реплику, -2 за ошибку."""
        xp = 0
        xp += total_lessons * 10
        xp += correct * 5
        xp -= errors * 2
        return max(xp, 0)


def format_progress(p: ProgressData) -> str:
    """Форматирует прогресс в красивое сообщение."""
    level_emoji = {"A1": "🟢", "A2": "🟢", "B1": "🟡", "B2": "🟡", "C1": "🔴", "C2": "🔴"}
    emoji = level_emoji.get(p.level, "⚪")

    lines = [f"📊 <b>Твой прогресс</b>  {emoji} {p.level}", ""]

    lines.append(f"📚 Уроков: {p.total_lessons}")
    lines.append(f"✍️ Реплик: {p.total_turns}  ✅ {p.correct}  ❌ {p.errors}")
    lines.append(f"🎯 Точность: {p.accuracy:.0f}%")
    lines.append(f"⭐ XP: {p.xp}")
    lines.append(f"🔥 Серия: {p.streak_days} дн.")

    if p.weak_areas:
        lines.append("")
        lines.append("📝 Слабые темы: " + ", ".join(p.weak_areas))

    if p.strong_areas:
        lines.append("💪 Сильные темы: " + ", ".join(p.strong_areas))

    if p.character and p.character != "default":
        lines.append("")
        lines.append(f"🎭 Персонаж: {p.character}")

    if p.interests:
        lines.append(f"🎯 Интересы: {p.interests}")

    return "\n".join(lines)
