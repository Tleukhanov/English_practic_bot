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


class Repository(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def get_or_create_user(self, tg_id: int, username: str | None = None, first_name: str | None = None) -> UserRow: ...

    @abstractmethod
    async def add_user_message(
        self,
        user_id: int,
        content: str,
        *,
        is_correct: bool | None = None,
        issues_json: str = "",
        corrected_text: str = "",
    ) -> None: ...

    @abstractmethod
    async def add_assistant_message(self, user_id: int, content: str) -> None: ...

    @abstractmethod
    async def get_history(self, user_id: int, limit: int) -> list[dict[str, str]]: ...

    @abstractmethod
    async def get_stats(self, user_id: int) -> Stats: ...

    @abstractmethod
    async def start_lesson(self, user_id: int, topic: str, content_json: str) -> LessonSession: ...

    @abstractmethod
    async def get_active_lesson(self, user_id: int) -> LessonSession | None: ...

    @abstractmethod
    async def update_lesson(self, session_id: int, *, step: int | None = None, task_index: int | None = None) -> None: ...

    @abstractmethod
    async def finish_lesson(self, session_id: int) -> None: ...

    @abstractmethod
    async def abort_active_lessons(self, user_id: int) -> None: ...
