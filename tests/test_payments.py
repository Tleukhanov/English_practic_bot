"""Тесты Telegram Payments: resolve_price, apply_paid_subscription, импорт хэндлеров."""

import pytest

from bot.handlers.payments import apply_paid_subscription, resolve_price
from storage.repo import WheelCoupon
from storage.sqlite import SQLiteRepository


@pytest.fixture
async def repo(tmp_path):
    db = SQLiteRepository(str(tmp_path / "payments.db"))
    await db.connect()
    yield db
    await db.close()


def _coupon(discount_pct: int, expires_at: str) -> WheelCoupon:
    return WheelCoupon(
        id=1,
        user_id=1,
        discount_pct=discount_pct,
        expires_at=expires_at,
        used=False,
    )


def test_resolve_price_plain():
    assert resolve_price(499, None) == (499, 0)


def test_resolve_price_discounted():
    coupon = _coupon(20, "2099-01-01T00:00:00+00:00")
    assert resolve_price(499, coupon) == (400, 20)
    assert resolve_price(1299, coupon) == (1040, 20)


def test_resolve_price_expired_coupon():
    coupon = _coupon(20, "2020-01-01T00:00:00+00:00")
    assert resolve_price(499, coupon) == (499, 0)


async def test_apply_paid_subscription_grants(repo):
    user = await repo.get_or_create_user(10)
    sub = await apply_paid_subscription(repo, user.id, 7, "charge-1", 499, "RUB", 0)
    assert sub is not None
    saved = await repo.get_subscription(user.id)
    assert saved is not None and saved.is_active
    assert saved.id == sub.id
    paid = await repo.find_payment("charge-1")
    assert paid is not None
    assert paid.user_id == user.id
    assert paid.amount == 499
    assert paid.plan_days == 7
    assert paid.discount_pct == 0


async def test_apply_paid_subscription_idempotent(repo):
    user = await repo.get_or_create_user(11)
    first = await apply_paid_subscription(repo, user.id, 7, "charge-2", 400, "RUB", 20)
    assert first is not None
    expires_before = (await repo.get_subscription(user.id)).expires_at
    paid_before = await repo.find_payment("charge-2")

    second = await apply_paid_subscription(repo, user.id, 7, "charge-2", 400, "RUB", 20)
    assert second is None

    saved = await repo.get_subscription(user.id)
    assert saved.expires_at == expires_before
    assert saved.id == first.id
    paid_after = await repo.find_payment("charge-2")
    assert paid_after is not None and paid_after.id == paid_before.id


async def test_apply_paid_subscription_marks_coupon(repo):
    user = await repo.get_or_create_user(12)
    coupon = await repo.create_coupon(user.id, 20, "2099-01-01T00:00:00+00:00")
    assert await repo.get_active_coupon(user.id) is not None

    sub = await apply_paid_subscription(
        repo, user.id, 30, "charge-3", 1040, "RUB", 20, coupon_id=coupon.id
    )
    assert sub is not None
    assert await repo.get_active_coupon(user.id) is None


async def test_apply_paid_subscription_ignores_wrong_coupon(repo):
    user = await repo.get_or_create_user(13)
    coupon = await repo.create_coupon(user.id, 30, "2099-01-01T00:00:00+00:00")
    await apply_paid_subscription(repo, user.id, 30, "charge-4", 910, "RUB", 30, coupon_id=999)
    active = await repo.get_active_coupon(user.id)
    assert active is not None and active.id == coupon.id


def test_import_payments_module():
    import bot.handlers.payments as payments

    assert payments.router is not None
    assert callable(payments.apply_paid_subscription)