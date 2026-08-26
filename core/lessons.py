"""Структурированные уроки (Фаза 1).

LessonService генерирует цельный мини-урок через LLM (тема -> слова -> ключевые
идеи -> грамматика -> задания). Бот проводит пользователя по шагам урока.
Логика не зависит от Telegram — только LLM и модели данных.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from providers.base import LLMProvider

from .json_utils import extract_json, extract_json_list, JsonParseError

LessonParseError = JsonParseError

LESSON_STEPS = ["intro", "vocabulary", "slides", "grammar", "tasks", "recap"]

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


SYSTEM_PROMPT_TEMPLATE = """You are an English teacher creating a structured mini-lesson for a Russian-speaking learner at the __LEVEL_DESC__ level.

__LEVEL_RULES__

Create ONE complete, engaging mini-lesson on the requested topic (if no topic given, pick an interesting everyday topic yourself).

Respond ONLY with a single valid JSON object. No markdown, no extra text, no code fences.

JSON schema:
{
  "topic": "topic name",
  "intro": "1-2 friendly English sentences introducing the topic and why it is interesting",
  "vocabulary": [
    {"word": "english word", "translation": "russian translation", "example": "short english example sentence"}
  ],
  "slides": ["short key point in English", "...", "..."],
  "grammar": {
    "rule": "name of the grammar point, e.g. 'Past Simple'",
    "explanation_ru": "short explanation in Russian",
    "examples": ["english example sentence", "..."]
  },
  "tasks": ["a speaking task or question for the student in English", "..."]
}

Rules:
- vocabulary: 6 to 8 words with Russian translations and short examples.
- slides: 3 to 5 concise bullet points that summarize the most useful ideas/words about the topic.
- grammar: pick ONE simple grammar point naturally connected to the topic and suited to the student's level.
- tasks: 3 to 5 short speaking tasks or questions the student should answer in English.
- intro, slides, examples, tasks, words and their examples must be in ENGLISH.
- translations and explanation_ru must be in RUSSIAN.
"""

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
    level: str | None,
    profile: str | None = None,
    recent_topics: list[str] | None = None,
    character_prompt: str = "",
) -> str:
    text = SYSTEM_PROMPT_TEMPLATE.replace(
        "__LEVEL_DESC__", LEVEL_DESCRIPTIONS.get(level, LEVEL_DESCRIPTIONS[None])
    ).replace(
        "__LEVEL_RULES__", LEVEL_RULES.get(level, "")
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


def build_lesson_prompt(
    topic: str | None,
    level: str | None = None,
    profile: str | None = None,
    recent_topics: list[str] | None = None,
    character_prompt: str = "",
) -> list[dict[str, str]]:
    user_message = f"Create a structured lesson. Topic: {topic}" if topic else "Create a structured lesson on an interesting topic of your choice."
    return [
        {"role": "system", "content": _render_system_prompt(level, profile, recent_topics, character_prompt)},
        {
            "role": "system",
            "content": (
                "CRITICAL FORMAT RULE — this overrides all other instructions: "
                "Your response MUST be ONLY a single valid JSON object matching the schema in the system prompt. "
                "No markdown, no text outside JSON, no code fences, no bullet points, no emoji headers. "
                "If you break this rule the student will see an error."
            ),
        },
        {"role": "user", "content": user_message},
    ]


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

    return LessonContent(
        topic=str(payload.get("topic", "")).strip() or "Без темы",
        intro=str(payload.get("intro", "")).strip(),
        vocabulary=vocabulary,
        slides=[str(s) for s in (payload.get("slides") or []) if isinstance(s, str)],
        grammar=grammar,
        tasks=[str(t) for t in (payload.get("tasks") or []) if isinstance(t, str)],
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


class LessonService:
    """Генерация структурированного урока через LLM."""

    def __init__(self, llm: LLMProvider):
        self._llm = llm

    async def generate(
        self,
        topic: str | None = None,
        level: str | None = None,
        profile: str | None = None,
        recent_topics: list[str] | None = None,
        character_prompt: str = "",
    ) -> LessonContent:
        messages = build_lesson_prompt(topic, level=level, profile=profile, recent_topics=recent_topics, character_prompt=character_prompt)
        raw = await self._llm.chat(messages, temperature=0.7, json_mode=True)
        return parse_lesson_response(raw)

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
