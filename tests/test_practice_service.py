import pytest

from core.practice import PracticeParseError, PracticeService
from providers.base import LLMProvider


class FakeLLM(LLMProvider):
    def __init__(self, response: str):
        self._response = response
        self.last_messages: list[dict[str, str]] = []

    async def chat(self, messages, temperature=None):
        self.last_messages = messages
        return self._response


async def test_practice_service_parses_llm_response():
    llm = FakeLLM(
        '{"is_correct": false, "corrected_text": "I went home.", '
        '"issues": [{"category": "grammar", "problem": "ошибка", "suggestion": "так лучше", "correction": "went"}], '
        '"next_question": "And then?", "tone": ""}'
    )
    service = PracticeService(llm)
    result = await service.analyze("I goed home", [])
    assert result.is_correct is False
    assert result.corrected_text == "I went home."
    assert len(result.issues) == 1


async def test_practice_service_passes_history_to_llm():
    llm = FakeLLM('{"is_correct": true, "corrected_text": "OK", "issues": [], "next_question": "", "tone": ""}')
    service = PracticeService(llm)
    history = [{"role": "user", "content": "previous"}]
    await service.analyze("current", history)
    assert llm.last_messages[0]["role"] == "system"
    assert llm.last_messages[-1] == {"role": "user", "content": "current"}


async def test_practice_service_raises_on_garbage():
    llm = FakeLLM("I'm sorry, I can't do that.")
    service = PracticeService(llm)
    with pytest.raises(PracticeParseError):
        await service.analyze("hello", [])
