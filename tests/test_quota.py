import pytest

from bot.quota import QuotaExceeded, QuotaGuard

from storage.sqlite import SQLiteRepository


@pytest.fixture
async def repo(tmp_path):
    db = SQLiteRepository(str(tmp_path / "quota.db"))
    await db.connect()
    yield db
    await db.close()


async def test_consume_within_limit(repo):
    guard = QuotaGuard(repo, daily_limit=3)
    user = await repo.get_or_create_user(1001)
    for _ in range(3):
        await guard.consume(user.id)
    assert await repo.get_llm_usage(user.id, guard._today()) == 3
    with pytest.raises(QuotaExceeded):
        await guard.consume(user.id)


async def test_zero_limit_is_disabled(repo):
    guard = QuotaGuard(repo, daily_limit=0)
    user = await repo.get_or_create_user(1002)
    for _ in range(100):
        await guard.consume(user.id)
    assert await repo.get_llm_usage(user.id, guard._today()) == 0


async def test_unlimited_user_bypasses_limit(repo):
    guard = QuotaGuard(repo, daily_limit=2)
    user = await repo.get_or_create_user(1003)
    await repo.set_unlimited_status(user.id, True)
    for _ in range(10):
        await guard.consume(user.id)
    assert await repo.get_unlimited_status(user.id) is True


async def test_usage_is_per_day(repo):
    user = await repo.get_or_create_user(1004)
    await repo.increment_llm_usage(user.id, "2026-08-30", 2)
    assert await repo.get_llm_usage(user.id, "2026-08-30") == 2
    assert await repo.get_llm_usage(user.id, "2026-08-31") == 0


async def test_increment_accumulates(repo):
    user = await repo.get_or_create_user(1005)
    await repo.increment_llm_usage(user.id, "2026-08-30", 1)
    await repo.increment_llm_usage(user.id, "2026-08-30", 1)
    assert await repo.get_llm_usage(user.id, "2026-08-30") == 2


async def test_custom_cost_consumption(repo):
    guard = QuotaGuard(repo, daily_limit=5)
    user = await repo.get_or_create_user(1006)
    await guard.consume(user.id, cost=3)
    await guard.consume(user.id, cost=2)
    assert await repo.get_llm_usage(user.id, guard._today()) == 5
    with pytest.raises(QuotaExceeded):
        await guard.consume(user.id, cost=1)


async def test_unlimited_status_default_false(repo):
    user = await repo.get_or_create_user(1007)
    assert await repo.get_unlimited_status(user.id) is False