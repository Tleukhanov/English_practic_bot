"""Tests for Phase 11 — Scheduler (reminders)."""

import time
from datetime import datetime, timezone, timedelta

import pytest
from aiogram.exceptions import TelegramRetryAfter
from core.scheduler import _build_expiry_message, _build_reminder_message, ReminderDedupe
from core import scheduler as sched
from core.retention import RetentionInfo
from storage.repo import Subscription, UserRow


class FakeBot:
    def __init__(self, fail_ids=None, flood_ids=None):
        self.sent = []
        self.times = []
        self._fail_ids = set(fail_ids or ())
        self._flood_ids = set(flood_ids or ())

    async def send_message(self, chat_id, text):
        if chat_id in self._flood_ids:
            raise TelegramRetryAfter(method=None, message="flood", retry_after=0)
        if chat_id in self._fail_ids:
            raise RuntimeError("boom")
        self.sent.append((chat_id, text))
        self.times.append(time.monotonic())


class FakeRepo:
    def __init__(self, users, spins=None, subs=None, activity=None):
        self.users = users
        self.spins = spins or {}
        self.subs = subs or {}
        self.activity = activity or {}

    async def get_all_users(self):
        return self.users

    async def get_last_spin_date(self, user_id):
        return self.spins.get(user_id)

    async def get_subscription(self, user_id):
        return self.subs.get(user_id)

    async def get_lesson_notes(self, user_id, limit=10):
        return []

    async def get_practice_dates(self, user_id, limit=50):
        return []

    async def get_last_activity(self, user_id):
        return self.activity.get(user_id)


def _stale_user(uid, tg_id, name="Anna"):
    return UserRow(id=uid, tg_id=tg_id, first_name=name)


def _stale_activity():
    return (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()


@pytest.fixture(autouse=True)
def reset_scheduler_state(monkeypatch):
    monkeypatch.setattr(sched, "SEND_PAUSE_SECONDS", 0.0)
    monkeypatch.setattr(sched, "_practice_reminder_dedupe", sched.ReminderDedupe())
    monkeypatch.setattr(
        sched, "_wheel_reminder_throttle", sched.ReminderThrottle(24 * 60 * 60)
    )
    monkeypatch.setattr(sched, "_expiry_reminder_dedupe", sched.ReminderDedupe())
    monkeypatch.setattr(sched, "_FLOOD_SLEEP_CAP_SECONDS", 0)


@pytest.mark.asyncio
async def test_mass_send_has_pause_between_recipients(monkeypatch):
    monkeypatch.setattr(sched, "SEND_PAUSE_SECONDS", 0.05)
    activity = _stale_activity()
    repo = FakeRepo(
        users=[_stale_user(1, 111), _stale_user(2, 222)],
        activity={1: activity, 2: activity},
    )
    bot = FakeBot()
    await sched.check_and_send_reminders(bot, repo)
    assert len(bot.sent) == 2
    assert bot.times[1] - bot.times[0] >= 0.04


@pytest.mark.asyncio
async def test_wheel_reminder_skips_user_without_spins():
    today = datetime.now(timezone.utc).date().isoformat()
    repo = FakeRepo(
        users=[_stale_user(1, 111), _stale_user(2, 222), _stale_user(3, 333)],
        spins={3: today},
        subs={2: Subscription(user_id=2, plan_days=7, expires_at="2999-01-01T00:00:00+00:00")},
    )
    bot = FakeBot()
    await sched.reminder_wheel_misses(bot, repo)
    chat_ids = [chat_id for chat_id, _ in bot.sent]
    assert chat_ids == [222]


@pytest.mark.asyncio
async def test_send_error_for_one_user_does_not_block_others():
    activity = _stale_activity()
    repo = FakeRepo(
        users=[_stale_user(1, 111), _stale_user(2, 222), _stale_user(3, 333)],
        activity={1: activity, 2: activity, 3: activity},
    )
    bot = FakeBot(fail_ids={222})
    await sched.check_and_send_reminders(bot, repo)
    chat_ids = [chat_id for chat_id, _ in bot.sent]
    assert chat_ids == [111, 333]


@pytest.mark.asyncio
async def test_flood_wait_for_one_user_does_not_break_batch():
    activity = _stale_activity()
    repo = FakeRepo(
        users=[_stale_user(1, 111), _stale_user(2, 222)],
        activity={1: activity, 2: activity},
    )
    bot = FakeBot(flood_ids={111})
    await sched.check_and_send_reminders(bot, repo)
    chat_ids = [chat_id for chat_id, _ in bot.sent]
    assert chat_ids == [222]


@pytest.mark.asyncio
async def test_daily_reminder_not_more_often_than_once_per_day():
    repo = FakeRepo(users=[_stale_user(1, 111)], activity={1: _stale_activity()})
    bot = FakeBot()
    await sched.check_and_send_reminders(bot, repo)
    await sched.check_and_send_reminders(bot, repo)
    assert len(bot.sent) == 1


@pytest.mark.asyncio
async def test_wheel_reminder_not_more_often_than_once_a_day():
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
    repo = FakeRepo(users=[_stale_user(1, 111)], spins={1: yesterday})
    bot = FakeBot()
    await sched.reminder_wheel_misses(bot, repo)
    await sched.reminder_wheel_misses(bot, repo)
    assert len(bot.sent) == 1


def test_build_reminder_no_activity():
    info = RetentionInfo(total_lessons=0, last_practice_hours=None)
    assert _build_reminder_message("Anna", info) is None


def test_build_reminder_for_free_chat_user_without_lessons():
    info = RetentionInfo(total_lessons=0, last_practice_hours=36)
    msg = _build_reminder_message("Anna", info)
    assert msg is not None
    assert "36" in msg


def test_build_reminder_no_practice_time():
    info = RetentionInfo(total_lessons=5, last_practice_hours=None)
    assert _build_reminder_message("Anna", info) is None


def test_build_reminder_recently_practiced():
    info = RetentionInfo(total_lessons=5, last_practice_hours=2)
    assert _build_reminder_message("Anna", info) is None


def test_build_reminder_with_weak_areas():
    info = RetentionInfo(
        total_lessons=5,
        last_practice_hours=36,
        weak_areas=["Past Simple", "Present Perfect"],
    )
    msg = _build_reminder_message("Anna", info)
    assert msg is not None
    assert "Anna" in msg
    assert "36" in msg
    assert "Past Simple" in msg
    assert "Present Perfect" in msg


def test_build_reminder_no_weak_areas():
    info = RetentionInfo(
        total_lessons=5,
        last_practice_hours=48,
        weak_areas=[],
    )
    msg = _build_reminder_message("Anna", info)
    assert msg is not None
    assert "Anna" in msg
    assert "48" in msg


def test_build_reminder_with_streak():
    info = RetentionInfo(
        total_lessons=5,
        last_practice_hours=30,
        weak_areas=["Past Simple"],
        streak_days=5,
    )
    msg = _build_reminder_message("Anna", info)
    assert msg is not None
    assert "5 дней" in msg
    assert "🔥" in msg


def test_build_reminder_no_streak():
    info = RetentionInfo(
        total_lessons=5,
        last_practice_hours=30,
        weak_areas=[],
        streak_days=1,
    )
    msg = _build_reminder_message("Anna", info)
    assert msg is not None
    assert "Серия" not in msg


def test_build_expiry_message_contains_expiry_and_premium():
    msg = _build_expiry_message("2026-09-10T12:00:00+00:00", 7)
    assert "истекает" in msg
    assert "/premium" in msg


def test_build_expiry_message_shows_date_and_days():
    msg = _build_expiry_message("2026-09-10T12:00:00+00:00", 30)
    assert "2026-09-10" in msg
    assert "30" in msg


def test_reminder_dedupe_first_send_true():
    d = ReminderDedupe()
    assert d.should_send(1, "2026-09-10T12:00:00+00:00") is True


def test_reminder_dedupe_same_expiry_false():
    d = ReminderDedupe()
    assert d.should_send(1, "2026-09-10T12:00:00+00:00") is True
    assert d.should_send(1, "2026-09-10T12:00:00+00:00") is False


def test_reminder_dedupe_different_expiry_true():
    d = ReminderDedupe()
    assert d.should_send(1, "2026-09-10T12:00:00+00:00") is True
    assert d.should_send(1, "2026-09-11T12:00:00+00:00") is True
