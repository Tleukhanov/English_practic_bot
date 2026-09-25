"""План уроков (после каждых 12 завершённых уроков).

LLM составляет план на ближайшие уроки: общая цель и список тем с фокусом
и обоснованием. План влияет на выбор темы следующего урока. Логика не
зависит от Telegram.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from providers.base import LLMProvider

from .json_utils import extract_json, JsonParseError

LessonPlanParseError = JsonParseError

PLAN_LESSON_COUNT = 12

PLAN_SYSTEM_PROMPT = """You are an English teacher planning the next lessons for a Russian-speaking student.

Create a study plan of exactly 12 upcoming lessons. Give an overall goal for the block and, for every lesson, a topic the student will study.

Respond ONLY with a single valid JSON object. No markdown, no extra text, no code fences.

JSON schema:
{
  "goal": "overall aim for these 12 lessons, one or two sentences",
  "lessons": [
    {"number": 1, "topic": "English topic name", "focus": "concrete skill or material to work on", "reason": "why this lesson comes next"},
    {"number": 2, "topic": "...", "focus": "...", "reason": "..."},
    {"number": 12, "topic": "...", "focus": "...", "reason": "..."}
  ]
}

Rules:
- "lessons" MUST contain EXACTLY 12 objects, with "number" from 1 to 12.
- Topics progress in difficulty from the student's current level towards slightly harder material, building step by step.
- The "focus" is the concrete skill, vocabulary or grammar point of the lesson; the "reason" explains why this lesson belongs in the plan.
- Consider the student's profile: their goal, interests and weak areas. Weave interests into topics and address weak areas in the "focus".
- NEVER suggest a topic from the recent topics list below — pick different, fresh topics.
- Consider how many lessons the student has already completed so the plan starts from the right point.
- topic/focus/reason in English, goal in Russian or English — keep everything short and useful.
"""


def _extract_number(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


@dataclass
class PlannedLesson:
    number: int
    topic: str
    focus: str = ""
    reason: str = ""


@dataclass
class LessonPlan:
    goal: str = ""
    lessons: list[PlannedLesson] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "goal": self.goal,
                "lessons": [asdict(lesson) for lesson in self.lessons],
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, raw: str) -> "LessonPlan":
        if not raw or not raw.strip():
            return cls()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return cls()
        if not isinstance(payload, dict):
            return cls()
        lessons: list[PlannedLesson] = []
        for item in payload.get("lessons") or []:
            if isinstance(item, dict):
                lessons.append(
                    PlannedLesson(
                        number=_extract_number(item.get("number") or 1),
                        topic=str(item.get("topic", "")),
                        focus=str(item.get("focus", "")),
                        reason=str(item.get("reason", "")),
                    )
                )
        return cls(goal=str(payload.get("goal", "")), lessons=lessons)


def build_plan_prompt(
    level: str | None,
    profile: str | None,
    recent_topics: list[str],
    completed_lessons: int,
) -> list[dict[str, str]]:
    """Собирает сообщения для LLM: контекст ученика и запрос плана."""
    parts = [PLAN_SYSTEM_PROMPT]
    extras: list[str] = []
    if level:
        extras.append(f"Student level: {level}.")
    if profile:
        extras.append(profile)
    if recent_topics:
        extras.append(
            "RECENT TOPICS (you MUST NOT repeat or reuse any of these): "
            + ", ".join(f'"{t}"' for t in recent_topics)
            + "."
        )
    extras.append(
        f"The student has completed {completed_lessons} lessons so far; "
        f"the plan is for the NEXT {PLAN_LESSON_COUNT} lessons."
    )
    if extras:
        parts.append("\n" + " ".join(extras))
    system = "\n".join(parts)
    return [
        {"role": "system", "content": system},
        {
            "role": "system",
            "content": (
                "CRITICAL FORMAT RULE — this overrides all other instructions: "
                "Your response MUST be ONLY a single valid JSON object matching the schema above. "
                "No markdown, no text outside JSON, no code fences, no bullet points, no emoji headers. "
                "If you break this rule the student will see an error."
            ),
        },
        {"role": "user", "content": f"Create a plan for the next {PLAN_LESSON_COUNT} lessons."},
    ]


def parse_plan_response(raw: str) -> LessonPlan:
    """Разбирает JSON-ответ LLM в LessonPlan. Поля — с безопасными дефолтами."""
    payload = extract_json(raw)
    lessons: list[PlannedLesson] = []
    for item in payload.get("lessons") or []:
        if isinstance(item, dict):
            lessons.append(
                PlannedLesson(
                    number=_extract_number(item.get("number") or 1),
                    topic=str(item.get("topic", "")).strip(),
                    focus=str(item.get("focus", "")).strip(),
                    reason=str(item.get("reason", "")).strip(),
                )
            )
    return LessonPlan(goal=str(payload.get("goal", "")).strip(), lessons=lessons)


def next_plan_index(based_on_lessons: int, completed_lessons: int, horizon: int) -> int | None:
    cursor = completed_lessons - based_on_lessons
    if 0 <= cursor < horizon:
        return cursor
    return None


class LessonPlanService:
    """Генерирует план на ближайшие уроки через LLM."""

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def generate(
        self,
        *,
        level: str | None,
        profile: str | None,
        recent_topics: list[str],
        completed_lessons: int,
    ) -> LessonPlan:
        messages = build_plan_prompt(level, profile, recent_topics, completed_lessons)
        raw = await self._llm.chat(messages, temperature=0.7, json_mode=True)
        return parse_plan_response(raw)