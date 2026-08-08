from core.lessons import LessonContent, VocabWord, GrammarBlock
from core.models import Issue, PracticeResult
from storage.repo import Stats

from bot.formatters import (
    format_lesson_recap,
    format_lesson_step,
    format_lesson_task,
    format_practice_result,
    format_stats,
)


def test_format_correct_result():
    result = PracticeResult(
        is_correct=True,
        corrected_text="I went to school yesterday.",
        issues=[],
        next_question="What did you learn there?",
        tone="Отлично!",
    )
    text = format_practice_result(result)
    assert "✅ Верно!" in text
    assert "Отлично!" in text
    assert "I went to school yesterday." in text
    assert "What did you learn there?" in text
    assert "❌" not in text


def test_format_result_with_issues_escapes_html():
    result = PracticeResult(
        is_correct=False,
        corrected_text="I <went> yesterday",
        issues=[
            Issue(
                category="grammar",
                problem="неверное время",
                suggestion="используй Past Simple",
                correction="went",
            )
        ],
        next_question="What happened?",
        tone="",
    )
    text = format_practice_result(result)
    assert "❌ Есть ошибки: 1" in text
    assert "Грамматика" in text
    assert "неверное время" in text
    assert "используй Past Simple" in text
    assert "went" in text
    assert "I &lt;went&gt; yesterday" in text


def test_format_stats():
    stats = Stats(total_turns=4, correct=1, errors=3, top_categories=[("grammar", 3), ("vocabulary", 1)])
    text = format_stats(stats)
    assert "Всего реплик: 4" in text
    assert "Верных: 1" in text
    assert "С ошибками: 3" in text
    assert "Точность: 25%" in text
    assert "Грамматика — 3" in text
    assert "Словарный запас — 1" in text


def _sample_lesson() -> LessonContent:
    return LessonContent(
        topic="Travelling",
        intro="Let's talk about travelling!",
        vocabulary=[VocabWord("luggage", "багаж", "I packed my luggage.")],
        slides=["Book flights early.", "Pack light."],
        grammar=GrammarBlock("Past Simple", "прошлые действия", ["I flew to Spain."]),
        tasks=["What did you pack?", "Describe your best holiday."],
    )


def test_format_lesson_intro():
    text = format_lesson_step("intro", _sample_lesson())
    assert "Урок: Travelling" in text
    assert "Let's talk about travelling!" in text
    assert "План урока" in text


def test_format_lesson_vocabulary():
    text = format_lesson_step("vocabulary", _sample_lesson())
    assert "luggage" in text
    assert "багаж" in text
    assert "I packed my luggage." in text


def test_format_lesson_slides():
    text = format_lesson_step("slides", _sample_lesson())
    assert "Book flights early." in text
    assert "Pack light." in text


def test_format_lesson_grammar():
    text = format_lesson_step("grammar", _sample_lesson())
    assert "Past Simple" in text
    assert "прошлые действия" in text
    assert "I flew to Spain." in text


def test_format_lesson_task_indexed():
    text = format_lesson_task(_sample_lesson(), 1)
    assert "Задание 2 из 2" in text
    assert "Describe your best holiday." in text


def test_format_lesson_recap():
    text = format_lesson_recap(_sample_lesson())
    assert "Travelling" in text
    assert "luggage" in text
    assert "Past Simple" in text


def test_format_lesson_step_unknown_raises():
    import pytest

    with pytest.raises(ValueError):
        format_lesson_step("nope", _sample_lesson())
