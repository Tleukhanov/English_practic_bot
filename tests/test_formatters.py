from core.diagnostic import DiagnosticAssessment, DiagnosticTask
from core.lessons import LessonContent, VocabWord, GrammarBlock
from core.models import Issue, PracticeResult
from storage.repo import Stats

from bot.formatters import (
    CEFR_LABELS_RU,
    format_diagnostic_question,
    format_lesson_recap,
    format_lesson_step,
    format_lesson_task,
    format_level_result,
    format_practice_result,
    format_practice_soft,
    format_profile,
    format_return_hook,
    format_reveal,
    format_stats,
)
from storage.repo import UserProfile


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


def test_format_stats_shows_level():
    stats = Stats(total_turns=0)
    text = format_stats(stats, level="B1")
    assert "Уровень: B1" in text
    assert CEFR_LABELS_RU["B1"] in text
    text = format_stats(stats)
    assert "Уровень" not in text


def test_format_practice_soft_hides_issues_on_correct():
    result = PracticeResult(
        is_correct=True,
        corrected_text="I went to school yesterday.",
        issues=[],
        next_question="What did you learn there?",
        tone="Отлично!",
    )
    text = format_practice_soft(result)
    assert "✅ Верно!" in text
    assert "Отлично!" in text
    assert "What did you learn there?" in text
    assert "Исправленный вариант" not in text
    assert "Показать ошибку" not in text


def test_format_practice_soft_offers_reveal_on_error():
    result = PracticeResult(
        is_correct=False,
        corrected_text="He <go> to school.",
        issues=[Issue(category="grammar", problem="время", suggestion="", correction="")],
        next_question="Where does he go?",
        tone="",
    )
    text = format_practice_soft(result)
    assert "Показать ошибку" in text
    assert "Where does he go?" in text
    assert "Есть ошибки" not in text
    assert "He &lt;go&gt; to school." not in text


def test_format_reveal_shows_correction_and_issues():
    issues = [
        {
            "category": "grammar",
            "problem": "неверное время",
            "suggestion": "используй Past Simple",
            "correction": "went",
        }
    ]
    text = format_reveal("I went to school yesterday.", issues)
    assert "Исправленный вариант" in text
    assert "I went to school yesterday." in text
    assert "Грамматика" in text
    assert "неверное время" in text
    assert "используй Past Simple" in text
    assert "<i>went</i>" in text


def test_format_reveal_escapes_html_and_handles_empty():
    text = format_reveal("<money> matters", [{"category": "x", "problem": "<bad>"}])
    assert "&lt;money&gt;" in text
    assert "&lt;bad&gt;" in text
    assert "Фраза была в порядке" not in text
    empty = format_reveal("", [])
    assert "Фраза была в порядке" in empty


def test_format_profile_filled():
    profile = UserProfile(
        user_id=1,
        goal="свободное общение",
        interests="chess, technology",
        weak_areas="Present Perfect",
        preferred_format="voice",
        notes="любит короткие объяснения",
    )
    text = format_profile(profile, level="B1")
    assert "Мой профиль" in text
    assert "B1" in text
    assert "свободное общение" in text
    assert "chess, technology" in text
    assert "Present Perfect" in text
    assert "голосовые тренировки" in text
    assert "любит короткие объяснения" in text


def test_format_profile_empty():
    text = format_profile(None, level=None)
    assert "ещё не определён" in text
    assert "расскажи, зачем учишь английский" in text


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
    assert "Обычный урок" in text
    assert "Travelling" in text
    assert "Let's talk about travelling!" in text
    assert "План урока" in text


def test_format_lesson_intro_shows_type_label():
    story = LessonContent(topic="The Space Trip", intro="A story about a trip!", lesson_type="story")
    text = format_lesson_step("intro", story)
    assert "Урок-история" in text
    assert "The Space Trip" in text


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


def test_format_return_hook_with_streak_and_due():
    text = format_return_hook(3, 5)
    assert "3 дня" in text
    assert "серия сгорит" in text
    assert "5 слов" in text
    assert "/review" in text


def test_format_return_hook_streak_one_no_due():
    text = format_return_hook(1, 0)
    assert "1 день" in text
    assert "слов" not in text.lower()


def test_format_return_hook_no_streak_with_due():
    text = format_return_hook(0, 2)
    assert "Отличный шаг" in text
    assert "2 слова" in text


def test_format_return_hook_pluralization():
    assert "11 слов" in format_return_hook(0, 11)
    assert "21 слово" in format_return_hook(0, 21)
    assert "5 дней" in format_return_hook(5, 0)


def test_format_lesson_step_unknown_raises():
    import pytest

    with pytest.raises(ValueError):
        format_lesson_step("nope", _sample_lesson())


# ---------- Диагностика уровня (Фаза 3) ----------

def test_format_diagnostic_question():
    task = DiagnosticTask(text="Introduce yourself and tell about your hobby.", level_hint="A1")
    text = format_diagnostic_question(task, 1, 6)
    assert "задание 1 из 6" in text
    assert "Introduce yourself" in text
    assert "Ответь по-английски" in text


def test_format_diagnostic_question_escapes_html():
    task = DiagnosticTask(text="Agree or disagree: <money> buys happiness.")
    text = format_diagnostic_question(task, 3, 6)
    assert "&lt;money&gt;" in text


def test_format_level_result():
    assessment = DiagnosticAssessment(
        level="B1",
        confidence=0.8,
        explanation_ru="уверенно строит сложные предложения, но путает времена",
        strengths=["good fluency"],
        weaknesses=["present perfect", "articles"],
        recommendation="повтори Present Perfect",
    )
    text = format_level_result(assessment)
    assert "B1" in text
    assert CEFR_LABELS_RU["B1"] in text
    assert "present perfect" in text
    assert "articles" in text
    assert "повтори Present Perfect" in text
    assert "⚠️" not in text


def test_format_level_result_estimated_note():
    assessment = DiagnosticAssessment(level="A2")
    text = format_level_result(assessment, estimated=True)
    assert "A2" in text
    assert "приблизительно" in text


def test_format_level_result_empty_assessment():
    assessment = DiagnosticAssessment(level="C1")
    text = format_level_result(assessment)
    assert "C1" in text
    assert CEFR_LABELS_RU["C1"] in text
