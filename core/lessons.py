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


SYSTEM_PROMPT = """You are an English teacher creating a structured mini-lesson for a Russian-speaking learner at an intermediate (B1) level.

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
- grammar: pick ONE simple grammar point naturally connected to the topic.
- tasks: 3 to 5 short speaking tasks or questions the student should answer in English.
- intro, slides, examples, tasks, words and their examples must be in ENGLISH.
- translations and explanation_ru must be in RUSSIAN.
"""


def build_lesson_prompt(topic: str | None) -> list[dict[str, str]]:
    user_message = f"Create a structured lesson. Topic: {topic}" if topic else "Create a structured lesson on an interesting topic of your choice."
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
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

    async def generate(self, topic: str | None = None) -> LessonContent:
        messages = build_lesson_prompt(topic)
        raw = await self._llm.chat(messages, temperature=0.7)
        return parse_lesson_response(raw)
