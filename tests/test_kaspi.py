import asyncio

import pytest

from bot.handlers.kaspi import (
    ORDER_CODE_LENGTH,
    _grant_order,
    _make_order_code,
    _make_unique_order_code,
    ensure_pending_order,
)

from storage.repo import KaspiOrder
from storage.sqlite import SQLiteRepository


@pytest.fixture
async def repo(tmp_path):
    db = SQLiteRepository(str(tmp_path / "kaspi.db"))
    await db.connect()
    yield db
    await db.close()


async def test_create_and_fetch_pending(repo):
    user = await repo.get_or_create_user(2001, username="u", first_name="U")
    order = await repo.create_order(user.id, 7, 1990, 0, 0, "BOT-AAAA")
    assert order.order_code == "BOT-AAAA"
    assert order.plan_days == 7
    assert order.amount == 1990
    assert order.status == KaspiOrder.STATUS_PENDING

    fetched = await repo.get_pending_order(user.id)
    assert fetched.id == order.id
    assert fetched.order_code == "BOT-AAAA"
    by_id = await repo.get_order(order.id)
    assert by_id.user_id == user.id


async def test_pending_returns_latest(repo):
    user = await repo.get_or_create_user(2002)
    first = await repo.create_order(user.id, 1, 990, 0, 0, "BOT-1111")
    second = await repo.create_order(user.id, 7, 1990, 0, 0, "BOT-2222")
    pending = await repo.get_pending_order(user.id)
    assert pending.id == second.id
    assert pending.order_code == "BOT-2222"
    assert first.id != second.id


async def test_attach_photo(repo):
    user = await repo.get_or_create_user(2003)
    order = await repo.create_order(user.id, 1, 990, 0, 0, _make_order_code())
    await repo.attach_photo(order.id, "FILE_ID")
    fetched = await repo.get_order(order.id)
    assert fetched.photo_file_id == "FILE_ID"


async def test_approve_order_is_idempotent(repo):
    user = await repo.get_or_create_user(2004)
    order = await repo.create_order(user.id, 7, 1990, 0, 0, _make_order_code())
    approved = await repo.approve_order(order.id)
    assert approved.status == KaspiOrder.STATUS_APPROVED
    assert approved.confirmed_at
    assert await repo.approve_order(order.id) is None


async def test_grant_order_activates_subscription_once(repo):
    user = await repo.get_or_create_user(2005)
    order = await repo.create_order(user.id, 7, 1990, 0, 0, _make_order_code())
    sub = await _grant_order(repo, order)
    assert sub is not None
    assert sub.plan_days == 7
    assert sub.is_active

    second = await _grant_order(repo, order)
    assert second is None
    sub_after = await repo.get_subscription(user.id)
    assert sub_after.expires_at == sub.expires_at


async def test_grant_burns_coupon(repo):
    user = await repo.get_or_create_user(2006)
    coupon = await repo.create_coupon(user.id, 20, "2099-01-01")
    order = await repo.create_order(user.id, 7, 1990, 20, coupon.id, _make_order_code())
    await _grant_order(repo, order)
    active = await repo.get_active_coupon(user.id)
    assert active is None


async def test_coupon_burned_only_on_grant_repo(repo):
    """Купон НЕ сгорает при создании заказа — только при подтверждении в _grant_order."""
    user = await repo.get_or_create_user(2009)
    coupon = await repo.create_coupon(user.id, 20, "2099-01-01")

    order = await ensure_pending_order(repo, user.id, 7, 1990)
    assert order.coupon_id == coupon.id
    assert order.discount_pct == 20

    # создание заказа купон не трогает
    active = await repo.get_active_coupon(user.id)
    assert active is not None and active.id == coupon.id

    # сгорает только при подтверждении
    await _grant_order(repo, order)
    assert await repo.get_active_coupon(user.id) is None


async def test_reject_cancels_without_grant(repo):
    user = await repo.get_or_create_user(2007)
    order = await repo.create_order(user.id, 1, 990, 0, 0, _make_order_code())
    await repo.attach_photo(order.id, "FILE")
    await repo.cancel_order(order.id)
    assert await repo.get_pending_order(user.id) is None
    cancelled = await repo.get_order(order.id)
    assert cancelled.status == KaspiOrder.STATUS_CANCELLED
    sub = await repo.get_subscription(user.id)
    assert (sub is None) or (not sub.is_active)


async def test_switch_tariff_creates_new_order(repo):
    """Выбор другого тарифа при живом заказе: старый отменяется, остаётся один."""
    user = await repo.get_or_create_user(2008)
    old = await repo.create_order(user.id, 7, 1990, 0, 0, _make_order_code())
    await repo.cancel_order(old.id)
    new = await repo.create_order(user.id, 30, 1990, 0, 0, _make_order_code())
    pending = await repo.get_pending_order(user.id)
    assert pending.id == new.id
    assert pending.plan_days == 30
    assert await repo.get_order(old.id) is not None
    restored = await repo.get_order(old.id)
    assert restored.status == KaspiOrder.STATUS_CANCELLED


def test_make_order_code_length():
    code = _make_order_code()
    assert code.startswith("BOT-")
    assert len(code) - len("BOT-") >= 6
    assert len(code) == len("BOT-") + ORDER_CODE_LENGTH


async def test_switch_tariff_keeps_discount(repo):
    """Смена тарифа не теряет скидку молча: купон живой, применён к новому заказу."""
    user = await repo.get_or_create_user(2011)
    coupon = await repo.create_coupon(user.id, 30, "2099-01-01")

    first = await ensure_pending_order(repo, user.id, 7, 1990)
    assert first.discount_pct == 30
    assert first.coupon_id == coupon.id

    second = await ensure_pending_order(repo, user.id, 30, 3990)
    assert second.plan_days == 30
    assert second.discount_pct == 30
    assert second.coupon_id == coupon.id
    # купон никуда не делся
    assert await repo.get_active_coupon(user.id) is not None
    # старый pending отменён, живой ровно один
    assert (await repo.get_order(first.id)).status == KaspiOrder.STATUS_CANCELLED
    pending = await repo.get_pending_order(user.id)
    assert pending.id == second.id
    assert pending.plan_days == 30


async def test_double_tap_creates_one_live_order(repo):
    """Двойной тап «Оплатить» → один живой pending-заказ, второй тап возвращает его же."""
    user = await repo.get_or_create_user(2012)
    a, b = await asyncio.gather(
        ensure_pending_order(repo, user.id, 7, 1990),
        ensure_pending_order(repo, user.id, 7, 1990),
    )
    assert a.id == b.id
    cursor = await repo._conn.execute(
        "SELECT COUNT(*) AS n FROM kaspi_orders WHERE user_id = ? AND status = ?",
        (user.id, KaspiOrder.STATUS_PENDING),
    )
    row = await cursor.fetchone()
    assert row["n"] == 1


async def test_ensure_pending_cancels_existing_pendings(repo):
    """Новый тариф при уже накопившихся pending: все старые отменены, остаётся один живой."""
    user = await repo.get_or_create_user(2013)
    old1 = await repo.create_order(user.id, 7, 1990, 0, 0, "BOT-OLD001")
    old2 = await repo.create_order(user.id, 7, 1990, 0, 0, "BOT-OLD002")

    order = await ensure_pending_order(repo, user.id, 30, 3990)
    assert order.plan_days == 30
    assert (await repo.get_order(old1.id)).status == KaspiOrder.STATUS_CANCELLED
    assert (await repo.get_order(old2.id)).status == KaspiOrder.STATUS_CANCELLED
    pending = await repo.get_pending_order(user.id)
    assert pending.id == order.id


async def test_unique_order_codes_for_many_orders(repo):
    """Коды заказов уникальны (каждый длиннее 6 символов после префикса)."""
    user = await repo.get_or_create_user(2014)
    codes = set()
    for _ in range(25):
        order = await repo.replace_pending_order(
            user.id, 7, 1990, 0, 0, _make_order_code()
        )
        codes.add(order.order_code)
        assert len(order.order_code) - len("BOT-") >= 6
    assert len(codes) == 25


async def test_make_unique_order_code_retries_on_collision(repo, monkeypatch):
    user = await repo.get_or_create_user(2015)
    taken = "BOT-" + "A" * ORDER_CODE_LENGTH
    await repo.create_order(user.id, 7, 1990, 0, 0, taken)

    calls = {"n": 0}

    def fake_choices(alphabet, k=ORDER_CODE_LENGTH):
        calls["n"] += 1
        return (["A"] if calls["n"] == 1 else ["B"]) * k

    monkeypatch.setattr("bot.handlers.kaspi.random.choices", fake_choices)
    code = await _make_unique_order_code(repo)
    assert calls["n"] == 2
    assert code == "BOT-" + "B" * ORDER_CODE_LENGTH
    assert not await repo.is_order_code_taken(code)


async def test_is_order_code_taken_ignores_cancelled(repo):
    user = await repo.get_or_create_user(2016)
    order = await repo.create_order(user.id, 7, 1990, 0, 0, "BOT-TEST01")
    assert await repo.is_order_code_taken("BOT-TEST01") is True
    await repo.cancel_order(order.id)
    assert await repo.is_order_code_taken("BOT-TEST01") is False