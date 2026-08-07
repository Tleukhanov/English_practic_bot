"""Сервис практики: сборка промпта, вызов LLM, устойчивый парсинг JSON-ответа.

Ядро продукта. Никакой логики Telegram здесь нет — только работа с LLM,
поэтому сервис переиспользуется и ботом, и будущим сайтом, и презентациями.
"""

from __future__ import annotations

import json
import re

from providers.base import LLMProvider

from .models import Issue, PracticeResult

SYSTEM_PROMPT = """You are a friendly English tutor for a Russian-speaking student who wants to practice speaking English.

The student writes you messages in English (possibly with mistakes). Your job:
1. Check whether the message is correct English.
2. If there are mistakes, list them and explain how to fix them.
3. Keep a natural dialogue going by asking a follow-up question.

Respond ONLY with a single valid JSON object. No markdown, no extra text, no code fences.

JSON schema:
{
  "is_correct": true,
  "corrected_text": "the full corrected version of the student's message",
  "issues": [
    {
      "category": "grammar | vocabulary | pronunciation | style | word_order",
      "problem": "what is wrong, in Russian",
      "suggestion": "how to fix it, in Russian",
      "correction": "the corrected fragment, in English"
    }
  ],
  "next_question": "a short natural follow-up question to continue the dialogue, in English",
  "tone": "a short encouraging phrase in Russian, e.g. \"Отлично!\""
}

Rules:
- "issues" must be an empty array when is_correct is true.
- "corrected_text" is required even when correct (keep the student's own phrasing, fix only real mistakes).
- Explanations ("problem", "suggestion") and "tone" must be in Russian. Everything else in English.
- Never translate the student's message to Russian; the dialogue stays in English.
"""


class PracticeParseError(ValueError):
    """Ответ LLM не удалось разобрать как JSON."""


def build_prompt(text: str, history: list[dict[str, str]], max_history: int = 6) -> list[dict[str, str]]:
    """Собирает сообщения для LLM: системный промпт + недавняя история + текущая реплика."""
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for item in history[-max_history:]:
        if item.get("role") in {"user", "assistant"} and item.get("content"):
            messages.append({"role": item["role"], "content": item["content"]})
    messages.append({"role": "user", "content": text})
    return messages


def _extract_json(text: str) -> dict:
    """Достаёт JSON-объект из ответа LLM, переживая ```json-обёртки и лишний текст."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise PracticeParseError(f"В ответе LLM нет JSON-объекта: {text[:200]!r}")
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise PracticeParseError(f"Невалидный JSON от LLM: {exc}") from exc


def parse_practice_response(raw: str) -> PracticeResult:
    """Разбирает ответ LLM в PracticeResult. Все поля — с безопасными дефолтами."""
    payload = _extract_json(raw)

    issues_raw = payload.get("issues") or []
    issues: list[Issue] = []
    for item in issues_raw:
        if not isinstance(item, dict):
            continue
        issues.append(
            Issue(
                category=str(item.get("category", "")),
                problem=str(item.get("problem", "")),
                suggestion=str(item.get("suggestion", "")),
                correction=str(item.get("correction", "")),
            )
        )

    return PracticeResult(
        is_correct=bool(payload.get("is_correct", not issues)),
        corrected_text=str(payload.get("corrected_text", "")).strip(),
        issues=issues,
        next_question=str(payload.get("next_question", "")).strip(),
        tone=str(payload.get("tone", "")).strip(),
    )


class PracticeService:
    """Высокоуровневый сервис: текст пользователя -> PracticeResult."""

    def __init__(self, llm: LLMProvider, max_history: int = 6):
        self._llm = llm
        self._max_history = max_history

    async def analyze(self, text: str, history: list[dict[str, str]]) -> PracticeResult:
        messages = build_prompt(text, history, max_history=self._max_history)
        raw = await self._llm.chat(messages)
        return parse_practice_response(raw)
