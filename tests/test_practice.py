import pytest

from core.practice import (
    PracticeParseError,
    build_prompt,
    parse_practice_response,
)


def test_parse_plain_json_with_issues():
    raw = (
        '{"is_correct": false, "corrected_text": "I went to the store yesterday.", '
        '"issues": [{"category": "grammar", "problem": "неверное время", '
        '"suggestion": "используй Past Simple", "correction": "went"}], '
        '"next_question": "What did you buy there?", '
        '"spoken_reply": "Nice! I went to the mall too, what did you buy there?", "tone": "Почти!"}'
    )
    result = parse_practice_response(raw)
    assert result.is_correct is False
    assert result.corrected_text == "I went to the store yesterday."
    assert result.next_question == "What did you buy there?"
    assert result.spoken_reply == "Nice! I went to the mall too, what did you buy there?"
    assert result.tone == "Почти!"
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.category == "grammar"
    assert issue.suggestion == "используй Past Simple"


def test_parse_json_in_code_fence():
    raw = '```json\n{"is_correct": true, "corrected_text": "Hello!", "issues": [], "next_question": "How are you?", "tone": ""}\n```'
    result = parse_practice_response(raw)
    assert result.is_correct is True
    assert result.issues == []
    assert result.corrected_text == "Hello!"


def test_parse_json_surrounded_by_text():
    raw = 'Вот ответ:\n{"is_correct": true, "corrected_text": "OK", "issues": [], "next_question": "What next?", "tone": "Отлично"}\nНадеюсь, помог!'
    result = parse_practice_response(raw)
    assert result.is_correct is True
    assert result.corrected_text == "OK"


def test_parse_missing_optional_fields_uses_defaults():
    result = parse_practice_response('{"corrected_text": "Hi"}')
    assert result.is_correct is True
    assert result.issues == []
    assert result.next_question == ""
    assert result.spoken_reply == ""


def test_parse_issue_without_all_fields():
    raw = '{"is_correct": false, "corrected_text": "X", "issues": [{"problem": "ошибка"}], "next_question": "?"}'
    result = parse_practice_response(raw)
    assert len(result.issues) == 1
    assert result.issues[0].category == ""
    assert result.issues[0].correction == ""


def test_parse_non_dict_issues_are_skipped():
    raw = '{"is_correct": false, "corrected_text": "X", "issues": [null, "oops", {"problem": "p"}], "next_question": "?"}'
    result = parse_practice_response(raw)
    assert len(result.issues) == 1


def test_parse_invalid_json_raises():
    with pytest.raises(PracticeParseError):
        parse_practice_response("просто текст без JSON")


def test_spoken_text_prefers_reply_over_question():
    from bot.handlers.voice import _spoken_text
    from core.models import PracticeResult

    result = PracticeResult(
        is_correct=True,
        corrected_text="Hello!",
        next_question="How are you?",
        spoken_reply="I'm great, thanks! What about you?",
    )
    assert _spoken_text(result) == "I'm great, thanks! What about you?"


def test_spoken_text_falls_back_to_next_question():
    from bot.handlers.voice import _spoken_text
    from core.models import PracticeResult

    result = PracticeResult(
        is_correct=True,
        corrected_text="Hello!",
        next_question="How are you?",
        spoken_reply="",
    )
    assert _spoken_text(result) == "How are you?"


def test_parse_empty_string_raises():
    with pytest.raises(PracticeParseError):
        parse_practice_response("")


def _non_system(messages):
    return [m for m in messages if m["role"] != "system"]


def test_build_prompt_includes_history_and_limits():
    history = [
        {"role": "user", "content": "one"},
        {"role": "assistant", "content": "two"},
        {"role": "user", "content": "three"},
    ]
    messages = build_prompt("four", history, max_history=2)
    assert messages[0]["role"] == "system"
    assert messages[-1]["role"] == "user"
    assert [m["content"] for m in _non_system(messages)] == ["two", "three", "four"]


def test_build_prompt_skips_bad_history_items():
    history = [{"role": "user", "content": ""}, {"role": "system", "content": "ignored"}, {"role": "user", "content": "ok"}]
    messages = build_prompt("last", history, max_history=10)
    assert [m["content"] for m in _non_system(messages)] == ["ok", "last"]


def test_build_prompt_includes_profile_snippet():
    messages = build_prompt("hi", [], profile="Student profile: Interests: chess; Goal: свободное общение.")
    system = messages[0]["content"]
    assert "Interests: chess" in system
    assert "weak areas" in system.lower()
