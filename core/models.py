"""Доменные модели практики английского."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Issue:
    """Одна найденная ошибка в речи пользователя."""

    category: str  # grammar | vocabulary | pronunciation | style | word_order
    problem: str  # что не так (на русском)
    suggestion: str  # как исправить (на русском)
    correction: str  # исправленный фрагмент (на английском)


@dataclass
class PracticeResult:
    """Результат проверки одной реплики пользователя."""

    is_correct: bool
    corrected_text: str  # полная исправленная версия фразы
    issues: list[Issue] = field(default_factory=list)
    next_question: str = ""  # следующий вопрос диалога (на английском)
    spoken_reply: str = ""  # реплика бота для озвучки (естественный ответ, не пересказ)
    tone: str = ""  # короткая одобрительная фраза (на русском)
