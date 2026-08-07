"""Форматирование ответов для пользователя."""

from __future__ import annotations

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


def _bold(text: str, html: bool) -> str:
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


def format_stats(stats: Stats, html: bool = True) -> str:
    lines = [_bold("Твоя статистика:", html), ""]
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
