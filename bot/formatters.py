"""Форматирование ответов для пользователя."""

from __future__ import annotations

from core.diagnostic import DiagnosticAssessment, DiagnosticTask
from core.lessons import LESSON_STEPS, LessonContent
from core.models import PracticeResult
from storage.repo import Stats

from .utils import escape

CATEGORY_LABELS = {
    "grammar": "Грамматика",
    "vocabulary": "Словарный запас",
    "pronunciation": "Произношение",
    "style": "Стиль",
    "word_order": "Порядок слов",
}


def _bold(text: str, html: bool = True) -> str:
    return f"<b>{text}</b>" if html else f"**{text}**"


def format_practice_result(result: PracticeResult, html: bool = True) -> str:
    parts: list[str] = []

    if result.is_correct:
        verdict = "✅ Верно!"
    else:
        verdict = f"❌ Есть ошибки: {len(result.issues)}"
    if result.tone:
        verdict += f" {result.tone}"
    parts.append(verdict)

    if result.issues:
        parts.append("")
        for index, issue in enumerate(result.issues, start=1):
            category = CATEGORY_LABELS.get(issue.category, issue.category or "Ошибка")
            line = f"{index}. {_bold(category, html)}: {escape(issue.problem)}"
            if issue.suggestion:
                line += f"\n   Как исправить: {escape(issue.suggestion)}"
            if issue.correction:
                suffix = f"<i>{escape(issue.correction)}</i>" if html else escape(issue.correction)
                line += f"\n   Правильно: {suffix}"
            parts.append(line)

    if result.corrected_text:
        parts.append("")
        parts.append(f"📝 {_bold('Исправленный вариант:', html)}\n{escape(result.corrected_text)}")

    if result.next_question:
        parts.append("")
        parts.append(f"💬 {escape(result.next_question)}")

    return "\n".join(parts)


def format_practice_soft(result: PracticeResult) -> str:
    """Короткий дружелюбный ответ: без тыканья в ошибки.

    При ошибке — мягкая подсказка и кнопка «Показать ошибку» (см. format_reveal).
    """
    if result.is_correct:
        verdict = "✅ Верно!"
        if result.tone:
            verdict += f" {result.tone}"
        parts = [verdict]
        if result.next_question:
            parts += ["", f"💬 {escape(result.next_question)}"]
        return "\n".join(parts)

    parts = ["❗ Хм, кажется, в этой фразе есть небольшая ошибка 🤏"]
    if result.next_question:
        parts += ["", f"💬 {escape(result.next_question)}"]
    parts += ["", "Нажми «🔍 Показать ошибку», чтобы увидеть, как сказать правильно."]
    return "\n".join(parts)


def format_reveal(corrected_text: str, issues: list[dict]) -> str:
    """Подробный разбор по кнопке «Показать ошибку»: исправленный вариант и ошибки."""
    lines: list[str] = []
    if corrected_text:
        lines.append(f"📝 {_bold('Исправленный вариант:')}")
        lines.append(escape(corrected_text))
        lines.append("")

    if issues:
        for index, issue in enumerate(issues, start=1):
            category = CATEGORY_LABELS.get(str(issue.get("category", "")), str(issue.get("category", "")) or "Ошибка")
            line = f"{index}. {_bold(category)}: {escape(str(issue.get('problem', '')))}"
            if issue.get("suggestion"):
                line += f"\n   Как исправить: {escape(str(issue['suggestion']))}"
            if issue.get("correction"):
                line += f"\n   Правильно: <i>{escape(str(issue['correction']))}</i>"
            lines.append(line)
    else:
        lines.append("Фраза была в порядке 🙂")

    return "\n".join(lines)


def format_stats(stats: Stats, html: bool = True, level: str | None = None) -> str:
    lines = [_bold("Твоя статистика:", html), ""]
    if level:
        label = CEFR_LABELS_RU.get(level, level)
        lines.append(f"🎯 Уровень: {level} — {label}")
    lines.append(f"✍️ Всего реплик: {stats.total_turns}")
    lines.append(f"✅ Верных: {stats.correct}")
    lines.append(f"❌ С ошибками: {stats.errors}")
    if stats.total_turns:
        accuracy = stats.correct / stats.total_turns * 100
        lines.append(f"🎯 Точность: {accuracy:.0f}%")
    if stats.top_categories:
        lines.append("")
        lines.append("Частые типы ошибок:")
        for category, count in stats.top_categories:
            label = CATEGORY_LABELS.get(category, category)
            lines.append(f"  • {label} — {count}")
    return "\n".join(lines)


# ---------- Уроки (Фаза 1) ----------

def format_lesson_intro(content: LessonContent) -> str:
    parts = [
        _bold(f"📚 Урок: {escape(content.topic)}"),
        "",
        escape(content.intro),
        "",
        "План урока:",
        "  1️⃣ Новые слова",
        "  2️⃣ Ключевые идеи",
        "  3️⃣ Грамматика",
        "  4️⃣ Задания и практика",
        "",
        "Нажми «➡️ Дальше», когда будешь готов.",
    ]
    return "\n".join(parts)


def format_lesson_vocabulary(content: LessonContent) -> str:
    parts = [_bold("📖 Новые слова"), ""]
    for index, word in enumerate(content.vocabulary, start=1):
        line = f"{index}. {_bold(escape(word.word))} — {escape(word.translation)}"
        if word.example:
            line += f"\n   <i>{escape(word.example)}</i>"
        parts.append(line)
    return "\n".join(parts)


def format_lesson_slides(content: LessonContent) -> str:
    parts = [_bold("💡 Ключевые идеи темы"), ""]
    for slide in content.slides:
        parts.append(f"• {escape(slide)}")
    return "\n".join(parts)


def format_lesson_grammar(content: LessonContent) -> str:
    grammar = content.grammar
    parts = [_bold(f"📐 Грамматика: {escape(grammar.rule if grammar else '')}")]
    if grammar and grammar.explanation_ru:
        parts.append("")
        parts.append(escape(grammar.explanation_ru))
    if grammar and grammar.examples:
        parts.append("")
        parts.append("Примеры:")
        for index, example in enumerate(grammar.examples, start=1):
            parts.append(f"{index}. <i>{escape(example)}</i>")
    return "\n".join(parts)


def format_lesson_task(content: LessonContent, task_index: int) -> str:
    total = len(content.tasks)
    task = content.tasks[task_index] if 0 <= task_index < total else ""
    return "\n".join(
        [
            _bold(f"❓ Задание {task_index + 1} из {total}"),
            "",
            escape(task),
            "",
            "Ответь на английском (текстом или голосом) — я проверю и исправлю.",
        ]
    )


def format_lesson_recap(content: LessonContent) -> str:
    parts = [_bold("🎉 Урок почти завершён!"), ""]
    parts.append(f"Тема: {escape(content.topic)}")
    if content.vocabulary:
        words = ", ".join(f"<b>{escape(w.word)}</b>" for w in content.vocabulary)
        parts.append(f"📖 Слова: {words}")
    if content.grammar and content.grammar.rule:
        parts.append(f"📐 Грамматика: {escape(content.grammar.rule)}")
    parts.append("")
    parts.append("Совет: повтори слова и построй 2–3 предложения на эту тему в течение дня.")
    parts.append("")
    parts.append("Нажми «🎓 Завершить урок» — увидишь статистику и новую тему.")
    return "\n".join(parts)


def format_lesson_step(step_name: str, content: LessonContent, task_index: int = 0) -> str:
    renderers = {
        "intro": format_lesson_intro,
        "vocabulary": format_lesson_vocabulary,
        "slides": format_lesson_slides,
        "grammar": format_lesson_grammar,
        "tasks": lambda c: format_lesson_task(c, task_index),
        "recap": format_lesson_recap,
    }
    if step_name not in LESSON_STEPS:
        raise ValueError(f"Неизвестный шаг урока: {step_name!r}")
    return renderers[step_name](content)


# ---------- Диагностика уровня (Фаза 3) ----------

CEFR_LABELS_RU = {
    "A1": "Начальный",
    "A2": "Элементарный",
    "B1": "Средний",
    "B2": "Выше среднего",
    "C1": "Продвинутый",
}


def format_diagnostic_question(task: DiagnosticTask, index: int, total: int) -> str:
    return "\n".join(
        [
            _bold(f"🎯 Диагностика · задание {index} из {total}"),
            "",
            escape(task.text),
            "",
            "Ответь по-английски текстом или голосом.",
        ]
    )


def format_level_result(assessment: DiagnosticAssessment, estimated: bool = False) -> str:
    label = CEFR_LABELS_RU.get(assessment.level, assessment.level)
    lines = [_bold(f"🎯 Твой уровень: {assessment.level} — {label}")]
    if estimated:
        lines += ["", "⚠️ Точная оценка не удалась, уровень определён приблизительно."]
    if assessment.explanation_ru:
        lines += ["", escape(assessment.explanation_ru)]
    if assessment.weaknesses:
        lines += ["", "🔍 Над чем поработать:"]
        lines += [f"  • {escape(w)}" for w in assessment.weaknesses]
    if assessment.recommendation:
        lines += ["", f"💡 Совет: {escape(assessment.recommendation)}"]
    lines += [
        "",
        "Дальше уроки будут подстроены под твой уровень. Начнём?",
        "Жми «📚 Начать урок»!",
    ]
    return "\n".join(lines)
