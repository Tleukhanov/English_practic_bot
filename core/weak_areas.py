"""Weak Areas Service — таргетированная практика по слабым местам (Фаза 13).

Отслеживает ошибки пользователя, приоритизирует слабые области,
постепенно затухает по мере улучшения. Интегрируется с practice prompt.
"""

from __future__ import annotations

from datetime import datetime, timezone

from storage.repo import WeakArea


class WeakAreaService:
    """Сервис управления слабыми областями."""

    DECAY_DAYS = 14  # после стольких дней без ошибки — deprioritize
    REMOVAL_THRESHOLD = 5  # correct_count >= 5 И last_seen > DECAY_DAYS → удалить
    PROMPT_MAX_AREAS = 3  # сколько областей показывать в промпте

    def __init__(self, repo) -> None:
        self._repo = repo

    async def get_weak_areas(self, user_id: int) -> list[WeakArea]:
        """Возвращает все weak areas пользователя, отсортированные по приоритету."""
        return await self._repo.get_weak_areas(user_id)

    async def get_top_for_prompt(self, user_id: int) -> str:
        """Возвращает строку для инжекта в practice prompt (топ-3 области)."""
        areas = await self.get_weak_areas(user_id)
        if not areas:
            return ""
        top = areas[: self.PROMPT_MAX_AREAS]
        lines = []
        for a in top:
            ratio = f"{a.correct_count}/{a.incorrect_count + a.correct_count}"
            lines.append(f"- {a.area} (правильно: {ratio})")
        return "Student weak areas (ask about these): " + "; ".join(
            f"{a.area} (practiced correctly {a.correct_count}/{a.incorrect_count + a.correct_count} times)"
            for a in top
        )

    async def update_from_practice(
        self, user_id: int, issues: list, is_correct: bool, corrected_text: str = ""
    ) -> None:
        """Обновляет weak areas после practice-хода.

        issues — список Issue(dataclass) с полем category.
        Если есть ошибки — создаёт/обновляет weak areas.
        Если ответ правильный — проверяет, улучшился ли пользователь.
        """
        now = datetime.now(timezone.utc).isoformat()

        if issues:
            for issue in issues:
                area = self._normalize_area(issue)
                if area:
                    await self._repo.upsert_weak_area(
                        user_id, area, incorrect_increment=1, last_seen=now
                    )
        elif is_correct:
            existing = await self._repo.get_weak_areas(user_id)
            for wa in existing:
                if self._matches_answer(wa.area, corrected_text):
                    await self._repo.upsert_weak_area(
                        user_id, wa.area, correct_increment=1, last_seen=now
                    )

    async def decay(self, user_id: int) -> None:
        """Удаляет старые weak areas, которые пользователь давно не ошибался."""
        areas = await self._repo.get_weak_areas(user_id)
        now = datetime.now(timezone.utc)
        for area in areas:
            try:
                last = datetime.fromisoformat(area.last_seen.replace("Z", "+00:00"))
                days_since = (now - last).total_seconds() / 86400
            except (ValueError, TypeError):
                continue
            if area.correct_count >= self.REMOVAL_THRESHOLD and days_since > self.DECAY_DAYS:
                await self._repo.delete_weak_area(user_id, area.area)

    def _normalize_area(self, issue) -> str:
        """Нормализует категорию ошибки в читаемую область."""
        cat = getattr(issue, "category", "") or ""
        cat = cat.strip().lower()
        mapping = {
            "grammar": "grammar",
            "vocabulary": "vocabulary",
            "pronunciation": "pronunciation",
            "style": "style",
            "word_order": "word order",
        }
        return mapping.get(cat, cat)

    def _matches_answer(self, area: str, text: str) -> bool:
        """Проверяет, связан ли ответ с известной weak area."""
        if not text:
            return False
        area_lower = area.lower()
        text_lower = text.lower()
        keywords = {
            "grammar": ["did", "was", "were", "have", "has", "had", "go", "went"],
        }
        for key, words in keywords.items():
            if key in area_lower:
                return any(w in text_lower for w in words)
        return False
