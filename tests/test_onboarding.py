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
    cb_onb_interest,
)
from bot.quota import QUOTA_EXCEEDED_TEXT, QuotaExceeded


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


class FakeUser:
    id = 1
    username = "alice"
    first_name = "Alice"


class FakeMessage:
    def __init__(self):
        self.answers = []
        self.edits = []

    async def answer(self, text, reply_markup=None):
        self.answers.append((text, reply_markup))

    async def edit_text(self, text, reply_markup=None):
        self.edits.append((text, reply_markup))


class FakeCallback:
    def __init__(self, data: str):
        self.data = data
        self.from_user = FakeUser()
        self.message = FakeMessage()
        self.answered = []

    async def answer(self, text=None, show_alert=None):
        self.answered.append(text)


class FakeQuota:
    def __init__(self, *, exhausted=False):
        self.exhausted = exhausted
        self.checked = []

    async def check(self, user_id):
        self.checked.append(user_id)
        if self.exhausted:
            raise QuotaExceeded("квота исчерпана")

    async def consume(self, user_id, *, cost=1):
        pass


async def test_done_quota_exhausted_blocks_lesson(monkeypatch):
    cb = FakeCallback("onb:interest:done")
    quota = FakeQuota(exhausted=True)
    calls = []

    async def fake_start(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr("bot.lessons._start_lesson", fake_start)
    await cb_onb_interest(cb, MagicMock(), MagicMock(), quota)

    assert calls == []
    assert quota.checked == [1]
    text, kb = cb.message.edits[-1]
    assert text == QUOTA_EXCEEDED_TEXT
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    assert any(btn.callback_data.startswith("premium:buy:") for btn in buttons)


async def test_done_passes_valid_quota_to_start_lesson(monkeypatch):
    cb = FakeCallback("onb:interest:done")
    quota = FakeQuota()
    recorded = {}

    async def fake_start(target, repo, lesson_service, topic, user_from, quota=None):
        recorded["quota"] = quota
        recorded["topic"] = topic

    monkeypatch.setattr("bot.lessons._start_lesson", fake_start)
    await cb_onb_interest(cb, MagicMock(), MagicMock(), quota)

    assert quota.checked == [1]
    assert recorded["quota"] is quota
    assert recorded["topic"] is None
    text, _ = cb.message.edits[0]
    assert "готово" in text.lower()
