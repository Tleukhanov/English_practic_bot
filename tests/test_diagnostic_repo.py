"""Тесты хранилища для диагностики уровня (Фаза 3): уровень и сессии диагностики."""

import json

import aiosqlite
import pytest

from storage.sqlite import SQLiteRepository


@pytest.fixture
async def repo(tmp_path):
    db = SQLiteRepository(str(tmp_path / "test.db"))
    await db.connect()
    yield db
    await db.close()


async def test_user_level_defaults_to_none(repo):
    user = await repo.get_or_create_user(111, username="alice")
    assert user.level is None
    assert await repo.get_level(user.id) is None


async def test_set_and_get_level(repo):
    user = await repo.get_or_create_user(111, username="alice")
    await repo.set_level(user.id, "B1")
    assert await repo.get_level(user.id) == "B1"
    user = await repo.get_or_create_user(111, username="alice")
    assert user.level == "B1"


async def test_migration_adds_level_column_to_old_db(tmp_path):
    db_path = str(tmp_path / "old.db")
    conn = await aiosqlite.connect(db_path)
    await conn.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER NOT NULL UNIQUE,
            username TEXT,
            first_name TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    await conn.commit()
    await conn.close()

    db = SQLiteRepository(db_path)
    await db.connect()
    user = await db.get_or_create_user(999, username="old")
    assert user.level is None
    await db.set_level(user.id, "A2")
    assert await db.get_level(user.id) == "A2"
    await db.close()


async def test_diagnostic_lifecycle(repo):
    user = await repo.get_or_create_user(500)
    questions = json.dumps([{"text": "Introduce yourself", "level_hint": "A1"}], ensure_ascii=False)
    session = await repo.start_diagnostic(user.id, questions)
    assert session.id > 0
    assert session.status == "active"
    assert session.answers_json == "[]"

    active = await repo.get_active_diagnostic(user.id)
    assert active is not None
    assert active.questions_json == questions

    await repo.append_diagnostic_answer(session.id, "Hi, my name is Anna.")
    await repo.append_diagnostic_answer(session.id, "I like coffee.")
    active = await repo.get_active_diagnostic(user.id)
    answers = json.loads(active.answers_json)
    assert answers == ["Hi, my name is Anna.", "I like coffee."]

    await repo.finish_diagnostic(session.id)
    assert await repo.get_active_diagnostic(user.id) is None


async def test_abort_active_diagnostics(repo):
    user = await repo.get_or_create_user(502)
    await repo.start_diagnostic(user.id, "[]")
    await repo.start_diagnostic(user.id, "[]")
    await repo.abort_active_diagnostics(user.id)
    assert await repo.get_active_diagnostic(user.id) is None


async def test_start_diagnostic_replaces_prior_active(repo):
    user = await repo.get_or_create_user(503)
    first = await repo.start_diagnostic(user.id, "[]")
    second = await repo.start_diagnostic(user.id, "[]")
    active = await repo.get_active_diagnostic(user.id)
    assert active.id == second.id
    cursor = await repo._conn.execute(
        "SELECT status FROM diagnostic_sessions WHERE id = ?", (first.id,)
    )
    row = await cursor.fetchone()
    assert row["status"] == "aborted"


async def test_active_diagnostics_are_per_user(repo):
    alice = await repo.get_or_create_user(601)
    bob = await repo.get_or_create_user(602)
    await repo.start_diagnostic(alice.id, "[]")
    assert await repo.get_active_diagnostic(bob.id) is None
    assert await repo.get_active_diagnostic(alice.id) is not None
