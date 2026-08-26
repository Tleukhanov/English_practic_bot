"""SRS Service — Spaced Repetition для словаря (Фаза 13).

Алгоритм SM-2 (упрощённый): каждое слово имеет интервал повторения,
который растёт при правильных ответах и сбрасывается при ошибках.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass
class SRSWord:
    """Слово в системе SRS."""

    id: int = 0
    user_id: int = 0
    word: str = ""
    translation: str = ""
    example: str = ""
    lesson_id: int = 0
    next_review: str = ""
    interval_days: int = 1
    ease_factor: float = 2.5
    correct_count: int = 0
    last_reviewed: str = ""
    created_at: str = ""


class SRSService:
    """Сервис spaced repetition для словаря."""

    MIN_EASE = 1.3
    MAX_INTERVAL_DAYS = 365

    def __init__(self, repo) -> None:
        self._repo = repo

    async def add_words(
        self, user_id: int, words: list[dict], lesson_id: int = 0
    ) -> int:
        """Добавляет слова из урока в SRS. Возвращает количество добавленных."""
        now = datetime.now(timezone.utc).isoformat()
        count = 0
        for w in words:
            word = str(w.get("word", "")).strip()
            translation = str(w.get("translation", "")).strip()
            example = str(w.get("example", "")).strip()
            if not word:
                continue
            existing = await self._repo.get_srs_word(user_id, word)
            if existing:
                continue
            await self._repo.add_srs_word(SRSWord(
                user_id=user_id, word=word, translation=translation,
                example=example, lesson_id=lesson_id,
                next_review=now, interval_days=1, ease_factor=2.5,
                created_at=now,
            ))
            count += 1
        return count

    async def get_due_words(self, user_id: int, limit: int = 10) -> list[SRSWord]:
        """Возвращает слова, готовые к повторению."""
        now = datetime.now(timezone.utc).isoformat()
        words = await self._repo.get_srs_words(user_id, limit=100)
        due = [w for w in words if w.next_review <= now]
        due.sort(key=lambda w: w.next_review)
        return due[:limit]

    async def review(self, word_id: int, quality: int) -> SRSWord | None:
        """Обновляет интервал слова по SM-2.

        quality: 0-5 (0=не помню, 5=легко вспомнил).
        """
        word = await self._repo.get_srs_word_by_id(word_id)
        if not word:
            return None

        now = datetime.now(timezone.utc)
        word.last_reviewed = now.isoformat()

        if quality >= 3:
            word.correct_count += 1
            if word.correct_count == 1:
                word.interval_days = 1
            elif word.correct_count == 2:
                word.interval_days = 6
            else:
                word.interval_days = min(
                    int(word.interval_days * word.ease_factor),
                    self.MAX_INTERVAL_DAYS,
                )
            word.ease_factor = max(
                self.MIN_EASE,
                word.ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)),
            )
        else:
            word.correct_count = 0
            word.interval_days = 1
            word.ease_factor = max(self.MIN_EASE, word.ease_factor - 0.2)

        word.next_review = (now + timedelta(days=word.interval_days)).isoformat()
        await self._repo.update_srs_word(word)
        return word

    async def get_stats(self, user_id: int) -> dict:
        """Возвращает статистику SRS для пользователя."""
        words = await self._repo.get_srs_words(user_id, limit=10000)
        now = datetime.now(timezone.utc).isoformat()
        due = sum(1 for w in words if w.next_review <= now)
        learned = sum(1 for w in words if w.correct_count >= 3)
        return {
            "total": len(words),
            "due": due,
            "learned": learned,
            "new": len(words) - learned,
        }
