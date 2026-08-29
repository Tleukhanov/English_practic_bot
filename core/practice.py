"""Сервис практики: сборка промпта, вызов LLM, устойчивый парсинг JSON-ответа.

Ядро продукта. Никакой логики Telegram здесь нет — только работа с LLM,
поэтому сервис переиспользуется и ботом, и будущим сайтом, и презентациями.
"""

from __future__ import annotations

from providers.base import LLMProvider

from .json_utils import extract_json, JsonParseError
from .models import Issue, PracticeResult

# Обратная совместимость: код и тесты могут ссылаться на PracticeParseError.
PracticeParseError = JsonParseError

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
  "spoken_reply": "a short natural spoken reply to the student's message in English, as if you two are having a voice conversation; say something a conversation partner would say, never repeat the student's words and never recite corrections",
  "tone": "a short encouraging phrase in Russian, e.g. \"Отлично!\""
}

Rules:
- "issues" must be an empty array when is_correct is true.
- "corrected_text" is required even when correct (keep the student's own phrasing, fix only real mistakes).
- "spoken_reply" is required: it is what gets read aloud by text-to-speech.
- Explanations ("problem", "suggestion") and "tone" must be in Russian. Everything else in English.
- Never translate the student's message to Russian; the dialogue stays in English.
- IMPORTANT: Check the conversation history. If the student is making the SAME mistake they made before, call it out explicitly in "tone" — mention that they already made this mistake before and need to pay attention. This is critical for learning.
"""


def build_prompt(
    text: str,
    history: list[dict[str, str]],
    max_history: int = 6,
    profile: str | None = None,
    character_prompt: str = "",
    weak_areas_prompt: str = "",
) -> list[dict[str, str]]:
    """Собирает сообщения для LLM: системный промпт + недавняя история + текущая реплика.

    profile — сниппет из памяти пользователя (Фаза 4).
    character_prompt — инструкции персонажа (Фаза 8), определяют тон общения.
    weak_areas_prompt — строка с топ слабыми областями (Фаза 13).
    """
    system = SYSTEM_PROMPT
    if profile:
        system += (
            f"\n\n{profile}\n"
            "Tailor follow-up questions and examples to the student's interests, "
            "level and weak areas when possible."
        )

    if weak_areas_prompt:
        system += (
            f"\n\n{weak_areas_prompt}\n"
            "IMPORTANT: When generating follow-up questions, PRIORITIZE these weak areas. "
            "Ask questions that naturally require the student to practice these specific skills. "
            "If the student has answered correctly 3+ times for an area, reduce how often you ask about it."
        )

    messages: list[dict[str, str]] = [{"role": "system", "content": system}]

    format_rule = (
        "CRITICAL FORMAT RULE — this overrides all other instructions: "
        "Your response MUST be ONLY a single valid JSON object matching the schema in the system prompt. "
        "No markdown, no text outside JSON, no code fences, no emoji explanations, no bullet points. "
        "Express personality ONLY through JSON fields: \"tone\", \"spoken_reply\", \"next_question\". "
        "If you break this rule the student will see an error."
    )

    if character_prompt:
        format_rule += (
            f"\n\nCHARACTER STYLE — you MUST act as this character when writing "
            f"\"tone\", \"spoken_reply\", and \"next_question\":\n{character_prompt}"
        )

    messages.append({"role": "system", "content": format_rule})
    for item in history[-max_history:]:
        if item.get("role") in {"user", "assistant"} and item.get("content"):
            messages.append({"role": item["role"], "content": item["content"]})
    messages.append({"role": "user", "content": text})
    return messages


def parse_practice_response(raw: str) -> PracticeResult:
    """Разбирает ответ LLM в PracticeResult. Все поля — с безопасными дефолтами."""
    payload = extract_json(raw)

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

    has_issues = len(issues) > 0
    raw_flag = payload.get("is_correct")
    # Issues и is_correct=True противоречат друг другу (нарушение схемы). Issues
    # сильнее: если есть разбор ошибок — фраза не может считаться правильной.
    if has_issues:
        is_correct = False
    elif raw_flag is None:
        is_correct = True
    else:
        is_correct = bool(raw_flag)

    return PracticeResult(
        is_correct=is_correct,
        corrected_text=str(payload.get("corrected_text", "")).strip(),
        issues=issues,
        next_question=str(payload.get("next_question", "")).strip(),
        spoken_reply=str(payload.get("spoken_reply", "")).strip(),
        tone=str(payload.get("tone", "")).strip(),
    )


class PracticeService:
    """Высокоуровневый сервис: текст пользователя -> PracticeResult."""

    def __init__(self, llm: LLMProvider, max_history: int = 6):
        self._llm = llm
        self._max_history = max_history

    async def analyze(
        self,
        text: str,
        history: list[dict[str, str]],
        profile: str | None = None,
        character_prompt: str = "",
        weak_areas_prompt: str = "",
    ) -> PracticeResult:
        messages = build_prompt(text, history, max_history=self._max_history, profile=profile, character_prompt=character_prompt, weak_areas_prompt=weak_areas_prompt)
        raw = await self._llm.chat(messages, json_mode=True)
        return parse_practice_response(raw)
