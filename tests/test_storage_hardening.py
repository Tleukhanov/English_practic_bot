"""Фаза 1 storage — атомарность, идемпотентность, схема, streak.

Тесты харднинга хранилища: атомарные upsert/INSERT OR IGNORE, зажим
decrement, owner-aware сжигание купона, валидация скидок, трёхзначный
is_correct, gap-семантика streak и колонки схемы на свежей БД.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.progress import ProgressService
from storage.repo import SRSWord
from storage.sqlite import SQLiteRepository


@pytest.fixture
async def repo(tmp_path):
    db = SQLiteRepository(str(tmp_path / "hardening.db"))
    await db.connect()
    yield db
    await db.close()


async def test_get_or_create_user_two_sequential_same_tg_id_one_row(repo):
    first = await repo.get_or_create_user(90001, username="alice")
    second = await repo.get_or_create_user(90001, username="alice-renamed")
    assert first.id == second.id
    cursor = await repo._conn.execute(
        "SELECT COUNT(*) AS n FROM users WHERE tg_id = ?", (90001,)
    )
    row = await cursor.fetchone()
    assert row["n"] == 1
    assert second.username == "alice-renamed"


async def test_create_payment_duplicate_id_returns_same(repo):
    user = await repo.get_or_create_user(90002)
    p1 = await repo.create_payment(user.id, "dup-pay-1", 499, "RUB", 7, 0)
    p2 = await repo.create_payment(user.id, "dup-pay-1", 100, "USD", 1, 10)
    assert p1.id == p2.id
    assert p1.telegram_payment_id == p2.telegram_payment_id
    cursor = await repo._conn.execute(
        "SELECT COUNT(*) AS n FROM payments WHERE telegram_payment_id = ?", ("dup-pay-1",)
    )
    row = await cursor.fetchone()
    assert row["n"] == 1


async def test_decrement_extra_actions_clamps_at_zero(repo):
    user = await repo.get_or_create_user(90003)
    await repo.add_extra_actions(user.id, 2)
    await repo.decrement_extra_actions(user.id, 5)
    assert await repo.get_extra_actions(user.id) == 0


async def test_add_extra_actions_is_additive(repo):
    user = await repo.get_or_create_user(90004)
    await repo.add_extra_actions(user.id, 10)
    await repo.add_extra_actions(user.id, 5)
    assert await repo.get_extra_actions(user.id) == 15


async def test_mark_coupon_used_wrong_owner_is_noop(repo):
    owner = await repo.get_or_create_user(90005)
    other = await repo.get_or_create_user(90006)
    coupon = await repo.create_coupon(owner.id, 20, "2099-01-01T00:00:00+00:00")
    await repo.mark_coupon_used(coupon.id, other.id)
    active = await repo.get_active_coupon(owner.id)
    assert active is not None and active.id == coupon.id


async def test_mark_coupon_used_right_owner_burns(repo):
    owner = await repo.get_or_create_user(90007)
    coupon = await repo.create_coupon(owner.id, 30, "2099-01-01T00:00:00+00:00")
    await repo.mark_coupon_used(coupon.id, owner.id)
    assert await repo.get_active_coupon(owner.id) is None


@pytest.mark.parametrize("bad", [150, -10, 101, -1])
async def test_create_coupon_rejects_invalid_discount(repo, bad):
    user = await repo.get_or_create_user(90008)
    with pytest.raises(ValueError):
        await repo.create_coupon(user.id, bad, "2099-01-01T00:00:00+00:00")


async def test_create_coupon_accepts_boundaries(repo):
    user = await repo.get_or_create_user(90009)
    for pct in (0, 100):
        coupon = await repo.create_coupon(user.id, pct, "2099-01-01T00:00:00+00:00")
        assert coupon.discount_pct == pct


async def test_streak_gap_breaks_both_funcs_agree(repo):
    user = await repo.get_or_create_user(90010)
    today = datetime.now(timezone.utc).date()
    dates = [today, today - timedelta(days=1), today - timedelta(days=2), today - timedelta(days=4)]
    dates_str = [d.isoformat() for d in dates]

    progress_streak = ProgressService._get_streak([], dates_str)
    assert progress_streak == 3

    for d in dates_str:
        await repo._conn.execute(
            "INSERT INTO messages (user_id, role, content, created_at) "
            "VALUES (?, 'user', ?, ?)",
            (user.id, "m", d + "T10:00:00+00:00"),
        )
    await repo._conn.commit()
    sqlite_streak = await repo._calc_streak(user.id)
    assert sqlite_streak == progress_streak == 3


def test_streak_no_grace_for_yesterday():
    today = datetime.now(timezone.utc).date()
    yesterday = (today - timedelta(days=1)).isoformat()
    assert ProgressService._get_streak([], [today.isoformat()]) == 1
    assert ProgressService._get_streak([], [yesterday]) == 0


async def test_fresh_db_schema_columns(repo):
    await repo._conn.execute("SELECT level, unlimited FROM users LIMIT 1")
    await repo._conn.execute("SELECT lesson_id FROM messages LIMIT 1")
    cursor = await repo._conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_kaspi_orders_pending'")
    assert await cursor.fetchone() is not None


async def test_is_correct_three_state(repo):
    user = await repo.get_or_create_user(90011)
    session = await repo.start_lesson(user.id, "T", "{}")
    none_id = await repo.add_user_message(user.id, "no verdict", lesson_id=session.id, is_correct=None)
    true_id = await repo.add_user_message(user.id, "correct", lesson_id=session.id, is_correct=True)
    false_id = await repo.add_user_message(user.id, "wrong", lesson_id=session.id, is_correct=False)

    messages = await repo.get_lesson_messages(session.id)
    by_id = {m["content"]: m for m in messages}
    assert by_id["no verdict"]["is_correct"] is None
    assert by_id["correct"]["is_correct"] is True
    assert by_id["wrong"]["is_correct"] is False


async def test_add_srs_word_ignored_duplicate_returns_none(repo):
    user = await repo.get_or_create_user(90012)
    word = SRSWord(user_id=user.id, word="hello", translation="привет")
    inserted = await repo.add_srs_word(word)
    assert inserted is not None and inserted > 0
    duplicate = await repo.add_srs_word(
        SRSWord(user_id=user.id, word="hello", translation="привет")
    )
    assert duplicate is None
