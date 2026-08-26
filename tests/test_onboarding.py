"""Tests for Phase 13 — Onboarding flow."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from bot.handlers.onboarding import (
    _welcome_text,
    _level_text,
    _interests_text,
    _done_text,
    _level_keyboard,
    _interests_keyboard,
)


def test_welcome_text():
    text = _welcome_text("Алиса")
    assert "Алиса" in text
    assert "AI репетитор" in text


def test_level_text():
    text = _level_text()
    assert "уровень" in text.lower()


def test_interests_text():
    text = _interests_text()
    assert "интересны" in text.lower()


def test_done_text():
    text = _done_text()
    assert "готово" in text.lower()
    assert "урок" in text.lower()


def test_level_keyboard_has_levels():
    kb = _level_keyboard()
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    codes = [btn.callback_data.split(":")[-1] for btn in buttons]
    assert "A1" in codes
    assert "C1" in codes
    assert "skip" in codes


def test_interests_keyboard_has_interests():
    kb = _interests_keyboard()
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    codes = [btn.callback_data.split(":")[-1] for btn in buttons]
    assert "career" in codes
    assert "travel" in codes
    assert "done" in codes


def test_level_keyboard_count():
    kb = _level_keyboard()
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    assert len(buttons) == 6


def test_interests_keyboard_count():
    kb = _interests_keyboard()
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    assert len(buttons) == 11
