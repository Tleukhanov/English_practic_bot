import pytest

from core.analytics import EventTracker, format_admin_stats

from storage.sqlite import SQLiteRepository


@pytest.fixture
async def repo(tmp_path):
    db = SQLiteRepository(str(tmp_path / "analytics.db"))
    await db.connect()
    yield db
    await db.close()


async def test_append_event_roundtrip(repo):
    user = await repo.get_or_create_user(3001)
    await repo.append_event(user.id, "premium_screen_shown")
    await repo.append_event(user.id, "wheel_spin", {"kind": "MISS"})

    assert await repo.count_events("premium_screen_shown", "2000-01-01") == 1
    assert await repo.count_events("wheel_spin", "2000-01-01") == 1
    assert await repo.count_events("unknown", "2000-01-01") == 0
    assert await repo.count_events("wheel_spin", "2999-01-01") == 0


async def test_event_tracker_stores_row(repo):
    user = await repo.get_or_create_user(3002)
    tracker = EventTracker(repo)
    await tracker.track(user.id, "kaspi_order_created", {"days": 7, "amount": 1990})
    assert await repo.count_events("kaspi_order_created", "2000-01-01") == 1


def test_format_admin_stats():
    text = format_admin_stats(pending_orders=3, revenue=5970, active_subs=2, spins_today=17)
    assert "Заявок на подтверждение: 3" in text
    assert "Выручка (подтверждённые): 5970₸" in text
    assert "Активных подписок: 2" in text
    assert "Круток сегодня: 17" in text


async def test_admin_aggregates_on_fresh_db(repo):
    assert await repo.count_pending_orders() == 0
    assert await repo.sum_revenue() == 0
    assert await repo.count_active_subscriptions() == 0
    assert await repo.count_spins_today("2000-01-01") == 0


async def test_admin_aggregates_with_data(repo):
    u1 = await repo.get_or_create_user(3003)
    u2 = await repo.get_or_create_user(3004)

    o1 = await repo.create_order(u1.id, 7, 1990, 0, 0, "BOT-A1B2")
    o2 = await repo.create_order(u2.id, 30, 3990, 0, 0, "BOT-C3D4")
    assert await repo.count_pending_orders() == 2

    await repo.approve_order(o1.id)
    assert await repo.count_pending_orders() == 1
    assert await repo.sum_revenue() == 1990

    await repo.grant_subscription(u1.id, 7)
    await repo.grant_subscription(u2.id, 30)
    assert await repo.count_active_subscriptions() == 2

    assert await repo.save_spin(u1.id, "2026-09-09")
    assert await repo.count_spins_today("2026-09-09") == 1
    assert await repo.count_spins_today("2026-09-10") == 0


async def test_tracker_events_roundtrip(repo):
    user = await repo.get_or_create_user(3005)
    tracker = EventTracker(repo)
    await tracker.track(user.id, "stuff")
    assert await repo.count_events("stuff", "2000-01-01") == 1