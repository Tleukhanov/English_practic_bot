import pytest

from core.lesson_notes import (
    LessonNoteParseError,
    LessonNoteService,
    build_note_prompt,
    parse_note_response,
)
from core.lessons import GrammarBlock, LessonContent
from providers.base import LLMProvider


def _lesson() -> LessonContent:
    return LessonContent(
        topic="Cooking",
        intro="Let's cook!",
        vocabulary=[],
        grammar=GrammarBlock("Present Simple", "привычки", ["I cook every day."]),
        tasks=["What do you cook?"],
    )


def test_build_note_prompt_includes_content_and_answers():
    answers = [
        {
            "content": "I cook every day",
            "is_correct": False,
            "corrected_text": "I cook every day.",
            "issues_json": '[{"category": "grammar", "problem": "артикль"}]',
        }
    ]
    messages = build_note_prompt(_lesson(), answers)
    assert messages[0]["role"] == "system"
    combined = messages[1]["content"]
    assert "Cooking" in combined
    assert "Present Simple" in combined
    assert "I cook every day" in combined
    assert "артикль" in combined


def test_build_note_prompt_without_answers():
    messages = build_note_prompt(_lesson(), [])
    assert "студент не отвечал" in messages[1]["content"]


def test_parse_note_response():
    raw = (
        '{"vocabulary": "+7 слов, использовал: brew", "grammar": "Present Simple — ок", '
        '"speaking": "улучшение", "mistakes": "артикли", "recommendation": "повторить артикли"}'
    )
    fields = parse_note_response(raw)
    assert fields["vocabulary"] == "+7 слов, использовал: brew"
    assert fields["grammar"] == "Present Simple — ок"
    assert fields["mistakes"] == "артикли"
    assert fields["recommendation"] == "повторить артикли"


def test_parse_note_response_defaults():
    fields = parse_note_response('{"vocabulary": "x"}')
    assert fields["grammar"] == ""
    assert fields["speaking"] == ""


def test_parse_note_response_invalid_raises():
    with pytest.raises(LessonNoteParseError):
        parse_note_response("no json here")


class FakeLLM(LLMProvider):
    def __init__(self, response: str):
        self._response = response
        self.last_temperature = None

    async def chat(self, messages, temperature=None):
        self.last_temperature = temperature
        return self._response


async def test_note_service_generates_and_parses():
    llm = FakeLLM(
        '{"vocabulary": "+5 слов", "grammar": "Present Simple — слабое место", '
        '"speaking": "ок", "mistakes": "артикли", "recommendation": "повторить Present Simple"}'
    )
    service = LessonNoteService(llm)
    note = await service.generate(
        user_id=5,
        lesson_id=3,
        content=_lesson(),
        answers=[{"content": "I cook", "is_correct": False, "corrected_text": "", "issues_json": ""}],
    )
    assert note.user_id == 5
    assert note.lesson_id == 3
    assert note.topic == "Cooking"
    assert note.vocabulary == "+5 слов"
    assert note.mistakes == "артикли"
    assert note.recommendation == "повторить Present Simple"
    assert note.created_at
    assert llm.last_temperature == 0.2
