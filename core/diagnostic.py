"""Диагностика уровня (Фаза 3).

Первый урок пользователя — диагностический: LLM генерирует «лестницу» заданий
(2 простых, 2 средних, 2 сложных), пользователь отвечает, и отдельный вызов LLM
оценивает уровень CEFR (A1..C1) с обоснованием. Логика не зависит от Telegram.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from providers.base import LLMProvider

from .json_utils import extract_json, JsonParseError

DiagnosticParseError = JsonParseError

CEFR_LEVELS = ["A1", "A2", "B1", "B2", "C1"]

# Диапазоны сложности заданий-лесенки: сколько заданий на каждый блок.
DIAGNOSTIC_LADDER: list[tuple[str, int]] = [
    ("A1", 1),
    ("A2", 1),
    ("B1", 2),
    ("B2", 1),
    ("C1", 1),
]


@dataclass
class DiagnosticTask:
    """Одно задание диагностики. level_hint — целевой диапазон сложности."""

    text: str
    level_hint: str = ""


@dataclass
class DiagnosticAssessment:
    """Результат определения уровня."""

    level: str  # CEFR: A1 | A2 | B1 | B2 | C1
    confidence: float = 0.0  # 0..1
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    recommendation: str = ""
    explanation_ru: str = ""


TASKS_SYSTEM_PROMPT = """You are an English teacher building a short placement (diagnostic) conversation for a Russian-speaking student.

Create a ladder of 6 short speaking tasks of increasing difficulty:
- 1 easy task (A1): simplest, personal introduction
- 1 easy task (A2): everyday routine or preferences
- 2 medium tasks (B1): opinions on everyday topics, short stories from the past
- 1 hard task (B2): abstract or debatable topic, pros and cons
- 1 hard task (C1): nuanced abstract question, disagree with a statement

The goal: by the end, an experienced teacher could estimate the student's CEFR level (A1..C1) from their answers.
Tasks must be open-ended (no yes/no answers) and short. Each next task lets the student show more complex grammar and vocabulary.

Respond ONLY with a single valid JSON object. No markdown, no extra text, no code fences.

JSON schema:
{
  "tasks": [
    {"text": "short open-ended task in English", "level_hint": "A1"},
    {"text": "...", "level_hint": "A2"},
    {"text": "...", "level_hint": "B1"},
    {"text": "...", "level_hint": "B1"},
    {"text": "...", "level_hint": "B2"},
    {"text": "...", "level_hint": "C1"}
  ]
}

Rules:
- exactly 6 tasks, ordered from easiest to hardest.
- level_hint is one of: A1, A2, B1, B2, C1.
- all tasks must be in English.
"""

ASSESSMENT_SYSTEM_PROMPT = """You are an English teacher assessing a student's CEFR level (A1, A2, B1, B2, C1) after a short diagnostic conversation.

You are given the tasks the student was asked and their verbatim answers. Judge by:
- grammar control and range
- vocabulary breadth and precision
- fluency, sentence length and complexity
- how well the answer addresses the task

Be conservative: when in doubt, prefer the lower level. An honest A2 is better than an inflated B1.

Respond ONLY with a single valid JSON object. No markdown, no extra text, no code fences.

JSON schema:
{
  "level": "B1",
  "confidence": 0.8,
  "explanation_ru": "short explanation in Russian why this level",
  "strengths": ["short strength in English or Russian"],
  "weaknesses": ["short weakness in English or Russian"],
  "recommendation": "short suggestion in Russian what to focus on"
}

Rules:
- "level" is one of: A1, A2, B1, B2, C1.
- "confidence" is a number from 0 to 1.
- arrays may be empty.
"""


def build_diagnostic_prompt() -> list[dict[str, str]]:
    return [
        {"role": "system", "content": TASKS_SYSTEM_PROMPT},
        {"role": "user", "content": "Create the placement conversation ladder."},
    ]


def parse_diagnostic_tasks(raw: str) -> list[DiagnosticTask]:
    """Разбирает JSON-ответ LLM в список заданий. Поля — с безопасными дефолтами."""
    payload = extract_json(raw)
    tasks: list[DiagnosticTask] = []
    for item in payload.get("tasks") or []:
        if isinstance(item, dict):
            tasks.append(
                DiagnosticTask(
                    text=str(item.get("text", "")).strip(),
                    level_hint=str(item.get("level_hint", "")).strip(),
                )
            )
    return tasks


def build_assessment_prompt(
    questions: list[DiagnosticTask],
    answers: list[str],
) -> list[dict[str, str]]:
    dialogue = "\n".join(
        f"TASK {i + 1}: {q.text}\nANSWER: {answers[i] if i < len(answers) else '(no answer)'}"
        for i, q in enumerate(questions)
    )
    return [
        {"role": "system", "content": ASSESSMENT_SYSTEM_PROMPT},
        {"role": "user", "content": f"Assess this student:\n\n{dialogue}"},
    ]


def _normalize_level(value: str) -> str:
    level = str(value).strip().upper()
    return level if level in CEFR_LEVELS else "B1"


def parse_assessment(raw: str) -> DiagnosticAssessment:
    """Разбирает JSON-ответ LLM в DiagnosticAssessment с безопасными дефолтами."""
    payload = extract_json(raw)
    return DiagnosticAssessment(
        level=_normalize_level(payload.get("level", "B1")),
        confidence=float(payload.get("confidence", 0.0) or 0.0),
        strengths=[str(s) for s in payload.get("strengths") or [] if isinstance(s, str)],
        weaknesses=[str(w) for w in payload.get("weaknesses") or [] if isinstance(w, str)],
        recommendation=str(payload.get("recommendation", "")).strip(),
        explanation_ru=str(payload.get("explanation_ru", "")).strip(),
    )


def diagnostic_tasks_to_json(tasks: list[DiagnosticTask]) -> str:
    return json.dumps([asdict(t) for t in tasks], ensure_ascii=False)


def diagnostic_tasks_from_json(raw: str) -> list[DiagnosticTask]:
    payload = json.loads(raw)
    return [
        DiagnosticTask(text=str(t.get("text", "")), level_hint=str(t.get("level_hint", "")))
        for t in payload
        if isinstance(t, dict)
    ]


def estimate_level_heuristic(answers: list[str]) -> str:
    """Запасная оценка без LLM: средняя длина ответа + индикаторы сложной лексики.

    Не заменяет LLM-оценку, только страхует от сбоя модели.
    """
    if not answers:
        return "B1"
    words = sum(len(a.split()) for a in answers)
    avg = words / len(answers)
    joined = " ".join(answers).lower()
    advanced = any(
        w in joined
        for w in (
            "although",
            "however",
            "therefore",
            "despite",
            "whereas",
            "moreover",
            "furthermore",
            "consequently",
        )
    )
    if avg >= 25 and advanced:
        return "B2"
    if avg >= 15:
        return "B1"
    if avg >= 8:
        return "A2"
    return "A1"


class DiagnosticService:
    """Высокоуровневый сервис: задания-лесенка и оценка уровня через LLM."""

    def __init__(self, llm: LLMProvider):
        self._llm = llm

    async def generate_tasks(self) -> list[DiagnosticTask]:
        messages = build_diagnostic_prompt()
        raw = await self._llm.chat(messages, temperature=0.7)
        return parse_diagnostic_tasks(raw)

    async def assess(
        self,
        questions: list[DiagnosticTask],
        answers: list[str],
    ) -> DiagnosticAssessment:
        messages = build_assessment_prompt(questions, answers)
        raw = await self._llm.chat(messages, temperature=0.0)
        return parse_assessment(raw)
