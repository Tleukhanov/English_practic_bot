"""Tests for Phase 10 — ProgressService."""

import pytest
from core.progress import (
    ProgressService,
    ProgressData,
    format_progress,
)


def test_xp_calculation():
    assert ProgressService._calculate_xp(0, 0, 0) == 0
    assert ProgressService._calculate_xp(1, 0, 0) == 10
    assert ProgressService._calculate_xp(0, 5, 0) == 25
    assert ProgressService._calculate_xp(0, 0, 5) == 0
    assert ProgressService._calculate_xp(1, 3, 1) == 23
    assert ProgressService._calculate_xp(0, 0, 10) == 0


def test_weak_areas_from_notes():
    from storage.repo import LessonNote

    notes = [
        LessonNote(mistakes="Past Simple, Present Simple"),
        LessonNote(mistakes="Past Simple"),
        LessonNote(mistakes="Past Perfect"),
    ]
    areas = ProgressService._get_weak_areas(notes)
    assert areas[0] == "Past Simple"
    assert "Present Simple" in areas


def test_weak_areas_empty():
    assert ProgressService._get_weak_areas([]) == []


def test_strong_areas_from_notes():
    from storage.repo import LessonNote

    notes = [
        LessonNote(topic="Chess", mistakes=""),
        LessonNote(topic="Music", mistakes="Past Simple"),
        LessonNote(topic="Cooking", mistakes=""),
    ]
    strong = ProgressService._get_strong_areas(notes)
    assert "Chess" in strong
    assert "Cooking" in strong
    assert "Music" not in strong


def test_strong_areas_empty():
    assert ProgressService._get_strong_areas([]) == []


def test_format_progress_basic():
    p = ProgressData(level="B1", total_lessons=5, total_turns=20, correct=15, errors=5, xp=75)
    text = format_progress(p)
    assert "B1" in text
    assert "5" in text  # lessons
    assert "20" in text  # turns
    assert "75" in text  # xp


def test_format_progress_with_weak_areas():
    p = ProgressData(level="A2", weak_areas=["Past Simple", "Present Perfect"])
    text = format_progress(p)
    assert "Past Simple" in text
    assert "Present Perfect" in text


def test_format_progress_with_character():
    p = ProgressData(level="B2", character="toxic")
    text = format_progress(p)
    assert "toxic" in text


def test_format_progress_with_interests():
    p = ProgressData(level="A1", interests="Games, Music")
    text = format_progress(p)
    assert "Games" in text
    assert "Music" in text


def test_accuracy_zero_turns():
    p = ProgressData(total_turns=0, correct=0, errors=0)
    assert p.accuracy == 0.0
