"""Tests for Phase 11 — Scheduler (reminders)."""

import pytest
from core.scheduler import _build_expiry_message, _build_reminder_message, ReminderDedupe
from core.retention import RetentionInfo


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
