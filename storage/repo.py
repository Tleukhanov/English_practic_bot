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
    ) -> None: ...

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
