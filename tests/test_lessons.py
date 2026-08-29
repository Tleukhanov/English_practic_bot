import pytest

from bot.lessons import LESSON_STEPS, next_lesson_position
from core.lessons import (
    LESSON_TYPES,
    LessonParseError,
    LessonService,
    build_lesson_prompt,
    lesson_content_from_json,
    lesson_content_to_json,
    parse_lesson_response,
    parse_proposals_response,
)
from core.practice import PracticeParseError, parse_practice_response
from providers.base import LLMProvider

VALID_LESSON_JSON = """
```json
{
  "topic": "Travelling",
  "intro": "Let's talk about travelling!",
  "vocabulary": [
    {"word": "luggage", "translation": "багаж", "example": "I packed my luggage yesterday."},
    {"word": "flight", "translation": "перелёт", "example": "The flight was long."}
  ],
  "slides": ["Book flights early.", "Pack light."],
  "grammar": {
    "rule": "Past Simple",
    "explanation_ru": "используется для завершённых действий в прошлом",
    "examples": ["I flew to Spain last year."]
  },
  "tasks": ["What did you pack for your last trip?", "Describe your best holiday."]
}
```
"""


def test_parse_lesson_response():
    content = parse_lesson_response(VALID_LESSON_JSON)
    assert content.topic == "Travelling"
    assert content.intro == "Let's talk about travelling!"
    assert len(content.vocabulary) == 2
    assert content.vocabulary[0].word == "luggage"
    assert content.vocabulary[0].translation == "багаж"
    assert content.slides == ["Book flights early.", "Pack light."]
    assert content.grammar is not None
    assert content.grammar.rule == "Past Simple"
    assert content.grammar.examples == ["I flew to Spain last year."]
    assert len(content.tasks) == 2


def test_parse_lesson_response_missing_fields():
    content = parse_lesson_response('{"topic": "Chess"}')
    assert content.topic == "Chess"
    assert content.vocabulary == []
    assert content.slides == []
    assert content.grammar is None
    assert content.tasks == []
    assert content.lesson_type == "standard"


def test_parse_lesson_response_unknown_type_falls_back_to_standard():
    content = parse_lesson_response('{"topic": "Chess", "lesson_type": "weird"}')
    assert content.lesson_type == "standard"

    content = parse_lesson_response('{"topic": "Chess", "lesson_type": "STORY"}')
    assert content.lesson_type == "story"


def test_parse_lesson_response_invalid_raises():
    with pytest.raises(LessonParseError):
        parse_lesson_response("no json here")


def test_build_prompt_with_topic():
    messages = build_lesson_prompt("Chess")
    assert messages[0]["role"] == "system"
    assert "Chess" in messages[2]["content"]


def test_build_prompt_without_topic():
    messages = build_lesson_prompt(None)
    assert "choice" in messages[2]["content"]


def test_build_prompt_defaults_to_a1_level():
    messages = build_lesson_prompt("Chess")
    assert "beginner (A1)" in messages[0]["content"]


def test_build_prompt_with_level_a1():
    messages = build_lesson_prompt("Chess", level="A1")
    assert "beginner (A1)" in messages[0]["content"]
    assert "simple answers" in messages[0]["content"]


def test_build_prompt_with_level_c1():
    messages = build_lesson_prompt("Chess", level="C1")
    assert "advanced (C1)" in messages[0]["content"]
    assert "argue and explain" in messages[0]["content"]


def test_build_prompt_with_unknown_level_falls_back_to_a1():
    messages = build_lesson_prompt("Chess", level="X9")
    assert "beginner (A1)" in messages[0]["content"]


def test_build_prompt_with_profile():
    messages = build_lesson_prompt(None, profile="Student profile: Interests: chess; Weak areas: Present Perfect.")
    system = messages[0]["content"]
    assert "Interests: chess" in system
    assert "weak areas" in system.lower()


def test_lesson_content_json_roundtrip():
    content = parse_lesson_response(VALID_LESSON_JSON)
    restored = lesson_content_from_json(lesson_content_to_json(content))
    assert restored == content
    assert restored.vocabulary[1].word == "flight"


class FakeLLM(LLMProvider):
    def __init__(self, response: str):
        self._response = response
        self.last_temperature = None

    async def chat(self, messages, temperature=None, **kwargs):
        self.last_temperature = temperature
        return self._response


async def test_lesson_service_generates_and_parses():
    llm = FakeLLM(VALID_LESSON_JSON)
    service = LessonService(llm)
    content = await service.generate("Travelling")
    assert content.topic == "Travelling"
    assert len(content.tasks) == 2
    assert llm.last_temperature == 0.7


async def test_lesson_service_generates_with_lesson_type():
    llm = FakeLLM(VALID_LESSON_JSON.replace('"topic": "Travelling"', '"topic": "Travelling", "lesson_type": "story"'))
    service = LessonService(llm)
    content = await service.generate("Travelling", lesson_type="story")
    assert content.lesson_type == "story"


def test_build_prompt_injects_lesson_type():
    messages = build_lesson_prompt("Chess", lesson_type="quiz")
    system = messages[0]["content"]
    assert "Quiz-style lesson" in system
    assert '"quiz"' in system

    messages = build_lesson_prompt("Chess", lesson_type="story")
    assert "Build the lesson around a tiny story" in messages[0]["content"]

    assert set(LESSON_TYPES) == {"standard", "story", "dialogue", "quiz", "ideas"}


def test_lesson_type_json_roundtrip():
    content = parse_lesson_response('{"topic": "Travelling", "lesson_type": "story"}')
    restored = lesson_content_from_json(lesson_content_to_json(content))
    assert restored.lesson_type == "story"

    legacy = lesson_content_from_json('{"topic": "Travelling", "intro": "hi"}')
    assert legacy.lesson_type == "standard"


def test_practice_parse_error_alias_compat():
    with pytest.raises(PracticeParseError):
        parse_practice_response("garbage")


def test_next_position_advances_steps():
    assert LESSON_STEPS[0] == "intro"
    assert next_lesson_position(0, 0, 0) == (1, 0, False)
    assert next_lesson_position(1, 0, 0) == (2, 0, False)
    assert next_lesson_position(2, 0, 0) == (3, 0, False)


def test_next_position_tasks_sequence():
    assert LESSON_STEPS[4] == "tasks"
    assert next_lesson_position(4, 0, 2) == (4, 1, False)
    assert next_lesson_position(4, 1, 2) == (5, 0, False)


def test_next_position_last_step_finishes():
    assert LESSON_STEPS[5] == "recap"
    assert next_lesson_position(5, 0, 0) == (6, 0, True)


def test_build_prompt_with_recent_topics():
    messages = build_lesson_prompt(
        None,
        recent_topics=["Daily Routine", "Cooking", "Travelling"],
    )
    system = messages[0]["content"]
    assert "Daily Routine" in system
    assert "DO NOT repeat" in system
    assert "DIFFERENT" in system


def test_build_prompt_without_recent_topics():
    messages = build_lesson_prompt(None)
    system = messages[0]["content"]
    assert "DO NOT repeat" not in system


def test_build_prompt_profile_and_recent_topics():
    messages = build_lesson_prompt(
        None,
        profile="Student profile: Weak areas: Present Perfect.",
        recent_topics=["Daily Routine", "Cooking"],
    )
    system = messages[0]["content"]
    assert "Weak areas: Present Perfect" in system
    assert "Daily Routine" in system
    assert "DO NOT repeat" in system


def test_parse_proposals_response():
    raw = '[{"topic": "Cooking", "description": "Learn food vocabulary"}, {"topic": "Travel", "description": "Explore travel phrases"}, {"topic": "Sports", "description": "Sports vocabulary"}]'
    proposals = parse_proposals_response(raw)
    assert len(proposals) == 3
    assert proposals[0]["topic"] == "Cooking"
    assert proposals[1]["description"] == "Explore travel phrases"


def test_parse_proposals_response_with_markdown():
    raw = '```json\n[{"topic": "Chess", "description": "Шахматы на английском"}, {"topic": "Music", "description": "Музыкальная лексика"}]\n```'
    proposals = parse_proposals_response(raw)
    assert len(proposals) == 2
    assert proposals[0]["topic"] == "Chess"


def test_parse_proposals_response_invalid():
    with pytest.raises(LessonParseError):
        parse_proposals_response("not json")


async def test_lesson_service_generate_proposals():
    response = '[{"topic": "AI", "description": "Обсудим будущее ИИ"}, {"topic": "Cooking", "description": "Кулинарная лексика"}, {"topic": "Space", "description": "Космос и звёзды"}]'
    llm = FakeLLM(response)
    service = LessonService(llm)
    proposals = await service.generate_proposals(level="B1")
    assert len(proposals) == 3
    assert proposals[0]["topic"] == "AI"
    assert llm.last_temperature == 0.8
