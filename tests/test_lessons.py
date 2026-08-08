import pytest

from core.lessons import (
    LessonParseError,
    LessonService,
    build_lesson_prompt,
    lesson_content_from_json,
    lesson_content_to_json,
    parse_lesson_response,
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


def test_parse_lesson_response_invalid_raises():
    with pytest.raises(LessonParseError):
        parse_lesson_response("no json here")


def test_build_prompt_with_topic():
    messages = build_lesson_prompt("Chess")
    assert messages[0]["role"] == "system"
    assert "Chess" in messages[1]["content"]


def test_build_prompt_without_topic():
    messages = build_lesson_prompt(None)
    assert "choice" in messages[1]["content"]


def test_lesson_content_json_roundtrip():
    content = parse_lesson_response(VALID_LESSON_JSON)
    restored = lesson_content_from_json(lesson_content_to_json(content))
    assert restored == content
    assert restored.vocabulary[1].word == "flight"


class FakeLLM(LLMProvider):
    def __init__(self, response: str):
        self._response = response
        self.last_temperature = None

    async def chat(self, messages, temperature=None):
        self.last_temperature = temperature
        return self._response


async def test_lesson_service_generates_and_parses():
    llm = FakeLLM(VALID_LESSON_JSON)
    service = LessonService(llm)
    content = await service.generate("Travelling")
    assert content.topic == "Travelling"
    assert len(content.tasks) == 2
    assert llm.last_temperature == 0.7


def test_practice_parse_error_alias_compat():
    with pytest.raises(PracticeParseError):
        parse_practice_response("garbage")
