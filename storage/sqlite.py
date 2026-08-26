"""Реализация хранилища на aiosqlite.

Таблицы:
- users: профили пользователей Telegram (включая CEFR-уровень, Фаза 3)
- messages: история диалога + результаты проверки (is_correct, issues_json)
  Та же таблица даёт и историю для промпта, и статистику практики.
- lesson_sessions: состояние структурированных уроков
- diagnostic_sessions: состояние диагностики уровня (Фаза 3)
- user_profiles: память пользователя (Фаза 4): цели, интересы, слабые места
- lesson_notes: итоги уроков (Фаза 5): слова, грамматика, ошибки, рекомендация
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import aiosqlite

from .repo import (
    DiagnosticSession,
    LessonNote,
    LessonSession,
    Repository,
    Stats,
    TopicProposal,
    UserProfile,
    UserRow,
    WeakArea,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id INTEGER NOT NULL UNIQUE,
    username TEXT,
    first_name TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    is_correct INTEGER,
    issues_json TEXT,
    corrected_text TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_user ON messages(user_id, id);

CREATE TABLE IF NOT EXISTS lesson_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    topic TEXT NOT NULL,
    step INTEGER NOT NULL DEFAULT 0,
    task_index INTEGER NOT NULL DEFAULT 0,
    content_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lesson_user ON lesson_sessions(user_id, status);

CREATE TABLE IF NOT EXISTS diagnostic_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    questions_json TEXT NOT NULL,
    answers_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_diagnostic_user ON diagnostic_sessions(user_id, status);

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    goal TEXT NOT NULL DEFAULT '',
    interests TEXT NOT NULL DEFAULT '',
    weak_areas TEXT NOT NULL DEFAULT '',
    preferred_format TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lesson_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    lesson_id INTEGER NOT NULL REFERENCES lesson_sessions(id),
    topic TEXT NOT NULL DEFAULT '',
    vocabulary TEXT NOT NULL DEFAULT '',
    grammar TEXT NOT NULL DEFAULT '',
    speaking TEXT NOT NULL DEFAULT '',
    mistakes TEXT NOT NULL DEFAULT '',
    recommendation TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lesson_notes_user ON lesson_notes(user_id, id);

CREATE TABLE IF NOT EXISTS topic_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    topic TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_topic_proposals_user ON topic_proposals(user_id, id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteRepository(Repository):
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(_SCHEMA)
        await self._migrate()
        await self._conn.commit()

    async def _migrate(self) -> None:
        """Идемпотентные миграции для БД, созданных до появления новых колонок."""
        cursor = await self._conn.execute("PRAGMA table_info(users)")
        rows = await cursor.fetchall()
        columns = {row["name"] for row in rows}
        if "level" not in columns:
            await self._conn.execute("ALTER TABLE users ADD COLUMN level TEXT")

        cursor = await self._conn.execute("PRAGMA table_info(messages)")
        columns = {row["name"] for row in await cursor.fetchall()}
        if "lesson_id" not in columns:
            await self._conn.execute("ALTER TABLE messages ADD COLUMN lesson_id INTEGER")

        cursor = await self._conn.execute("PRAGMA table_info(user_profiles)")
        columns = {row["name"] for row in await cursor.fetchall()}
        if "character" not in columns:
            await self._conn.execute("ALTER TABLE user_profiles ADD COLUMN character TEXT NOT NULL DEFAULT ''")

        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS user_weak_areas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                area TEXT NOT NULL,
                incorrect_count INTEGER NOT NULL DEFAULT 0,
                correct_count INTEGER NOT NULL DEFAULT 0,
                last_seen TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT '',
                UNIQUE(user_id, area)
            )
        """)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    def _require_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Хранилище не подключено: вызовите connect()")
        return self._conn

    async def get_or_create_user(
        self,
        tg_id: int,
        username: str | None = None,
        first_name: str | None = None,
    ) -> UserRow:
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT id, tg_id, username, first_name, level FROM users WHERE tg_id = ?",
            (tg_id,),
        )
        row = await cursor.fetchone()
        if row is not None:
            return UserRow(
                id=row["id"],
                tg_id=row["tg_id"],
                username=row["username"],
                first_name=row["first_name"],
                level=row["level"],
            )

        cursor = await conn.execute(
            "INSERT INTO users (tg_id, username, first_name, created_at) VALUES (?, ?, ?, ?)",
            (tg_id, username, first_name, _now()),
        )
        await conn.commit()
        return UserRow(id=cursor.lastrowid, tg_id=tg_id, username=username, first_name=first_name)

    async def set_level(self, user_id: int, level: str) -> None:
        conn = self._require_conn()
        await conn.execute("UPDATE users SET level = ? WHERE id = ?", (level, user_id))
        await conn.commit()

    async def get_level(self, user_id: int) -> str | None:
        conn = self._require_conn()
        cursor = await conn.execute("SELECT level FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        return row["level"] if row else None

    async def get_profile(self, user_id: int) -> UserProfile | None:
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT user_id, goal, interests, weak_areas, preferred_format, notes, character, updated_at "
            "FROM user_profiles WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return UserProfile(
            user_id=row["user_id"],
            goal=row["goal"],
            interests=row["interests"],
            weak_areas=row["weak_areas"],
            preferred_format=row["preferred_format"],
            notes=row["notes"],
            character=row["character"],
            updated_at=row["updated_at"],
        )

    async def save_profile(self, profile: UserProfile) -> None:
        conn = self._require_conn()
        await conn.execute(
            "INSERT INTO user_profiles "
            "(user_id, goal, interests, weak_areas, preferred_format, notes, character, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "goal = excluded.goal, interests = excluded.interests, weak_areas = excluded.weak_areas, "
            "preferred_format = excluded.preferred_format, notes = excluded.notes, "
            "character = excluded.character, "
            "updated_at = excluded.updated_at",
            (
                profile.user_id,
                profile.goal,
                profile.interests,
                profile.weak_areas,
                profile.preferred_format,
                profile.notes,
                profile.character,
                profile.updated_at,
            ),
        )
        await conn.commit()

    async def add_user_message(
        self,
        user_id: int,
        content: str,
        *,
        is_correct: bool | None = None,
        issues_json: str = "",
        corrected_text: str = "",
        lesson_id: int | None = None,
    ) -> None:
        conn = self._require_conn()
        await conn.execute(
            "INSERT INTO messages (user_id, role, content, is_correct, issues_json, corrected_text, lesson_id, created_at) "
            "VALUES (?, 'user', ?, ?, ?, ?, ?, ?)",
            (user_id, content, is_correct, issues_json, corrected_text, lesson_id, _now()),
        )
        await conn.commit()

    async def add_assistant_message(self, user_id: int, content: str) -> None:
        conn = self._require_conn()
        await conn.execute(
            "INSERT INTO messages (user_id, role, content, created_at) VALUES (?, 'assistant', ?, ?)",
            (user_id, content, _now()),
        )
        await conn.commit()

    async def get_history(self, user_id: int, limit: int) -> list[dict[str, str]]:
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT role, content FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        rows = await cursor.fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]

    async def get_lesson_messages(self, lesson_id: int) -> list[dict]:
        """Ответы пользователя во время конкретного урока — для итоговой заметки."""
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT content, is_correct, issues_json, corrected_text FROM messages "
            "WHERE lesson_id = ? AND role = 'user' ORDER BY id ASC",
            (lesson_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "content": row["content"],
                "is_correct": bool(row["is_correct"]),
                "issues_json": row["issues_json"] or "",
                "corrected_text": row["corrected_text"] or "",
            }
            for row in rows
        ]

    async def get_stats(self, user_id: int) -> Stats:
        conn = self._require_conn()

        cursor = await conn.execute(
            "SELECT COUNT(*) AS total, COALESCE(SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END), 0) AS correct, "
            "COALESCE(SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END), 0) AS errors "
            "FROM messages WHERE user_id = ? AND role = 'user' AND is_correct IS NOT NULL",
            (user_id,),
        )
        totals = await cursor.fetchone()

        cursor = await conn.execute(
            "SELECT issues_json FROM messages "
            "WHERE user_id = ? AND role = 'user' AND issues_json IS NOT NULL AND issues_json != '' "
            "ORDER BY id DESC LIMIT 200",
            (user_id,),
        )
        rows = await cursor.fetchall()

        categories: dict[str, int] = {}
        for row in rows:
            try:
                issues = json.loads(row["issues_json"])
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(issues, list):
                continue
            for issue in issues:
                if isinstance(issue, dict) and issue.get("category"):
                    cat = str(issue["category"])
                    categories[cat] = categories.get(cat, 0) + 1

        top = sorted(categories.items(), key=lambda kv: kv[1], reverse=True)[:5]
        return Stats(
            total_turns=totals["total"] if totals else 0,
            correct=totals["correct"] if totals else 0,
            errors=totals["errors"] if totals else 0,
            top_categories=top,
        )

    async def get_last_correction(self, user_id: int) -> dict | None:
        """Последний разбор фразы пользователя для кнопки «Показать ошибку»."""
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT is_correct, corrected_text, issues_json FROM messages "
            "WHERE user_id = ? AND role = 'user' AND is_correct = 0 "
            "AND corrected_text IS NOT NULL AND corrected_text != '' "
            "ORDER BY id DESC LIMIT 1",
            (user_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return {
            "is_correct": bool(row["is_correct"]),
            "corrected_text": row["corrected_text"],
            "issues_json": row["issues_json"] or "",
        }

    # ---------- уроки ----------

    @staticmethod
    def _row_to_lesson(row) -> LessonSession:
        return LessonSession(
            id=row["id"],
            user_id=row["user_id"],
            topic=row["topic"],
            step=row["step"],
            task_index=row["task_index"],
            content_json=row["content_json"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def start_lesson(self, user_id: int, topic: str, content_json: str) -> LessonSession:
        conn = self._require_conn()
        now = _now()
        # Атомарно закрываем старые активные уроки, чтобы не копились «зависшие» сессии.
        await conn.execute(
            "UPDATE lesson_sessions SET status = 'aborted', updated_at = ? WHERE user_id = ? AND status = 'active'",
            (now, user_id),
        )
        cursor = await conn.execute(
            "INSERT INTO lesson_sessions (user_id, topic, content_json, status, created_at, updated_at) "
            "VALUES (?, ?, ?, 'active', ?, ?)",
            (user_id, topic, content_json, now, now),
        )
        await conn.commit()
        session_id = cursor.lastrowid
        return LessonSession(
            id=session_id,
            user_id=user_id,
            topic=topic,
            step=0,
            task_index=0,
            content_json=content_json,
            status="active",
            created_at=now,
            updated_at=now,
        )

    async def get_active_lesson(self, user_id: int) -> LessonSession | None:
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT * FROM lesson_sessions WHERE user_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
            (user_id,),
        )
        row = await cursor.fetchone()
        return self._row_to_lesson(row) if row else None

    async def update_lesson(self, session_id: int, *, step: int | None = None, task_index: int | None = None) -> None:
        conn = self._require_conn()
        updates: list[str] = []
        params: list[object] = []
        if step is not None:
            updates.append("step = ?")
            params.append(step)
        if task_index is not None:
            updates.append("task_index = ?")
            params.append(task_index)
        if not updates:
            return
        updates.append("updated_at = ?")
        params.append(_now())
        params.append(session_id)
        await conn.execute(f"UPDATE lesson_sessions SET {', '.join(updates)} WHERE id = ?", params)
        await conn.commit()

    async def finish_lesson(self, session_id: int) -> None:
        conn = self._require_conn()
        await conn.execute(
            "UPDATE lesson_sessions SET status = 'finished', updated_at = ? WHERE id = ?",
            (_now(), session_id),
        )
        await conn.commit()

    async def finish_active_lessons(self, user_id: int) -> None:
        conn = self._require_conn()
        await conn.execute(
            "UPDATE lesson_sessions SET status = 'finished', updated_at = ? WHERE user_id = ? AND status = 'active'",
            (_now(), user_id),
        )
        await conn.commit()

    async def abort_active_lessons(self, user_id: int) -> None:
        conn = self._require_conn()
        await conn.execute(
            "UPDATE lesson_sessions SET status = 'aborted', updated_at = ? WHERE user_id = ? AND status = 'active'",
            (_now(), user_id),
        )
        await conn.commit()

    async def add_lesson_note(self, note: LessonNote) -> int:
        conn = self._require_conn()
        cursor = await conn.execute(
            "INSERT INTO lesson_notes "
            "(user_id, lesson_id, topic, vocabulary, grammar, speaking, mistakes, recommendation, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                note.user_id,
                note.lesson_id,
                note.topic,
                note.vocabulary,
                note.grammar,
                note.speaking,
                note.mistakes,
                note.recommendation,
                note.created_at or _now(),
            ),
        )
        await conn.commit()
        return cursor.lastrowid

    async def get_lesson_notes(self, user_id: int, limit: int = 10) -> list[LessonNote]:
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT id, user_id, lesson_id, topic, vocabulary, grammar, speaking, mistakes, recommendation, created_at "
            "FROM lesson_notes WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        rows = await cursor.fetchall()
        return [
            LessonNote(
                id=row["id"],
                user_id=row["user_id"],
                lesson_id=row["lesson_id"],
                topic=row["topic"],
                vocabulary=row["vocabulary"],
                grammar=row["grammar"],
                speaking=row["speaking"],
                mistakes=row["mistakes"],
                recommendation=row["recommendation"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    # ---------- диагностика уровня (Фаза 3) ----------

    @staticmethod
    def _row_to_diagnostic(row) -> DiagnosticSession:
        return DiagnosticSession(
            id=row["id"],
            user_id=row["user_id"],
            questions_json=row["questions_json"],
            answers_json=row["answers_json"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def start_diagnostic(self, user_id: int, questions_json: str) -> DiagnosticSession:
        conn = self._require_conn()
        now = _now()
        # Атомарно закрываем старые активные диагностики, чтобы не копились «зависшие» сессии.
        await conn.execute(
            "UPDATE diagnostic_sessions SET status = 'aborted', updated_at = ? "
            "WHERE user_id = ? AND status = 'active'",
            (now, user_id),
        )
        cursor = await conn.execute(
            "INSERT INTO diagnostic_sessions (user_id, questions_json, status, created_at, updated_at) "
            "VALUES (?, ?, 'active', ?, ?)",
            (user_id, questions_json, now, now),
        )
        await conn.commit()
        return DiagnosticSession(
            id=cursor.lastrowid,
            user_id=user_id,
            questions_json=questions_json,
            answers_json="[]",
            status="active",
            created_at=now,
            updated_at=now,
        )

    async def get_active_diagnostic(self, user_id: int) -> DiagnosticSession | None:
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT * FROM diagnostic_sessions WHERE user_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
            (user_id,),
        )
        row = await cursor.fetchone()
        return self._row_to_diagnostic(row) if row else None

    async def append_diagnostic_answer(self, session_id: int, answer: str) -> None:
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT answers_json FROM diagnostic_sessions WHERE id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
        answers: list[str] = []
        if row and row["answers_json"]:
            try:
                parsed = json.loads(row["answers_json"])
            except (json.JSONDecodeError, TypeError):
                parsed = None
            if isinstance(parsed, list):
                answers = [str(a) for a in parsed]
        answers.append(answer)
        await conn.execute(
            "UPDATE diagnostic_sessions SET answers_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(answers, ensure_ascii=False), _now(), session_id),
        )
        await conn.commit()

    async def finish_diagnostic(self, session_id: int) -> None:
        conn = self._require_conn()
        await conn.execute(
            "UPDATE diagnostic_sessions SET status = 'finished', updated_at = ? WHERE id = ?",
            (_now(), session_id),
        )
        await conn.commit()

    async def abort_active_diagnostics(self, user_id: int) -> None:
        conn = self._require_conn()
        await conn.execute(
            "UPDATE diagnostic_sessions SET status = 'aborted', updated_at = ? "
            "WHERE user_id = ? AND status = 'active'",
            (_now(), user_id),
        )
        await conn.commit()

    # ---------- предложения тем (Фаза 2) ----------

    async def save_topic_proposals(self, user_id: int, proposals: list[TopicProposal]) -> None:
        conn = self._require_conn()
        await conn.execute("DELETE FROM topic_proposals WHERE user_id = ?", (user_id,))
        for p in proposals:
            await conn.execute(
                "INSERT INTO topic_proposals (user_id, topic, description, created_at) VALUES (?, ?, ?, ?)",
                (user_id, p.topic, p.description, p.created_at or _now()),
            )
        await conn.commit()

    async def get_topic_proposal(self, proposal_id: int) -> TopicProposal | None:
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT id, user_id, topic, description, created_at FROM topic_proposals WHERE id = ?",
            (proposal_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return TopicProposal(
            id=row["id"],
            user_id=row["user_id"],
            topic=row["topic"],
            description=row["description"],
            created_at=row["created_at"],
        )

    async def get_topic_proposals(self, user_id: int) -> list[TopicProposal]:
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT id, user_id, topic, description, created_at FROM topic_proposals WHERE user_id = ? ORDER BY id",
            (user_id,),
        )
        return [
            TopicProposal(
                id=row["id"],
                user_id=row["user_id"],
                topic=row["topic"],
                description=row["description"],
                created_at=row["created_at"],
            )
            for row in await cursor.fetchall()
        ]

    async def delete_topic_proposals(self, user_id: int) -> None:
        conn = self._require_conn()
        await conn.execute("DELETE FROM topic_proposals WHERE user_id = ?", (user_id,))
        await conn.commit()

    async def get_topic_proposals(self, user_id: int) -> list[TopicProposal]:
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT topic, description FROM topic_proposals WHERE user_id = ? ORDER BY id",
            (user_id,),
        )
        return [
            TopicProposal(topic=row["topic"], description=row["description"])
            for row in await cursor.fetchall()
        ]

    async def get_practice_dates(self, user_id: int, limit: int = 50) -> list[str]:
        """Возвращает уникальные даты (YYYY-MM-DD) последних практик пользователя."""
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT DISTINCT substr(created_at, 1, 10) AS day "
            "FROM messages WHERE user_id = ? AND role = 'user' "
            "ORDER BY day DESC LIMIT ?",
            (user_id, limit),
        )
        return [row["day"] for row in await cursor.fetchall()]

    # ---------- weak areas (Фаза 13) ----------

    async def get_weak_areas(self, user_id: int) -> list[WeakArea]:
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT id, user_id, area, incorrect_count, correct_count, last_seen, created_at "
            "FROM user_weak_areas WHERE user_id = ? "
            "ORDER BY (incorrect_count * 2.0 + "
            "CASE WHEN last_seen != '' THEN "
            "  MAX(0, 14 - CAST((julianday('now') - julianday(last_seen)) AS INTEGER)) / 14.0 "
            "ELSE 0 END) DESC",
            (user_id,),
        )
        return [
            WeakArea(
                id=row["id"],
                user_id=row["user_id"],
                area=row["area"],
                incorrect_count=row["incorrect_count"],
                correct_count=row["correct_count"],
                last_seen=row["last_seen"],
                created_at=row["created_at"],
            )
            for row in await cursor.fetchall()
        ]

    async def upsert_weak_area(
        self,
        user_id: int,
        area: str,
        incorrect_increment: int = 0,
        correct_increment: int = 0,
        last_seen: str = "",
    ) -> None:
        conn = self._require_conn()
        now = last_seen or ""
        await conn.execute(
            """
            INSERT INTO user_weak_areas (user_id, area, incorrect_count, correct_count, last_seen, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, area) DO UPDATE SET
                incorrect_count = incorrect_count + excluded.incorrect_count,
                correct_count = correct_count + excluded.correct_count,
                last_seen = CASE WHEN excluded.last_seen != '' THEN excluded.last_seen ELSE user_weak_areas.last_seen END
            """,
            (user_id, area, incorrect_increment, correct_increment, now, now),
        )
        await conn.commit()

    async def delete_weak_area(self, user_id: int, area: str) -> None:
        conn = self._require_conn()
        await conn.execute(
            "DELETE FROM user_weak_areas WHERE user_id = ? AND area = ?",
            (user_id, area),
        )
        await conn.commit()

    async def get_all_users(self) -> list[UserRow]:
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT id, tg_id, username, first_name, level FROM users"
        )
        rows = await cursor.fetchall()
        return [
            UserRow(
                id=row["id"],
                tg_id=row["tg_id"],
                username=row["username"],
                first_name=row["first_name"],
                level=row["level"],
            )
            for row in rows
        ]
