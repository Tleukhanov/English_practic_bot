"""Tests for Phase 12 — Achievements + Levels."""

import pytest
from core.achievements import (
    check_achievements,
    get_level_for_xp,
    get_next_level,
    format_achievements,
    _check_condition,
    ACHIEVEMENTS_LIST,
    LEVEL_THRESHOLDS,
)
from core.progress import ProgressData


# --- Levels ---

def test_level_novice():
    name, emoji = get_level_for_xp(0)
    assert name == "Новичок"
    assert emoji == "🌱"


def test_level_student():
    name, emoji = get_level_for_xp(100)
    assert name == "Ученик"


def test_level_legend():
    name, emoji = get_level_for_xp(2500)
    assert name == "Легенда"
    assert emoji == "💎"


def test_next_level():
    name, needed = get_next_level(0)
    assert name == "Ученик"
    assert needed == 50


def test_next_level_max():
    name, needed = get_next_level(5000)
    assert name is None


# --- Condition checking ---

def test_condition_lessons():
    p = ProgressData(total_lessons=5)
    assert _check_condition("lessons >= 5", p) is True
    assert _check_condition("lessons >= 10", p) is False


def test_condition_accuracy():
    p = ProgressData(accuracy=85.0, total_turns=25)
    assert _check_condition("accuracy >= 80 and turns >= 20", p) is True
    assert _check_condition("accuracy >= 95 and turns >= 30", p) is False


def test_condition_streak():
    p = ProgressData(streak_days=7)
    assert _check_condition("streak >= 7", p) is True
    assert _check_condition("streak >= 14", p) is False


# --- Achievements ---

def test_first_lesson_earned():
    p = ProgressData(total_lessons=1)
    achs = check_achievements(p)
    first = next(a for a in achs if a.id == "first_lesson")
    assert first.earned is True


def test_first_lesson_not_earned():
    p = ProgressData(total_lessons=0)
    achs = check_achievements(p)
    first = next(a for a in achs if a.id == "first_lesson")
    assert first.earned is False


def test_streak_achievement():
    p = ProgressData(streak_days=3)
    achs = check_achievements(p)
    streak = next(a for a in achs if a.id == "streak_3")
    assert streak.earned is True


def test_xp_achievement():
    p = ProgressData(xp=100)
    achs = check_achievements(p)
    xp100 = next(a for a in achs if a.id == "xp_100")
    assert xp100.earned is True


def test_accuracy_achievement():
    p = ProgressData(accuracy=96.0, total_turns=35)
    achs = check_achievements(p)
    acc = next(a for a in achs if a.id == "accuracy_95")
    assert acc.earned is True


def test_all_achievements_count():
    assert len(ACHIEVEMENTS_LIST) == 15


# --- Format ---

def test_format_achievements():
    p = ProgressData(xp=100, total_lessons=1, correct=5, total_turns=10)
    achs = check_achievements(p)
    text = format_achievements(achs, p)
    assert "100" in text
    assert "Получены" in text
