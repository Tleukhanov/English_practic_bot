from core.models import Issue, PracticeResult
from storage.repo import Stats

from bot.formatters import format_practice_result, format_stats


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
