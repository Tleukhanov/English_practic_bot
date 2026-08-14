from datetime import datetime, timedelta, timezone

import pytest

from core.profile import (
    EXTRACT_SYSTEM_PROMPT,
    ProfileParseError,
    ProfileService,
    build_extract_prompt,
    parse_profile_update,
    profile_update_due,
    to_profile_snippet,
)
from providers.base import LLMProvider
from storage.repo import UserProfile


def test_to_profile_snippet_none_and_empty():
    assert to_profile_snippet(None) == ""
    assert to_profile_snippet(UserProfile(user_id=1)) == ""


def test_to_profile_snippet_full():
    profile = UserProfile(
        user_id=1,
        goal="свободное общение",
        interests="chess, technology",
        weak_areas="Present Perfect, артикли",
        preferred_format="voice",
        notes="любит короткие объяснения",
    )
    text = to_profile_snippet(profile)
    assert "Goal: свободное общение" in text
    assert "Interests: chess, technology" in text
    assert "Weak areas: Present Perfect, артикли" in text
    assert "Prefers voice practice" in text
    assert "Note: любит короткие объяснения" in text


def test_build_extract_prompt_includes_context():
    previous = UserProfile(user_id=1, interests="chess")
    dialogue = [
        {"role": "user", "content": "I like playing chess"},
        {"role": "assistant", "content": "Nice! Try: I like playing chess."},
    ]
    messages = build_extract_prompt(previous, dialogue)
    assert messages[0]["role"] == "system"
    assert EXTRACT_SYSTEM_PROMPT in messages[0]["content"]
    combined = messages[1]["content"]
    assert "Interests: chess" in combined
    assert "I like playing chess" in combined


def test_parse_profile_update_valid():
    raw = '{"goal": "работа", "interests": "travel, movies", "weak_areas": "articles", "preferred_format": "voice", "notes": "любит голос"}'
    update = parse_profile_update(raw)
    assert update["goal"] == "работа"
    assert update["interests"] == "travel, movies"
    assert update["weak_areas"] == "articles"
    assert update["preferred_format"] == "voice"
    assert update["notes"] == "любит голос"


def test_parse_profile_update_defaults_and_format_validation():
    update = parse_profile_update('{"goal": "", "preferred_format": "singing"}')
    assert update["goal"] == ""
    assert update["preferred_format"] == ""


def test_parse_profile_update_invalid_json_raises():
    with pytest.raises(ProfileParseError):
        parse_profile_update("no json here")


def test_profile_update_due():
    now = datetime.now(timezone.utc)
    assert profile_update_due(None, now=now) is True
    assert profile_update_due(UserProfile(user_id=1, updated_at=""), now=now) is True
    fresh = UserProfile(user_id=1, updated_at=now.isoformat())
    assert profile_update_due(fresh, now=now) is False
    stale = UserProfile(user_id=1, updated_at=(now - timedelta(hours=2)).isoformat())
    assert profile_update_due(stale, now=now) is True
    assert profile_update_due(UserProfile(user_id=1, updated_at="garbage"), now=now) is True


class FakeLLM(LLMProvider):
    def __init__(self, response: str):
        self._response = response
        self.last_temperature = None

    async def chat(self, messages, temperature=None):
        self.last_temperature = temperature
        return self._response


async def test_profile_service_updates_and_merges():
    llm = FakeLLM(
        '{"goal": "работа в IT", "interests": "programming", "weak_areas": "", '
        '"preferred_format": "", "notes": ""}'
    )
    service = ProfileService(llm)
    previous = UserProfile(
        user_id=7,
        goal="",
        interests="chess",
        weak_areas="Present Perfect",
        notes="любит короткие объяснения",
    )
    updated = await service.update(7, previous, [{"role": "user", "content": "I work in IT"}])

    assert updated.user_id == 7
    assert updated.goal == "работа в IT"
    assert updated.interests == "programming"
    assert updated.weak_areas == "Present Perfect"
    assert updated.notes == "любит короткие объяснения"
    assert updated.preferred_format == ""
    assert llm.last_temperature == 0.0


async def test_profile_service_from_scratch():
    llm = FakeLLM('{"goal": "путешествия", "interests": "", "weak_areas": "", "preferred_format": "", "notes": ""}')
    service = ProfileService(llm)
    updated = await service.update(3, None, [{"role": "user", "content": "I want to travel"}])
    assert updated.goal == "путешествия"
    assert updated.interests == ""
    assert updated.user_id == 3
