import pytest

from bot.handlers.kaspi import _grant_order, _make_order_code

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


def test_make_order_code_format():
    code = _make_order_code()
    assert code.startswith("BOT-")
    assert len(code) == 8