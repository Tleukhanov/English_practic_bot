"""Колесо удачи: выбор приза, pity-механика и выдача бонусов.

Сервис не зависит от aiogram и ничего не знает о слое бота.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from storage.repo import Repository

# --- идентификаторы секторов -------------------------------------------------

DISCOUNT_10 = "DISCOUNT_10"  # купон -10%
DISCOUNT_20 = "DISCOUNT_20"  # купон -20%
DISCOUNT_30 = "DISCOUNT_30"  # купон -30%
ACTIONS_15 = "ACTIONS_15"  # +15 действий ИИ
ACTIONS_50 = "ACTIONS_50"  # +50 действий ИИ
JACKPOT = "JACKPOT"  # день безлимита
MISS = "MISS"

# --- сектора с весами (публичная константа для легенды) ----------------------

WHEEL_SECTORS: tuple[tuple[str, int], ...] = (
    (DISCOUNT_10, 30),
    (DISCOUNT_20, 18),
    (DISCOUNT_30, 8),
    (ACTIONS_15, 25),
    (ACTIONS_50, 10),
    (JACKPOT, 3),
    (MISS, 6),
)

# большой приз = скидка 20/30%, +50 действий, джекпот
BIG_PRIZES: tuple[str, ...] = (DISCOUNT_20, DISCOUNT_30, ACTIONS_50, JACKPOT)
# приз, который гарантирует pity-счётчик (после сухой серии)
BIG_PRIZE_KINDS: tuple[str, ...] = BIG_PRIZES
PITY_THRESHOLD = 7  # 7 сухих круток подряд — и большой приз гарантирован
COUPON_TTL_HOURS = 24  # срок жизни купона со скидкой

SECTOR_TITLES: dict[str, str] = {
    DISCOUNT_10: "🎟 Скидка 10%",
    DISCOUNT_20: "🎟 Скидка 20%",
    DISCOUNT_30: "🎟 Скидка 30%",
    ACTIONS_15: "⚡ +15 действий ИИ",
    ACTIONS_50: "⚡ +50 действий ИИ",
    JACKPOT: "💎 Джекпот — день безлимита",
    MISS: "😅 Мимо",
}

SECTOR_DESCRIPTIONS: dict[str, str] = {
    DISCOUNT_10: "Купон −10% на подписку. Действует 24 часа — не зевай!",
    DISCOUNT_20: "Купон −20% на подписку. Действует 24 часа — не зевай!",
    DISCOUNT_30: "Купон −30% на подписку. Действует 24 часа — не зевай!",
    ACTIONS_15: "В запас упало 15 дополнительных действий ИИ.",
    ACTIONS_50: "В запас упало 50 дополнительных действий ИИ.",
    JACKPOT: "Безлимит на ИИ на 24 часа. Практикуйся сколько захочешь!",
    MISS: "Повезёт в следующий раз. Крутка будет доступна завтра.",
}


@dataclass
class WheelPrize:
    kind: str
    title: str = ""
    description: str = ""
    discount_pct: int = 0
    extra_actions: int = 0
    coupon_expires_at: str = ""


class WheelCooldown(Exception):
    """Крутка сегодня уже потрачена."""


class WheelService:
    """Сервис колеса удачи.

    Счётчик сухих круток (`dry_streak`) хранится в БД на пользователя
    (столбец user_balances.dry_streak), поэтому pity переживает перезапуск
    процесса и работает одинаково на любых инстансах сервиса.
    """

    def __init__(self, repo, rng: random.Random | None = None):
        self._repo = repo
        self._rng = rng or random.Random()

    @staticmethod
    def today() -> str:
        """Сегодня (ISO дата, UTC)."""
        return datetime.now(timezone.utc).date().isoformat()

    async def is_spin_available(self, user_id: int) -> bool:
        last = await self._repo.get_last_spin_date(user_id)
        return last != self.today()

    async def spin(self, user_id: int) -> WheelPrize:
        """Крутка на сегодня. Приз применяется, крутка всегда списывается.

        Спин атомарен: сначала фиксируем крутку в БД (INSERT ... ON CONFLICT
        DO NOTHING). Если сегодня уже было записано — крутка уже была, и мы
        НЕ применяем приз повторно (бросаем WheelCooldown). Это защищает от
        двойных бонусов при двух одновременных нажатиях.
        """
        if not await self.is_spin_available(user_id):
            raise WheelCooldown("Крутка доступна раз в сутки: сегодня уже крутил")

        inserted = await self._repo.save_spin(user_id, self.today())
        if not inserted:
            # Кто-то уже успел записать крутку — сегодняшняя уже потрачена.
            raise WheelCooldown("Крутка доступна раз в сутки: сегодня уже крутил")

        kind = await self._pick_kind(user_id)
        return await self._apply_prize(user_id, kind)

    async def _pick_kind(self, user_id: int) -> str:
        sub = await self._repo.get_subscription(user_id)
        is_subscriber = sub is not None and sub.is_active

        dry_streak = await self._repo.get_dry_streak(user_id)

        if dry_streak >= PITY_THRESHOLD:
            kind = self._rng.choice(BIG_PRIZE_KINDS)
        else:
            kind = self._pick_weighted()

        # подписчикам скидки не выпадают: вместо них бонус LLM-действий
        kind = self._translate_for_subscriber(kind, is_subscriber)

        if kind in BIG_PRIZES:
            await self._repo.set_dry_streak(user_id, 0)
        else:
            await self._repo.set_dry_streak(user_id, dry_streak + 1)
        return kind

    def _pick_weighted(self) -> str:
        total = sum(weight for _, weight in WHEEL_SECTORS)
        r = self._rng.random() * total
        upto = 0.0
        for kind, weight in WHEEL_SECTORS:
            upto += weight
            if r < upto:
                return kind
        return WHEEL_SECTORS[-1][0]

    @staticmethod
    def _translate_for_subscriber(kind: str, is_subscriber: bool) -> str:
        if not is_subscriber:
            return kind
        if kind == DISCOUNT_10:
            return ACTIONS_15
        if kind in (DISCOUNT_20, DISCOUNT_30):
            return ACTIONS_50
        return kind

    async def _apply_prize(self, user_id: int, kind: str) -> WheelPrize:
        if kind in (DISCOUNT_10, DISCOUNT_20, DISCOUNT_30):
            pct = self._discount_pct(kind)
            expires = (datetime.now(timezone.utc) + timedelta(hours=COUPON_TTL_HOURS)).isoformat()
            await self._repo.create_coupon(user_id, pct, expires)
            return WheelPrize(
                kind=kind,
                title=SECTOR_TITLES[kind],
                description=SECTOR_DESCRIPTIONS[kind],
                discount_pct=pct,
                coupon_expires_at=expires,
            )

        if kind in (ACTIONS_15, ACTIONS_50):
            amount = 50 if kind == ACTIONS_50 else 15
            await self._repo.add_extra_actions(user_id, amount)
            return WheelPrize(
                kind=kind,
                title=SECTOR_TITLES[kind],
                description=SECTOR_DESCRIPTIONS[kind],
                extra_actions=amount,
            )

        if kind == JACKPOT:
            await self._repo.grant_subscription(user_id, 1)
            return WheelPrize(
                kind=kind,
                title=SECTOR_TITLES[kind],
                description=SECTOR_DESCRIPTIONS[kind],
            )

        return WheelPrize(
            kind=kind,
            title=SECTOR_TITLES[kind],
            description=SECTOR_DESCRIPTIONS[kind],
        )

    @staticmethod
    def _discount_pct(kind: str) -> int:
        return int(kind.rsplit("_", 1)[1])