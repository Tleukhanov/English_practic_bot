"""Дневная квота LLM для тестирования.

QuotaGuard обеспечивает двухшаговый контроль квоты::

    await quota.check(user_id)     # бросит QuotaExceeded, если бюджета нет
    result = await llm_call(...)   # сам LLM-вызов
    await quota.consume(user_id)   # списание только после успешного вызова

Списание не мутирует бюджет; ``check`` — проверка, ``consume`` — billed.
Метод ``consume`` эффективно бездействует для unlimited/subscription-active.
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

    async def check(self, user_id: int) -> None:
        """Проверяет, есть ли у пользователя бюджет. Бросает QuotaExceeded если нет.

        Не мутирует ничего — просто проверка.
        """
        if self._daily_limit <= 0:
            return
        if await self._repo.get_unlimited_status(user_id):
            return
        sub = await self._repo.get_subscription(user_id)
        if sub and sub.is_active:
            return
        used = await self._repo.get_llm_usage(user_id, self._today())
        if used < self._daily_limit:
            return
        extra = await self._repo.get_extra_actions(user_id)
        if extra > 0:
            return
        raise QuotaExceeded(f"квота исчерпана: {used}/{self._daily_limit}")

    async def consume(self, user_id: int, *, cost: int = 1) -> None:
        """Списывает cost единиц квоты. Не проверяет лимит — вызывай check() заранее.

        Для unlimited/subscription-active — no-op (всё ещё бесплатно).
        Биллинг: extra_actions тратятся первыми, остаток идёт в daily usage.
        """
        if self._daily_limit <= 0:
            return
        if await self._repo.get_unlimited_status(user_id):
            return
        sub = await self._repo.get_subscription(user_id)
        if sub and sub.is_active:
            return
        used = await self._repo.get_llm_usage(user_id, self._today())
        extra = await self._repo.get_extra_actions(user_id)
        extra_used = min(extra, cost)
        if extra_used > 0:
            await self._repo.decrement_extra_actions(user_id, extra_used)
        daily_used = cost - extra_used
        if daily_used > 0:
            await self._repo.increment_llm_usage(user_id, self._today(), daily_used)