"""Абстракция хранилища — чтобы позже можно было пересесть на Postgres без правки бота."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class UserRow:
    id: int
    tg_id: int
    username: str | None = None
    first_name: str | None = None
    level: str | None = None  # CEFR: A1 | A2 | B1 | B2 | C1 | None


@dataclass
class UserProfile:
    """Память пользователя (Фаза 4): то, что LLM выводит из диалога.

    Поля хранятся как текст (списки — через запятую), чтобы было просто
    встраивать их в промпты.
    """

    user_id: int
    goal: str = ""  # цель обучения, коротко (на русском)
    interests: str = ""  # интересы, через запятую
    weak_areas: str = ""  # повторяющиеся ошибки, через запятую (напр. "Present Perfect, артикли")
    preferred_format: str = ""  # voice | text | ""
    notes: str = ""  # особенности поведения (на русском)
    character: str = ""  # ID выбранного персонажа (напр. "chill", "toxic") или "" (по умолчанию)
    updated_at: str = ""


@dataclass
class Stats:
    total_turns: int = 0  # всего реплик пользователя
    correct: int = 0  # корректных
    errors: int = 0  # с ошибками
    top_categories: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class LessonSession:
    id: int
    user_id: int
    topic: str
    step: int  # индекс шага в core.lessons.LESSON_STEPS
    task_index: int  # индекс текущего задания внутри шага "tasks"
    content_json: str
    status: str  # active | finished | aborted
    created_at: str
    updated_at: str


@dataclass
class DiagnosticSession:
    id: int
    user_id: int
    questions_json: str  # список DiagnosticTask в JSON
    answers_json: str  # список ответов пользователя в JSON
    status: str  # active | finished | aborted
    created_at: str
    updated_at: str


@dataclass
class LessonNote:
    """Структурированный итог урока (Фаза 5), сгенерированный LLM."""

    id: int = 0
    user_id: int = 0
    lesson_id: int = 0
    topic: str = ""
    vocabulary: str = ""  # +N новых слов, какие использовал
    grammar: str = ""  # тема и как усвоена
    speaking: str = ""  # оценка говорения
    mistakes: str = ""  # повторяющиеся ошибки
    recommendation: str = ""  # что повторить дальше
    created_at: str = ""


@dataclass
class TopicProposal:
    """Предложение темы для урока (Фаза 2). Временная запись до выбора пользователя."""

    id: int = 0
    user_id: int = 0
    topic: str = ""
    description: str = ""
    created_at: str = ""


@dataclass
class WeakArea:
    """Слабая область пользователя (Фаза 13)."""

    id: int = 0
    user_id: int = 0
    area: str = ""
    incorrect_count: int = 0
    correct_count: int = 0
    last_seen: str = ""
    created_at: str = ""

    @property
    def priority_score(self) -> float:
        """Чем выше, тем важнее."""
        from datetime import datetime, timezone
        age_days = 999.0
        if self.last_seen:
            try:
                dt = datetime.fromisoformat(self.last_seen.replace("Z", "+00:00"))
                age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400
            except (ValueError, TypeError):
                pass
        recency_bonus = max(0, 14 - age_days) / 14.0
        error_weight = self.incorrect_count / max(1, self.incorrect_count + self.correct_count)
        return error_weight * 2.0 + recency_bonus


@dataclass
class SRSWord:
    """Слово в системе spaced repetition (Фаза 13)."""

    id: int = 0
    user_id: int = 0
    word: str = ""
    translation: str = ""
    example: str = ""
    lesson_id: int = 0
    next_review: str = ""
    interval_days: int = 1
    ease_factor: float = 2.5
    correct_count: int = 0
    last_reviewed: str = ""
    created_at: str = ""


@dataclass
class LeaderboardRow:
    """Строка лидерборда."""

    user_id: int = 0
    username: str | None = None
    first_name: str | None = None
    level: str | None = None
    xp: int = 0
    total_lessons: int = 0
    streak_days: int = 0


class Repository(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def get_or_create_user(self, tg_id: int, username: str | None = None, first_name: str | None = None) -> UserRow: ...

    @abstractmethod
    async def set_level(self, user_id: int, level: str) -> None: ...

    @abstractmethod
    async def get_level(self, user_id: int) -> str | None: ...

    @abstractmethod
    async def get_profile(self, user_id: int) -> UserProfile | None: ...

    @abstractmethod
    async def save_profile(self, profile: UserProfile) -> None: ...

    @abstractmethod
    async def add_user_message(
        self,
        user_id: int,
        content: str,
        *,
        is_correct: bool | None = None,
        issues_json: str = "",
        corrected_text: str = "",
        lesson_id: int | None = None,
    ) -> int: ...

    @abstractmethod
    async def add_assistant_message(self, user_id: int, content: str) -> None: ...

    @abstractmethod
    async def get_history(self, user_id: int, limit: int) -> list[dict[str, str]]: ...

    @abstractmethod
    async def get_lesson_messages(self, lesson_id: int) -> list[dict]: ...

    @abstractmethod
    async def get_stats(self, user_id: int) -> Stats: ...

    @abstractmethod
    async def get_last_correction(self, user_id: int) -> dict | None: ...

    @abstractmethod
    async def get_user_message(self, user_id: int, message_id: int) -> dict | None: ...

    @abstractmethod
    async def start_lesson(self, user_id: int, topic: str, content_json: str) -> LessonSession: ...

    @abstractmethod
    async def get_active_lesson(self, user_id: int) -> LessonSession | None: ...

    @abstractmethod
    async def update_lesson(self, session_id: int, *, step: int | None = None, task_index: int | None = None) -> None: ...

    @abstractmethod
    async def finish_lesson(self, session_id: int) -> None: ...

    @abstractmethod
    async def finish_active_lessons(self, user_id: int) -> None: ...

    @abstractmethod
    async def abort_active_lessons(self, user_id: int) -> None: ...

    @abstractmethod
    async def add_lesson_note(self, note: LessonNote) -> int: ...

    @abstractmethod
    async def get_lesson_notes(self, user_id: int, limit: int = 10) -> list[LessonNote]: ...

    @abstractmethod
    async def get_all_users(self) -> list[UserRow]: ...

    # ---------- диагностика уровня (Фаза 3) ----------

    @abstractmethod
    async def start_diagnostic(self, user_id: int, questions_json: str) -> DiagnosticSession: ...

    @abstractmethod
    async def get_active_diagnostic(self, user_id: int) -> DiagnosticSession | None: ...

    @abstractmethod
    async def append_diagnostic_answer(self, session_id: int, answer: str) -> None: ...

    @abstractmethod
    async def finish_diagnostic(self, session_id: int) -> None: ...

    @abstractmethod
    async def abort_active_diagnostics(self, user_id: int) -> None: ...

    # ---------- предложения тем (Фаза 2) ----------

    @abstractmethod
    async def save_topic_proposals(self, user_id: int, proposals: list[TopicProposal]) -> None: ...

    @abstractmethod
    async def get_topic_proposal(self, proposal_id: int) -> TopicProposal | None: ...

    @abstractmethod
    async def get_topic_proposals(self, user_id: int) -> list[TopicProposal]: ...

    @abstractmethod
    async def delete_topic_proposals(self, user_id: int) -> None: ...

    @abstractmethod
    async def get_practice_dates(self, user_id: int, limit: int = 50) -> list[str]: ...

    # ---------- слабые области (Фаза 13) ----------

    @abstractmethod
    async def get_weak_areas(self, user_id: int) -> list[WeakArea]: ...

    @abstractmethod
    async def upsert_weak_area(
        self,
        user_id: int,
        area: str,
        incorrect_increment: int = 0,
        correct_increment: int = 0,
        last_seen: str = "",
    ) -> None: ...

    @abstractmethod
    async def delete_weak_area(self, user_id: int, area: str) -> None: ...

    # ---------- SRS vocabulary (Фаза 13) ----------

    @abstractmethod
    async def add_srs_word(self, word: SRSWord) -> int: ...

    @abstractmethod
    async def get_srs_word(self, user_id: int, word: str) -> SRSWord | None: ...

    @abstractmethod
    async def get_srs_word_by_id(self, word_id: int) -> SRSWord | None: ...

    @abstractmethod
    async def get_srs_words(self, user_id: int, limit: int = 100) -> list[SRSWord]: ...

    @abstractmethod
    async def update_srs_word(self, word: SRSWord) -> None: ...

    # ---------- лидерборд ----------

    @abstractmethod
    async def get_leaderboard(self, limit: int = 20) -> list[LeaderboardRow]: ...
