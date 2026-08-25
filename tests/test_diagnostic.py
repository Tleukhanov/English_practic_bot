"""Тесты ядра диагностики уровня (Фаза 3): парсеры, эвристика, сервис на мок-LLM."""

import pytest

from core.diagnostic import (
    CEFR_LEVELS,
    DiagnosticParseError,
    DiagnosticService,
    DiagnosticTask,
    build_assessment_prompt,
    build_diagnostic_prompt,
    diagnostic_tasks_from_json,
    diagnostic_tasks_to_json,
    estimate_level_heuristic,
    parse_assessment,
    parse_diagnostic_tasks,
)
from providers.base import LLMProvider

VALID_TASKS_JSON = """
```json
{
  "tasks": [
    {"text": "Introduce yourself. What is your name and where are you from?", "level_hint": "A1"},
    {"text": "Describe your typical day.", "level_hint": "A2"},
    {"text": "What do you think about living in a big city?", "level_hint": "B1"},
    {"text": "Tell me about a trip you remember well.", "level_hint": "B1"},
    {"text": "What are the pros and cons of remote work?", "level_hint": "B2"},
    {"text": "Some people say money buys happiness. Do you agree?", "level_hint": "C1"}
  ]
}
```
"""

VALID_ASSESSMENT_JSON = """{
  "level": "B1",
  "confidence": 0.8,
  "explanation_ru": "уверенно строит сложные предложения, но путает времена",
  "strengths": ["good fluency", "wide vocabulary"],
  "weaknesses": ["present perfect", "articles"],
  "recommendation": "повтори Present Perfect и артикли"
}
"""


def test_parse_diagnostic_tasks():
    tasks = parse_diagnostic_tasks(VALID_TASKS_JSON)
    assert len(tasks) == 6
    assert tasks[0].text.startswith("Introduce")
    assert tasks[0].level_hint == "A1"
    assert tasks[-1].level_hint == "C1"


def test_parse_diagnostic_tasks_missing_fields():
    assert parse_diagnostic_tasks('{"tasks": []}') == []
    assert parse_diagnostic_tasks('{"tasks": [{"text": "x"}]}')[0].level_hint == ""


def test_parse_diagnostic_tasks_invalid_raises():
    with pytest.raises(DiagnosticParseError):
        parse_diagnostic_tasks("no json")


def test_build_diagnostic_prompt():
    messages = build_diagnostic_prompt()
    assert messages[0]["role"] == "system"
    assert "A1" in messages[0]["content"] or "ladder" in messages[0]["content"]


def test_parse_assessment():
    assessment = parse_assessment(VALID_ASSESSMENT_JSON)
    assert assessment.level == "B1"
    assert assessment.confidence == 0.8
    assert any("fluency" in s for s in assessment.strengths)
    assert any("present perfect" in s for s in assessment.weaknesses)
    assert assessment.recommendation


def test_parse_assessment_invalid_level_normalizes_to_b1():
    assessment = parse_assessment('{"level": "X9", "confidence": 0.9}')
    assert assessment.level == "B1"
    assert assessment.confidence == 0.9


def test_parse_assessment_missing_confidence_defaults_zero():
    assessment = parse_assessment('{"level": "A2"}')
    assert assessment.confidence == 0.0


def test_parse_assessment_lowercase_level_normalized():
    assert parse_assessment('{"level": "c1"}').level == "C1"


def test_assessment_prompt_contains_dialogue():
    questions = [
        DiagnosticTask(text="Introduce yourself", level_hint="A1"),
        DiagnosticTask(text="Your plans?", level_hint="B1"),
    ]
    messages = build_assessment_prompt(questions, ["Hi, I'm Anna.", "I plan to travel."])
    assert "Introduce yourself" in messages[1]["content"]
    assert "Hi, I'm Anna." in messages[1]["content"]
    assert "no answer" in build_assessment_prompt(questions, ["only one"])[1]["content"]


def test_tasks_json_roundtrip():
    tasks = parse_diagnostic_tasks(VALID_TASKS_JSON)
    restored = diagnostic_tasks_from_json(diagnostic_tasks_to_json(tasks))
    assert restored == tasks


def test_estimate_level_heuristic():
    assert estimate_level_heuristic([]) == "B1"
    assert estimate_level_heuristic(["hi", "fine", "ok"]) == "A1"
    assert estimate_level_heuristic(["My name is Anna and I am from Moscow. I like music and books."]) == "A2"
    long_simple = ["I like to travel because it is interesting. I often go to other countries with my friends."]
    assert estimate_level_heuristic(long_simple) == "B1"
    advanced = [
        "Although the weather was particularly bad, we nevertheless continued our journey without any hesitation. "
        "Therefore we arrived much later than we expected, but despite that we were nevertheless satisfied with the outcome."
    ]
    assert estimate_level_heuristic(advanced) == "B2"


class FakeLLM(LLMProvider):
    def __init__(self, response: str):
        self._response = response
        self.last_temperature = None

    async def chat(self, messages, temperature=None, **kwargs):
        self.last_temperature = temperature
        return self._response


async def test_diagnostic_service_generates_tasks():
    llm = FakeLLM(VALID_TASKS_JSON)
    service = DiagnosticService(llm)
    tasks = await service.generate_tasks()
    assert len(tasks) == 6
    assert llm.last_temperature == 0.7


async def test_diagnostic_service_assess():
    llm = FakeLLM(VALID_ASSESSMENT_JSON)
    service = DiagnosticService(llm)
    questions = parse_diagnostic_tasks(VALID_TASKS_JSON)
    assessment = await service.assess(questions, ["Hi", "I am fine"])
    assert assessment.level == "B1"
    assert llm.last_temperature == 0.0


def test_cefr_levels_order():
    assert CEFR_LEVELS == ["A1", "A2", "B1", "B2", "C1"]
