"""Тесты колеса удачи: спин, купоны, бонусы действий, джекпот, pity."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.wheel import (
    ACTIONS_15,
    ACTIONS_50,
    BIG_PRIZES,
    DISCOUNT_10,
    DISCOUNT_20,
    JACKPOT,
    MISS,
    WheelCooldown,
    WheelPrize,
    WheelService,
)
from storage.sqlite import SQLiteRepository


class FakeRng:
    """Детерминированный подменщик random.Random.

    random() выдаёт числа из очереди по очереди (по умолчанию 0.0),
    choice(seq) — первый элемент seq (либо из своей очереди).
    """

    def __init__(self, random_values=None, choice_values=None):
        self._random = list(random_values or [])
        self._choice = list(choice_values or [])

    def random(self):
        return self._random.pop(0) if self._random else 0.0

    def choice(self, seq):
        return self._choice.pop(0) if self._choice else seq[0]


@pytest.fixture
async def repo(tmp_path):
    db = SQLiteRepository(str(tmp_path / "wheel.db"))
    await db.connect()
    yield db
    await db.close()


async def test_spin_saves_and_cooldowns(repo):
    user = await repo.get_or_create_user(101, username="wheel_user")
    svc = WheelService(repo)

    assert await svc.is_spin_available(user.id)
    await svc.spin(user.id)

    assert await repo.get_last_spin_date(user.id) == WheelService.today()
    assert not await svc.is_spin_available(user.id)
    with pytest.raises(WheelCooldown):
        await svc.spin(user.id)


async def test_discount_creates_coupon(repo):
    user = await repo.get_or_create_user(102)
    # random()=0.0 -> сектор DISCOUNT_10
    svc = WheelService(repo, rng=FakeRng(random_values=[0.0]))

    prize = await svc.spin(user.id)

    assert isinstance(prize, WheelPrize)
    assert prize.kind == DISCOUNT_10
    assert prize.discount_pct == 10
    expires = datetime.fromisoformat(prize.coupon_expires_at.replace("Z", "+00:00"))
    assert expires > datetime.now(timezone.utc)

    coupon = await repo.get_active_coupon(user.id)
    assert coupon is not None
    assert coupon.discount_pct == 10


async def test_extra_actions_prize(repo):
    user = await repo.get_or_create_user(103)
    # random()=0.6*100=60 -> интервал ACTIONS_15 [56, 81)
    svc = WheelService(repo, rng=FakeRng(random_values=[0.6]))

    prize = await svc.spin(user.id)

    assert prize.kind == ACTIONS_15
    assert prize.extra_actions == 15
    assert await repo.get_extra_actions(user.id) == 15


async def test_jackpot_grants_one_day_sub(repo):
    user = await repo.get_or_create_user(104)
    # random()=0.92*100=92 -> интервал JACKPOT [91, 94)
    svc = WheelService(repo, rng=FakeRng(random_values=[0.92]))

    prize = await svc.spin(user.id)

    assert prize.kind == JACKPOT
    sub = await repo.get_subscription(user.id)
    assert sub is not None
    assert sub.plan_days == 1
    assert sub.is_active


async def test_subscriber_gets_actions_not_discount(repo):
    user = await repo.get_or_create_user(105)
    await repo.grant_subscription(user.id, 7)
    # сектор DISCOUNT_10, но подписчику должен упасть ACTIONS_15
    svc = WheelService(repo, rng=FakeRng(random_values=[0.0]))

    prize = await svc.spin(user.id)

    assert prize.kind == ACTIONS_15
    assert prize.extra_actions == 15
    assert await repo.get_active_coupon(user.id) is None
    assert await repo.get_extra_actions(user.id) == 15


async def test_pity_forces_big_prize(repo):
    user = await repo.get_or_create_user(106)
    # всегда MISS, пока pity не форсирует большой приз
    svc = WheelService(repo, rng=FakeRng(random_values=[0.95 for _ in range(7)]))

    for _ in range(7):
        prize = await svc.spin(user.id)
        assert prize.kind == MISS
        # сбрасываем кулдаун, чтобы уместить 8 круток в один день
        await repo._conn.execute("DELETE FROM wheel_spins WHERE user_id = ?", (user.id,))
        await repo._conn.commit()

    prize = await svc.spin(user.id)
    assert prize.kind in BIG_PRIZES


async def test_import_handlers_smoke():
    import bot.handlers.wheel as wheel_handlers

    assert wheel_handlers.router is not None