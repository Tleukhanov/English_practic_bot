"""Tests for Phase 9 — RetentionService."""

import pytest
from datetime import datetime, timezone, timedelta

from core.retention import _parse_created_at
from core.progress import ProgressService
from storage.repo import LessonNote


# --- _parse_created_at ---

def test_parse_created_at_valid():
    result = _parse_created_at("2026-08-20T12:00:00+00:00")
    assert result is not None
    assert result.year == 2026


def test_parse_created_at_none():
    assert _parse_created_at(None) is None


def test_parse_created_at_invalid():
    assert _parse_created_at("not-a-date") is None


# --- streak via ProgressService ---

def test_streak_single_day():
    today = datetime.now(timezone.utc)
    notes = [LessonNote(created_at=today.isoformat())]
    assert ProgressService._get_streak(notes) == 1


def test_streak_two_days():
    today = datetime.now(timezone.utc)
    yesterday = today - timedelta(days=1)
    notes = [
        LessonNote(created_at=today.isoformat()),
        LessonNote(created_at=yesterday.isoformat()),
    ]
    assert ProgressService._get_streak(notes) == 2


def test_streak_broken():
    today = datetime.now(timezone.utc)
    three_days_ago = today - timedelta(days=3)
    notes = [
        LessonNote(created_at=today.isoformat()),
        LessonNote(created_at=three_days_ago.isoformat()),
    ]
    assert ProgressService._get_streak(notes) == 1


def test_streak_empty():
    assert ProgressService._get_streak([]) == 0


def test_streak_invalid_dates():
    notes = [LessonNote(created_at="invalid"), LessonNote(created_at="also-invalid")]
    assert ProgressService._get_streak(notes) == 0


# --- weak areas via ProgressService ---

def test_weak_areas_from_notes():
    notes = [
        LessonNote(mistakes="Present Simple, Past Simple"),
        LessonNote(mistakes="Present Simple, Past Perfect"),
        LessonNote(mistakes="Past Simple"),
    ]
    areas = ProgressService._get_weak_areas(notes)
    assert "Present Simple" in areas
    assert "Past Simple" in areas
    assert len(areas) <= 5


def test_weak_areas_empty():
    assert ProgressService._get_weak_areas([]) == []


def test_weak_areas_no_mistakes():
    notes = [LessonNote(mistakes=""), LessonNote(mistakes=None)]
    assert ProgressService._get_weak_areas(notes) == []


def test_weak_areas_frequency():
    notes = [
        LessonNote(mistakes="Past Simple"),
        LessonNote(mistakes="Past Simple"),
        LessonNote(mistakes="Past Simple"),
        LessonNote(mistakes="Present Simple"),
    ]
    areas = ProgressService._get_weak_areas(notes)
    assert areas[0] == "Past Simple"
