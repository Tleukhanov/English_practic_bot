"""Реализация хранилища на aiosqlite.

Таблицы:
- users: профили пользователей Telegram
- messages: история диалога + результаты проверки (is_correct, issues_json)
  Та же таблица даёт и историю для промпта, и статистику практики.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import aiosqlite

from .repo import Repository, Stats, UserRow

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
        await self._conn.commit()

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
            "SELECT id, tg_id, username, first_name FROM users WHERE tg_id = ?",
            (tg_id,),
        )
        row = await cursor.fetchone()
        if row is not None:
            return UserRow(id=row["id"], tg_id=row["tg_id"], username=row["username"], first_name=row["first_name"])

        cursor = await conn.execute(
            "INSERT INTO users (tg_id, username, first_name, created_at) VALUES (?, ?, ?, ?)",
            (tg_id, username, first_name, _now()),
        )
        await conn.commit()
        return UserRow(id=cursor.lastrowid, tg_id=tg_id, username=username, first_name=first_name)

    async def add_user_message(
        self,
        user_id: int,
        content: str,
        *,
        is_correct: bool | None = None,
        issues_json: str = "",
        corrected_text: str = "",
    ) -> None:
        conn = self._require_conn()
        await conn.execute(
            "INSERT INTO messages (user_id, role, content, is_correct, issues_json, corrected_text, created_at) "
            "VALUES (?, 'user', ?, ?, ?, ?, ?)",
            (user_id, content, is_correct, issues_json, corrected_text, _now()),
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

    async def get_stats(self, user_id: int) -> Stats:
        conn = self._require_conn()

        cursor = await conn.execute(
            "SELECT COUNT(*) AS total, COALESCE(SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END), 0) AS correct, "
            "COALESCE(SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END), 0) AS errors "
            "FROM messages WHERE user_id = ? AND role = 'user'",
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
