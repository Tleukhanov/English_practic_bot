"""Pity-механика и атомарный спайн колеса: прогон через отдельные инстансы сервиса."""

from __future__ import annotations

import pytest

from core.wheel import (
    ACTIONS_15,
    BIG_PRIZES,
    MISS,
    WheelCooldown,
    WheelService,
)
from storage.sqlite import SQLiteRepository


class FakeRng:
    """Детерминированный подменщик random.Random (как в test_wheel.py)."""

    def __init__(self, random_values=None, choice_values=None):
        self._random = list(random_values or [])
        self._choice = list(choice_values or [])

    def random(self):
        return self._random.pop(0) if self._random else 0.0

    def choice(self, seq):
        return self._choice.pop(0) if self._choice else seq[0]


@pytest.fixture
async def repo(tmp_path):
    db = SQLiteRepository(str(tmp_path / "wheel_pity.db"))
    await db.connect()
    yield db
    await db.close()


async def _clear_spin(repo, user_id):
    """Сбрасываем кулдаун дня, чтобы уместить несколько круток в один тестовый день."""
    await repo._conn.execute("DELETE FROM wheel_spins WHERE user_id = ?", (user_id,))
    await repo._conn.commit()


async def test_pity_works_across_instances(repo):
    """7 сухих круток на инстансе A, следующая (гарантированный приз) на инстансе B."""
    user = await repo.get_or_create_user(201)

    # Инстанс A: 7 сухих круток — всегда MISS (после 7 сухих pity форсирует приз).
    svc_a = WheelService(repo, rng=FakeRng(random_values=[0.95 for _ in range(7)]))
    for _ in range(7):
        prize = await svc_a.spin(user.id)
        assert prize.kind == MISS
        await _clear_spin(repo, user.id)

    assert await repo.get_dry_streak(user.id) == 7

    # Инстанс B: следующий спин должен форсировать big prize.
    svc_b = WheelService(repo, rng=FakeRng(random_values=[0.95, 0.95]))
    prize = await svc_b.spin(user.id)
    assert prize.kind in BIG_PRIZES

    # После большого приза dry_streak сбрасывается в 0.
    assert await repo.get_dry_streak(user.id) == 0


async def test_dry_streak_resets_after_win(repo):
    """Ранний большой приз сразу сбрасывает счётчик сухих круток."""
    user = await repo.get_or_create_user(202)

    # 2 мимо подряд.
    svc_a = WheelService(repo, rng=FakeRng(random_values=[0.95, 0.95]))
    for _ in range(2):
        prize = await svc_a.spin(user.id)
        assert prize.kind == MISS
        await _clear_spin(repo, user.id)

    assert await repo.get_dry_streak(user.id) == 2

    # Сразу джекпот (random 0.92 -> JACKPOT) на новом инстансе.
    svc_b = WheelService(repo, rng=FakeRng(random_values=[0.92]))
    prize = await svc_b.spin(user.id)
    assert prize.kind in BIG_PRIZES
    await _clear_spin(repo, user.id)

    assert await repo.get_dry_streak(user.id) == 0

    # После сброса следующая крутка снова обычная справедливая (MISS возможен).
    svc_c = WheelService(repo, rng=FakeRng(random_values=[0.95]))
    prize = await svc_c.spin(user.id)
    assert prize.kind == MISS
    assert await repo.get_dry_streak(user.id) == 1


async def test_duplicate_spin_applies_prize_once(repo):
    """Двойная крутка за один день: приз применяется ровно один раз."""
    user = await repo.get_or_create_user(203)

    svc = WheelService(repo, rng=FakeRng(random_values=[0.6, 0.6]))
    prize = await svc.spin(user.id)
    assert prize.kind == ACTIONS_15
    assert await repo.get_extra_actions(user.id) == 15

    # Повторная крутка того же дня — WheelCooldown и НИКАКОГО нового приза.
    with pytest.raises(WheelCooldown):
        await svc.spin(user.id)

    assert await repo.get_extra_actions(user.id) == 15


async def test_duplicate_spin_no_double_subscription(repo):
    """Двойной джекпот не выдаёт две подписки."""
    user = await repo.get_or_create_user(204)

    svc = WheelService(repo, rng=FakeRng(random_values=[0.92, 0.92]))
    prize = await svc.spin(user.id)
    assert prize.kind in BIG_PRIZES
    sub = await repo.get_subscription(user.id)
    assert sub is not None

    with pytest.raises(WheelCooldown):
        await svc.spin(user.id)

    # Лишь одна подписка создана гарантированным призом колеса.
    cursor = await repo._conn.execute(
        "SELECT COUNT(*) AS n FROM subscriptions WHERE user_id = ?", (user.id,)
    )
    row = await cursor.fetchone()
    assert row["n"] == 1
