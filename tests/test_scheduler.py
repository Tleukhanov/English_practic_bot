"""Tests for Phase 11 — Scheduler (reminders)."""

import pytest
from core.scheduler import _build_reminder_message
from core.retention import RetentionInfo


def test_build_reminder_no_lessons():
    info = RetentionInfo(total_lessons=0)
    assert _build_reminder_message("Anna", info) is None


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
