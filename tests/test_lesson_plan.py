import pytest

from core.json_utils import JsonParseError
from core.lesson_plan import (
    LessonPlan,
    LessonPlanService,
    build_plan_prompt,
    next_plan_index,
    parse_plan_response,
)
from providers.base import LLMProvider

VALID_PLAN_JSON = (
    '{"goal": "Уверенно говорить о путешествиях", "lessons": ['
    '{"number": 1, "topic": "At the airport", "focus": "check-in vocabulary", "reason": "easy, practical start"},'
    '{"number": 2, "topic": "Booking a hotel", "focus": "reservation phrases", "reason": "builds on travel vocab"}]}'
)


def test_parse_valid_plan():
    plan = parse_plan_response(VALID_PLAN_JSON)
    assert plan.goal == "Уверенно говорить о путешествиях"
    assert len(plan.lessons) == 2
    assert plan.lessons[0].number == 1
    assert plan.lessons[0].topic == "At the airport"
    assert plan.lessons[0].focus == "check-in vocabulary"
    assert plan.lessons[0].reason == "easy, practical start"


def test_parse_plan_defaults_missing_fields():
    plan = parse_plan_response('{"goal": "g", "lessons": [{"number": 1, "topic": "Chess"}]}')
    assert plan.lessons[0].number == 1
    assert plan.lessons[0].topic == "Chess"
    assert plan.lessons[0].focus == ""
    assert plan.lessons[0].reason == ""


def test_parse_plan_invalid_raises():
    with pytest.raises(JsonParseError):
        parse_plan_response("no json here")


def test_parse_plan_skips_non_dict_items():
    raw = '{"goal": "g", "lessons": [{"number": 1, "topic": "Topic1"}, "junk", 42, null]}'
    plan = parse_plan_response(raw)
    assert len(plan.lessons) == 1
    assert plan.lessons[0].topic == "Topic1"


def test_plan_json_roundtrip():
    plan = parse_plan_response(VALID_PLAN_JSON)
    restored = LessonPlan.from_json(plan.to_json())
    assert restored == plan


def test_plan_from_json_empty():
    plan = LessonPlan.from_json("")
    assert plan.goal == ""
    assert plan.lessons == []


def test_plan_from_json_broken():
    plan = LessonPlan.from_json("{broken")
    assert plan.goal == ""
    assert plan.lessons == []


def test_next_plan_index():
    assert next_plan_index(12, 12, 12) == 0
    assert next_plan_index(12, 23, 12) == 11
    assert next_plan_index(12, 24, 12) is None
    assert next_plan_index(12, 11, 12) is None


def test_build_plan_prompt_messages():
    messages = build_plan_prompt("A2", "Interests: cooking", ["Food", "Cooking"], 12)
    assert len(messages) == 3
    assert messages[0]["role"] == "system"
    assert "12" in messages[0]["content"]
    assert "CRITICAL FORMAT RULE" in messages[1]["content"]
    assert messages[2]["role"] == "user"
    assert "Food" in messages[0]["content"]
    assert "Interests: cooking" in messages[0]["content"]
    assert messages[0]["content"].startswith("You are an English teacher")


class FakeLLM(LLMProvider):
    def __init__(self, response: str):
        self.response = response
        self.last_messages = None
        self.last_temperature = None
        self.last_json_mode = None

    async def chat(self, messages, temperature=None, json_mode=False, **kwargs):
        self.last_messages = messages
        self.last_temperature = temperature
        self.last_json_mode = json_mode
        return self.response


async def test_service_generates_parses_plan():
    llm = FakeLLM(VALID_PLAN_JSON)
    service = LessonPlanService(llm)
    plan = await service.generate(
        level="B1",
        profile="Interests: travel",
        recent_topics=["Daily Routine"],
        completed_lessons=24,
    )
    assert plan.goal == "Уверенно говорить о путешествиях"
    assert len(plan.lessons) == 2
    assert llm.last_temperature == 0.7
    assert llm.last_json_mode is True
    prompt_text = " ".join(m["content"] for m in llm.last_messages)
    assert "B1" in prompt_text
    assert "Interests: travel" in prompt_text
    assert "Daily Routine" in prompt_text
    assert "24" in prompt_text