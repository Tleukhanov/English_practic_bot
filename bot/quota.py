"""Дневная квота LLM для тестирования.

Идея: тестеры (10-15 человек) могут выжечь лимиты LLM-провайдера за пару дней.
QuotaGuard считает LLM-действия (урок, реплика практики, ответ диагностики) в день
на пользователя. При исчерпании бросает QuotaExceeded — хэндлер отвечает
дружелюбным сообщением. Промокод из .env снимает лимит пользователю навсегда.
"""

from __future__ import annotations

from datetime import datetime, timezone

from storage.repo import Repository

QUOTA_EXCEEDED_TEXT = (
    "⛔️ Дневной лимит использования ИИ исчерпан. Приходи завтра — счётчик сбросится.\n\n"
    "Есть промокод на безлимит? Отправь /promo"
)


class QuotaExceeded(Exception):
    """Дневной лимит LLM-действий пользователя исчерпан."""


class QuotaGuard:
    def __init__(self, repo: Repository, daily_limit: int):
        self._repo = repo
        self._daily_limit = daily_limit

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).date().isoformat()

    async def consume(self, user_id: int, *, cost: int = 1) -> None:
        """Гасит единицу дневной квоты. Бросает QuotaExceeded при исчерпании."""
        if self._daily_limit <= 0:
            return
        if await self._repo.get_unlimited_status(user_id):
            return
        used = await self._repo.get_llm_usage(user_id, self._today())
        if used >= self._daily_limit:
            raise QuotaExceeded(f"kвота исчерпана: {used}/{self._daily_limit}")
        await self._repo.increment_llm_usage(user_id, self._today(), cost)