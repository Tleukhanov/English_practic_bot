"""Структурированные уроки (Фаза 1).

LessonService генерирует цельный мини-урок через LLM (тема -> слова -> ключевые
идеи -> грамматика -> задания). Бот проводит пользователя по шагам урока.
Логика не зависит от Telegram — только LLM и модели данных.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field

from providers.base import LLMProvider

from .json_utils import extract_json, extract_json_list, JsonParseError

LessonParseError = JsonParseError
logger = logging.getLogger(__name__)

LESSON_STEPS = ["intro", "vocabulary", "slides", "grammar", "tasks", "recap"]

# Форматы урока: каждый меняет акценты, чтобы уроки не повторялись.
LESSON_TYPES = {
    "standard": "Balanced lesson: a short engaging intro, practical vocabulary, a few useful ideas, one simple grammar point.",
    "story": "Build the lesson around a tiny story: the intro opens the story, the slides continue the plot, and the tasks ask about the story and the student's own experience.",
    "dialogue": "Conversation-focused lesson: vocabulary and tasks serve a short dialogue; tasks are questions that keep the student talking.",
    "quiz": "Quiz-style lesson: tasks are quick interactive questions (fill-in-the-blank, choose the correct option, or 'translate this') with one right answer each.",
    "ideas": "Discussion lesson: slides present a few opinions or facts, and tasks ask the student to agree/disagree and explain why.",
}

TOPIC_PROPOSALS_SYSTEM_PROMPT = """You are an English teacher choosing lesson topics for a Russian-speaking student.

Generate exactly 3 interesting, distinct topics. Each topic has a short English name and a 1-sentence Russian description of why it is interesting and what the student will learn.

Respond ONLY with a single valid JSON array. No markdown, no extra text, no code fences.

JSON schema:
[
  {"topic": "English topic name", "description": "Russian description of the topic"},
  {"topic": "...", "description": "..."},
  {"topic": "...", "description": "..."}
]

Rules:
- topics must be different from each other
- topics should be engaging and practical (not academic or boring)
- descriptions must be in RUSSIAN, 1 sentence, explain what the student will learn
- If the student has interests listed in their profile, at least 2 of 3 topics MUST revolve around those interests. This is critical — the student should feel the lessons are tailored specifically for them.
- NEVER suggest a topic that was already covered. The list of banned topics is provided below — follow it strictly.
- If interests overlap with banned topics, pick a DIFFERENT angle within that interest (e.g. if "cooking" is banned, try "restaurant English" or "food culture around the world").
"""


@dataclass
class VocabWord:
    word: str
    translation: str
    example: str


@dataclass
class GrammarBlock:
    rule: str
    explanation_ru: str
    examples: list[str] = field(default_factory=list)


@dataclass
class LessonContent:
    topic: str
    intro: str
    vocabulary: list[VocabWord] = field(default_factory=list)
    slides: list[str] = field(default_factory=list)
    grammar: GrammarBlock | None = None
    tasks: list[str] = field(default_factory=list)
    lesson_type: str = "standard"


CORE_SYSTEM_PROMPT = """You are an English teacher creating a structured mini-lesson for a Russian-speaking learner at the __LEVEL_DESC__ level.

__LEVEL_RULES__

Create the CORE of a short engaging mini-lesson on the requested topic (if no topic given, pick an interesting everyday topic yourself).

Respond ONLY with a single valid JSON object. No markdown, no extra text, no code fences.

JSON schema:
{
  "topic": "topic name",
  "lesson_type": "standard",
  "intro": "1-2 short friendly English sentences introducing the topic and why it is interesting",
  "vocabulary": [
    {"word": "english word", "translation": "russian translation", "example": "short english example sentence"}
  ],
  "grammar": {
    "rule": "name of the grammar point, e.g. 'Past Simple'",
    "explanation_ru": "short explanation in Russian",
    "examples": ["english example sentence", "..."]
  }
}

Rules:
- Keep the lesson SHORT: vocabulary is exactly 3 to 4 words with Russian translations and short examples.
- grammar: ONE simple grammar point naturally connected to the topic and suited to the student's level; give 1-2 examples.
- intro, words and grammar examples must be in ENGLISH.
- translations and explanation_ru must be in RUSSIAN.

__LESSON_TYPE_RULES__
"""

SLIDES_SYSTEM_PROMPT = """You are an English teacher. A student is taking a SHORT English lesson on the topic below. Now produce the "key ideas" part of that lesson.

Respond ONLY with a single valid JSON object. No markdown, no extra text, no code fences.

JSON schema:
{ "slides": ["short English key point", "...", "..."] }

Rules:
- 2 to 3 concise bullet points in ENGLISH with the most useful ideas, facts or phrases about the topic.
- Do NOT repeat the vocabulary list — give fresh, memorable points the student should remember.

__LEVEL_RULES__
__LESSON_TYPE_RULES__
"""

TASKS_SYSTEM_PROMPT = """You are an English teacher. A student is finishing a SHORT lesson on the topic below. Create the speaking tasks for it.

Respond ONLY with a single valid JSON object. No markdown, no extra text, no code fences.

JSON schema:
{ "tasks": ["an English speaking task or question", "...", "..."] }

Rules:
- 2 to 3 short speaking tasks or questions in ENGLISH the student answers aloud.
- Each task must be answerable in 1-3 sentences at the student's level.

__LEVEL_RULES__
__LESSON_TYPE_RULES__
"""

# Совместимость: прежний единый шаблон соответствует «ядру» урока.
SYSTEM_PROMPT_TEMPLATE = CORE_SYSTEM_PROMPT

LEVEL_DESCRIPTIONS = {
    None: "beginner (A1)",
    "A1": "beginner (A1)",
    "A2": "elementary (A2)",
    "B1": "intermediate (B1)",
    "B2": "upper-intermediate (B2)",
    "C1": "advanced (C1)",
}

LEVEL_RULES = {
    None: "Keep everything simple: basic vocabulary, short sentences, tasks that require only simple answers.",
    "A1": "Keep everything simple: basic vocabulary, short sentences, tasks that require only simple answers.",
    "A2": "Use everyday vocabulary and simple sentences; allow tasks with short answers about daily life.",
    "B1": "Use intermediate vocabulary and a few complex sentences; tasks may ask for opinions.",
    "B2": "Use richer vocabulary and complex sentences; tasks may ask for pros/cons and abstract topics.",
    "C1": "Use advanced vocabulary and nuanced structures; tasks may ask to argue and explain abstract ideas.",
}


def _render_system_prompt(
    body: str,
    level: str | None,
    profile: str | None = None,
    recent_topics: list[str] | None = None,
    character_prompt: str = "",
    lesson_type: str = "standard",
) -> str:
    type_rules = LESSON_TYPES.get(lesson_type, LESSON_TYPES["standard"])
    text = body.replace(
        "__LEVEL_DESC__", LEVEL_DESCRIPTIONS.get(level, LEVEL_DESCRIPTIONS[None])
    ).replace(
        "__LEVEL_RULES__", LEVEL_RULES.get(level, "")
    ).replace(
        "__LESSON_TYPE_RULES__",
        f"Lesson format: {type_rules}\n"
        f'Set "lesson_type" to exactly: "{lesson_type}".',
    )
    if profile:
        text += (
            f"\n\n{profile}\n"
            "If the student has interests, prefer a lesson around one of them "
            "(pick the most engaging topic). Address their weak areas in the grammar point."
        )
    if recent_topics:
        topics_str = ", ".join(f'"{t}"' for t in recent_topics)
        text += (
            f"\n\nRecent lesson topics (DO NOT repeat any of them): {topics_str}.\n"
            "Pick a DIFFERENT, fresh topic."
        )
    if character_prompt:
        text += f"\n\n[CHARACTER STYLE — act as this character while keeping JSON format: {character_prompt}]"
    text += (
        "\n\nIMPORTANT: Your ENTIRE response MUST be a single valid JSON object matching the schema above. "
        "No markdown, no explanations outside JSON, no code fences, no extra text before or after. "
        "Apply CHARACTER STYLE to the tone and content of your response."
    )
    return text


def _step_messages(system: str, user: str) -> list[dict[str, str]]:
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
        {"role": "user", "content": user},
    ]


def build_lesson_prompt(
    topic: str | None,
    level: str | None = None,
    profile: str | None = None,
    recent_topics: list[str] | None = None,
    character_prompt: str = "",
    lesson_type: str = "standard",
) -> list[dict[str, str]]:
    user_message = f"Create a structured lesson. Topic: {topic}" if topic else "Create a structured lesson on an interesting topic of your choice."
    system = _render_system_prompt(CORE_SYSTEM_PROMPT, level, profile, recent_topics, character_prompt, lesson_type)
    return _step_messages(system, user_message)


def _build_core_messages(
    topic: str | None,
    level: str | None = None,
    profile: str | None = None,
    recent_topics: list[str] | None = None,
    character_prompt: str = "",
    lesson_type: str = "standard",
) -> list[dict[str, str]]:
    return build_lesson_prompt(topic, level, profile, recent_topics, character_prompt, lesson_type)


def _build_slides_messages(
    topic: str,
    level: str | None = None,
    character_prompt: str = "",
    lesson_type: str = "standard",
) -> list[dict[str, str]]:
    system = _render_system_prompt(SLIDES_SYSTEM_PROMPT, level, character_prompt=character_prompt, lesson_type=lesson_type)
    return _step_messages(system, f"Topic: {topic}. Give me the key ideas (slides) for this lesson.")


def _build_tasks_messages(
    topic: str,
    level: str | None = None,
    character_prompt: str = "",
    lesson_type: str = "standard",
) -> list[dict[str, str]]:
    system = _render_system_prompt(TASKS_SYSTEM_PROMPT, level, character_prompt=character_prompt, lesson_type=lesson_type)
    return _step_messages(system, f"Topic: {topic}. Create the speaking tasks for this lesson.")


def parse_lesson_response(raw: str) -> LessonContent:
    """Разбирает JSON-ответ LLM в LessonContent. Поля — с безопасными дефолтами."""
    payload = extract_json(raw)

    vocabulary: list[VocabWord] = []
    for item in payload.get("vocabulary") or []:
        if isinstance(item, dict):
            vocabulary.append(
                VocabWord(
                    word=str(item.get("word", "")),
                    translation=str(item.get("translation", "")),
                    example=str(item.get("example", "")),
                )
            )

    grammar_raw = payload.get("grammar")
    grammar: GrammarBlock | None = None
    if isinstance(grammar_raw, dict):
        grammar = GrammarBlock(
            rule=str(grammar_raw.get("rule", "")),
            explanation_ru=str(grammar_raw.get("explanation_ru", "")),
            examples=[str(e) for e in (grammar_raw.get("examples") or []) if isinstance(e, str)],
        )

    lesson_type = str(payload.get("lesson_type", "")).strip().lower()
    if lesson_type not in LESSON_TYPES:
        lesson_type = "standard"
    return LessonContent(
        topic=str(payload.get("topic", "")).strip() or "Без темы",
        intro=str(payload.get("intro", "")).strip(),
        vocabulary=vocabulary,
        slides=[str(s) for s in (payload.get("slides") or []) if isinstance(s, str)],
        grammar=grammar,
        tasks=[str(t) for t in (payload.get("tasks") or []) if isinstance(t, str)],
        lesson_type=lesson_type,
    )


def lesson_content_to_json(content: LessonContent) -> str:
    return json.dumps(asdict(content), ensure_ascii=False)


def lesson_content_from_json(raw: str) -> LessonContent:
    payload = json.loads(raw)
    grammar_raw = payload.get("grammar")
    grammar: GrammarBlock | None = None
    if isinstance(grammar_raw, dict):
        grammar = GrammarBlock(
            rule=str(grammar_raw.get("rule", "")),
            explanation_ru=str(grammar_raw.get("explanation_ru", "")),
            examples=[str(e) for e in (grammar_raw.get("examples") or [])],
        )
    return LessonContent(
        topic=str(payload.get("topic", "")),
        intro=str(payload.get("intro", "")),
        vocabulary=[VocabWord(**item) for item in payload.get("vocabulary") or []],
        slides=[str(s) for s in payload.get("slides") or []],
        grammar=grammar,
        tasks=[str(t) for t in payload.get("tasks") or []],
        lesson_type=str(payload.get("lesson_type", "standard")),
    )


def parse_proposals_response(raw: str) -> list[dict[str, str]]:
    """Разбирает JSON-ответ LLM со списком предложений тем."""
    payload = extract_json_list(raw)
    proposals: list[dict[str, str]] = []
    for item in payload:
        if isinstance(item, dict):
            topic = str(item.get("topic", "")).strip()
            description = str(item.get("description", "")).strip()
            if topic:
                proposals.append({"topic": topic, "description": description})
    return proposals[:3]


def _render_proposals_prompt(level: str | None = None, profile: str | None = None, recent_topics: list[str] | None = None) -> str:
    parts = [TOPIC_PROPOSALS_SYSTEM_PROMPT]
    extras: list[str] = []
    if level:
        extras.append(f"Student level: {level}.")
    if profile:
        extras.append(profile)
    if recent_topics:
        extras.append(
            "BANNED TOPICS (you MUST NOT suggest any of these): "
            + ", ".join(recent_topics)
            + ". Pick completely different topics."
        )
    if extras:
        parts.append("\n" + " ".join(extras))
    return "\n".join(parts)


def extract_str_list(raw: str, key: str) -> list[str]:
    """Вытаскивает список строк из ответа LLM, толерантно к формату.

    Принимает {"slides": [...]}, {..., "tasks": [...]} или просто массив.
    При невалидном JSON возвращает [] — шаг урока не должен ронять весь урок.
    """
    if not raw or not raw.strip():
        return []
    payload = None
    try:
        payload = extract_json(raw)
    except LessonParseError:
        try:
            payload = extract_json_list(raw)
        except LessonParseError:
            return []
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get(key) or []
    else:
        return []
    return [str(x) for x in items if isinstance(x, str)]


class LessonService:
    """Генерация структурированного урока через LLM в три шага.

    Шаг 1 — «ядро» урока (тема, интро, слова, грамматика).
    Шаг 2 — ключевые идеи (slides), шаг 3 — задания (tasks). Шаги 2 и 3 идут
    параллельно после ядра. Если побочный шаг не удался — урок всё равно
    собирается, а карточка не падает.
    """

    def __init__(self, llm: LLMProvider):
        self._llm = llm

    async def _step(self, messages: list[dict[str, str]]) -> str:
        try:
            return await self._llm.chat(messages, temperature=0.7, json_mode=True)
        except Exception:
            logger.warning("Шаг генерации урока не удался", exc_info=True)
            return ""

    async def generate(
        self,
        topic: str | None = None,
        level: str | None = None,
        profile: str | None = None,
        recent_topics: list[str] | None = None,
        character_prompt: str = "",
        lesson_type: str = "standard",
    ) -> LessonContent:
        core_raw = await self._step(
            _build_core_messages(topic, level=level, profile=profile, recent_topics=recent_topics, character_prompt=character_prompt, lesson_type=lesson_type)
        )
        if not core_raw:
            raise LessonParseError("LLM не вернул ядро урока")
        content = parse_lesson_response(core_raw)
        content.lesson_type = lesson_type

        base = {"topic": content.topic or topic or "", "level": level, "character_prompt": character_prompt, "lesson_type": lesson_type}
        slides_raw, tasks_raw = await asyncio.gather(
            self._step(_build_slides_messages(base["topic"], level=level, character_prompt=character_prompt, lesson_type=lesson_type)),
            self._step(_build_tasks_messages(base["topic"], level=level, character_prompt=character_prompt, lesson_type=lesson_type)),
        )
        content.slides = extract_str_list(slides_raw, "slides") or content.slides
        content.tasks = extract_str_list(tasks_raw, "tasks") or content.tasks
        return content

    async def generate_proposals(
        self,
        level: str | None = None,
        profile: str | None = None,
        recent_topics: list[str] | None = None,
    ) -> list[dict[str, str]]:
        """Генерирует 3 предложения тем для урока (Фаза 2)."""
        system = _render_proposals_prompt(level=level, profile=profile, recent_topics=recent_topics)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": "Choose 3 interesting lesson topics."},
        ]
        raw = await self._llm.chat(messages, temperature=0.8, json_mode=True)
        return parse_proposals_response(raw)
