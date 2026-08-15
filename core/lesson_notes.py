"""Заметки после урока (Фаза 5).

После завершения урока LLM анализирует его содержание и ответы пользователя
и выдаёт короткий структурированный итог: новые слова, грамматика, говорение,
повторяющиеся ошибки и рекомендация. Логика не зависит от Telegram.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from providers.base import LLMProvider
from storage.repo import LessonNote

from .json_utils import extract_json, JsonParseError
from .lessons import LessonContent

LessonNoteParseError = JsonParseError

NOTE_SYSTEM_PROMPT = """You are an English teacher writing a short structured note about a finished mini-lesson.

You are given the lesson content (topic, vocabulary, grammar) and the student's answers during the lesson, each with the corrected version and detected issues.

Write a concise lesson note. Every field is a short phrase. Write vocabulary/grammar names in English, everything else in Russian.

Fields:
- vocabulary: how many new words the lesson had and whether the student actually used some of them (e.g. "+7 слов, использовал: brew, smooth").
- grammar: which grammar point was covered and how well the student used it.
- speaking: one short assessment of the student's speaking in this lesson.
- mistakes: recurring mistakes seen in the answers (short phrases, e.g. "артикли, порядок слов").
- recommendation: what to practice next (short, in Russian).

Respond ONLY with a single valid JSON object. No markdown, no extra text, no code fences.

JSON schema:
{"vocabulary": "...", "grammar": "...", "speaking": "...", "mistakes": "...", "recommendation": "..."}
"""


def build_note_prompt(content: LessonContent, answers: list[dict]) -> list[dict[str, str]]:
    """Собирает сообщения для LLM: контент урока + ответы пользователя."""
    vocabulary = ", ".join(
        f"{w.word} ({w.translation})" for w in content.vocabulary
    ) or "(нет словаря)"
    grammar = content.grammar.rule if content.grammar else "(грамматика не задана)"

    if not answers:
        answers_text = "(студент не отвечал во время урока)"
    else:
        lines: list[str] = []
        for i, answer in enumerate(answers, start=1):
            issues: list[str] = []
            try:
                raw_issues = json.loads(answer.get("issues_json") or "[]")
                if isinstance(raw_issues, list):
                    for issue in raw_issues:
                        if isinstance(issue, dict) and issue.get("problem"):
                            issues.append(str(issue["problem"]))
            except (json.JSONDecodeError, TypeError):
                pass
            verdict = "ok" if answer.get("is_correct") else f"issues: {', '.join(issues) or 'есть замечания'}"
            lines.append(
                f"ANSWER {i}: {answer.get('content', '')}\n"
                f"verdict: {verdict}\n"
                f"corrected: {answer.get('corrected_text', '')}"
            )
        answers_text = "\n\n".join(lines)

    user_message = (
        f"Lesson:\n"
        f"topic: {content.topic}\n"
        f"vocabulary: {vocabulary}\n"
        f"grammar: {grammar}\n\n"
        f"Student answers:\n{answers_text}"
    )
    return [
        {"role": "system", "content": NOTE_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]


def parse_note_response(raw: str) -> dict[str, str]:
    """Разбирает JSON-ответ LLM в поля заметки."""
    payload = extract_json(raw)
    return {
        field: str(payload.get(field, "")).strip()
        for field in ("vocabulary", "grammar", "speaking", "mistakes", "recommendation")
    }


class LessonNoteService:
    """Генерирует итоговую заметку урока через LLM."""

    def __init__(self, llm: LLMProvider):
        self._llm = llm

    async def generate(
        self,
        user_id: int,
        lesson_id: int,
        content: LessonContent,
        answers: list[dict],
    ) -> LessonNote:
        messages = build_note_prompt(content, answers)
        raw = await self._llm.chat(messages, temperature=0.2)
        fields = parse_note_response(raw)
        return LessonNote(
            user_id=user_id,
            lesson_id=lesson_id,
            topic=content.topic,
            created_at=datetime.now(timezone.utc).isoformat(),
            **fields,
        )
