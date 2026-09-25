"""Дневная квота LLM для тестирования.

QuotaGuard обеспечивает двухшаговый контроль квоты::

    await quota.check(user_id)     # бросит QuotaExceeded, если бюджета нет
    result = await llm_call(...)   # сам LLM-вызов
    await quota.consume(user_id)   # списание только после успешного вызова

``check`` — предпроверка без мутаций, ``consume`` — атомарное billed-списание.
Счётчик дневной квоты НИКОГДА не превышает daily_limit даже при конкурентных
сообщениях: списание идёт условным UPDATE `... WHERE count + ? <= limit`, а при
rowcount == 0 ``consume`` бросает QuotaExceeded (устраняет TOCTOU).
Метод ``consume`` эффективно бездействует для unlimited/subscription-active.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from core.analytics import track_event
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
        # Сериализует multi-step списание (extra_actions -> daily) в рамках
        # процесса; атомарный UPDATE в БД дополнительно защищает счётчик.
        self._lock = asyncio.Lock()

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).date().isoformat()

    async def check(self, user_id: int) -> None:
        """Проверяет, есть ли у пользователя бюджет. Бросает QuotaExceeded если нет.

        Не мутирует ничего — просто предпроверка. Окончательный атомарный
        контроль делает consume().
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
        await track_event(self._repo, user_id, "quota_hit")
        raise QuotaExceeded(f"квота исчерпана: {used}/{self._daily_limit}")

    async def _try_charge_daily(self, user_id: int, day: str, amount: int) -> bool:
        """Атомарно увеличивает дневной счётчик, если он не превысит лимит.

        SQLite-путь: условный UPDATE `count + amount <= limit`, rowcount == 0
        означает, что списать нельзя. Для хранилищ без прямого доступа к SQL —
        read-modify-write под локом процесса (не атомарно в БД, но корректно
        для однопроцессного бота).
        """
        require_conn = getattr(self._repo, "_require_conn", None)
        if require_conn is None:
            used = await self._repo.get_llm_usage(user_id, day)
            if used + amount > self._daily_limit:
                return False
            await self._repo.increment_llm_usage(user_id, day, amount)
            return True
        conn = require_conn()
        await conn.execute(
            "INSERT OR IGNORE INTO llm_usage (user_id, day, count) VALUES (?, ?, 0)",
            (user_id, day),
        )
        cursor = await conn.execute(
            "UPDATE llm_usage SET count = count + ? "
            "WHERE user_id = ? AND day = ? AND count + ? <= ?",
            (amount, user_id, day, amount, self._daily_limit),
        )
        await conn.commit()
        return cursor.rowcount > 0

    async def consume(self, user_id: int, *, cost: int = 1) -> None:
        """Списывает cost единиц квоты. Бросает QuotaExceeded, если списание
        превысило бы дневной лимит.

        Для unlimited/subscription-active — no-op (всё ещё бесплатно).
        Биллинг: extra_actions тратятся первыми, остаток идёт в daily usage.
        Списание атомарно: счётчик никогда не превышает daily_limit.
        """
        if self._daily_limit <= 0:
            return
        if await self._repo.get_unlimited_status(user_id):
            return
        sub = await self._repo.get_subscription(user_id)
        if sub and sub.is_active:
            return
        async with self._lock:
            extra = await self._repo.get_extra_actions(user_id)
            extra_used = min(extra, cost)
            daily_used = cost - extra_used
            if daily_used > 0:
                if not await self._try_charge_daily(user_id, self._today(), daily_used):
                    await track_event(self._repo, user_id, "quota_hit")
                    raise QuotaExceeded(
                        f"квота исчерпана: нельзя списать {cost} "
                        f"(лимит {self._daily_limit}/день)"
                    )
            if extra_used > 0:
                await self._repo.decrement_extra_actions(user_id, extra_used)