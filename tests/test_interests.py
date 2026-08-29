"""Tests for Phase 7 — /interests command and topic proposals with interests."""

import pytest
from unittest.mock import AsyncMock
from datetime import datetime, timezone

from bot.handlers.interests import (
    _parse_interests,
    _format_interests,
    PREDEFINED_INTERESTS,
    ONBOARDING_INTEREST_BY_CODE,
)
from core.lessons import _render_proposals_prompt


# --- parse / format ---

def test_parse_empty_string():
    assert _parse_interests("") == set()


def test_parse_comma_separated():
    assert _parse_interests("Games, Music") == {"Games", "Music"}


def test_parse_strips_whitespace():
    assert _parse_interests("  Games ,  Music  ") == {"Games", "Music"}


def test_format_empty():
    assert _format_interests(set()) == ""


def test_format_sorted():
    result = _format_interests({"Music", "Games", "Sports"})
    assert result == "Games, Music, Sports"


def test_format_on_plain_string_does_not_split_characters():
    result = _format_interests(_parse_interests("Games, Music"))
    assert result == "Games, Music"


def test_onboarding_codes_map_to_known_names():
    for code, name in ONBOARDING_INTEREST_BY_CODE.items():
        known = {n for _, n in PREDEFINED_INTERESTS}
        assert name in known, f"code={code!r} -> {name!r} отсутствует в /interests"


def test_predefined_interests_count():
    assert len(PREDEFINED_INTERESTS) == 13


def test_predefined_interests_unique_names():
    names = [name for _, name in PREDEFINED_INTERESTS]
    assert len(names) == len(set(names))


# --- proposals prompt with interests ---

def test_proposals_prompt_includes_interests():
    profile = "Interests: Games, Programming / AI. Goal: свободное общение."
    prompt = _render_proposals_prompt(profile=profile)
    assert "Games" in prompt
    assert "Programming / AI" in prompt


def test_proposals_prompt_prioritizes_interests():
    profile = "Interests: Music. Goal: свободное общение."
    prompt = _render_proposals_prompt(profile=profile)
    assert "interests" in prompt.lower() or "Interests" in prompt


def test_proposals_prompt_avoids_recent_topics():
    recent = ["Chess", "Cooking"]
    prompt = _render_proposals_prompt(recent_topics=recent)
    assert "Chess" in prompt
    assert "Cooking" in prompt


def test_proposals_prompt_with_level():
    prompt = _render_proposals_prompt(level="A1", profile="Interests: Sports.")
    assert "A1" in prompt
    assert "Sports" in prompt
