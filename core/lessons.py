"""Структурированные уроки (Фаза 1).

LessonService генерирует цельный мини-урок через LLM (тема -> слова -> ключевые
идеи -> грамматика -> задания). Бот проводит пользователя по шагам урока.
Логика не зависит от Telegram — только LLM и модели данных.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from providers.base import LLMProvider

from .json_utils import extract_json, JsonParseError

LessonParseError = JsonParseError

LESSON_STEPS = ["intro", "vocabulary", "slides", "grammar", "tasks", "recap"]


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
    None: "intermediate (B1)",
    "A1": "beginner (A1)",
    "A2": "elementary (A2)",
    "B1": "intermediate (B1)",
    "B2": "upper-intermediate (B2)",
    "C1": "advanced (C1)",
}

LEVEL_RULES = {
    None: "",
    "A1": "Keep everything simple: basic vocabulary, short sentences, tasks that require only simple answers.",
    "A2": "Use everyday vocabulary and simple sentences; allow tasks with short answers about daily life.",
    "B1": "Use intermediate vocabulary and a few complex sentences; tasks may ask for opinions.",
    "B2": "Use richer vocabulary and complex sentences; tasks may ask for pros/cons and abstract topics.",
    "C1": "Use advanced vocabulary and nuanced structures; tasks may ask to argue and explain abstract ideas.",
}


def _render_system_prompt(level: str | None) -> str:
    return SYSTEM_PROMPT_TEMPLATE.replace(
        "__LEVEL_DESC__", LEVEL_DESCRIPTIONS.get(level, LEVEL_DESCRIPTIONS[None])
    ).replace(
        "__LEVEL_RULES__", LEVEL_RULES.get(level, "")
    )


def build_lesson_prompt(topic: str | None, level: str | None = None) -> list[dict[str, str]]:
    user_message = f"Create a structured lesson. Topic: {topic}" if topic else "Create a structured lesson on an interesting topic of your choice."
    return [
        {"role": "system", "content": _render_system_prompt(level)},
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


class LessonService:
    """Генерация структурированного урока через LLM."""

    def __init__(self, llm: LLMProvider):
        self._llm = llm

    async def generate(self, topic: str | None = None, level: str | None = None) -> LessonContent:
        messages = build_lesson_prompt(topic, level=level)
        raw = await self._llm.chat(messages, temperature=0.7)
        return parse_lesson_response(raw)
