import sqlite3

import pytest

from storage.repo import MiniLessonSession
from storage.sqlite import SQLiteRepository


@pytest.fixture
async def repo(tmp_path):
    db = SQLiteRepository(str(tmp_path / "miniapp.db"))
    await db.connect()
    yield db
    await db.close()


async def test_miniapp_migration_keeps_chat_lessons_compatible(repo):
    user = await repo.get_or_create_user(2001)
    session = await repo.start_lesson(user.id, "Chat lesson", "{}")

    cursor = await repo._conn.execute("PRAGMA table_info(lesson_sessions)")
    columns = {row["name"] for row in await cursor.fetchall()}
    assert {"mode", "score_json", "deck_preset"}.issubset(columns)

    cursor = await repo._conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'audio_answers'"
    )
    assert await cursor.fetchone() is not None

    cursor = await repo._conn.execute(
        "SELECT mode, status FROM lesson_sessions WHERE id = ?", (session.id,)
    )
    row = await cursor.fetchone()
    assert row["mode"] == "chat"
    assert row["status"] == "active"

    await repo.close()
    await repo.connect()
    cursor = await repo._conn.execute("PRAGMA table_info(audio_answers)")
    assert {row["name"] for row in await cursor.fetchall()} == {
        "id",
        "session_id",
        "word",
        "audio_file",
        "transcript",
        "rating",
    }


async def test_start_mini_lesson_replaces_active_mini_session(repo):
    user = await repo.get_or_create_user(2002)
    deck = '{"title": "Coffee"}'
    first = await repo.start_mini_lesson(user.id, "Coffee", deck, "mixed")
    second = await repo.start_mini_lesson(user.id, "Travel", '{"title": "Travel"}', "cards")

    assert isinstance(first, MiniLessonSession)
    assert first.status == "active"
    assert first.content_json == deck
    assert first.preset == "mixed"
    assert first.score_json is None
    active = await repo.get_active_mini_lesson(user.id)
    assert active is not None
    assert active.id == second.id
    assert active.topic == "Travel"
    assert active.preset == "cards"

    cursor = await repo._conn.execute(
        "SELECT status FROM lesson_sessions WHERE id = ?", (first.id,)
    )
    assert (await cursor.fetchone())["status"] == "aborted"


async def test_save_mini_answers_overwrites_score(repo):
    user = await repo.get_or_create_user(2003)
    session = await repo.start_mini_lesson(user.id, "Chess", "{}", "quiz")

    await repo.save_mini_answers(session.id, '[{"quiz_index": 0, "correct": false}]')
    saved = await repo.get_active_mini_lesson(user.id)
    assert saved is not None
    assert saved.score_json == '[{"quiz_index": 0, "correct": false}]'

    await repo.save_mini_answers(session.id, '[{"quiz_index": 0, "correct": true}]')
    saved = await repo.get_active_mini_lesson(user.id)
    assert saved is not None
    assert saved.score_json == '[{"quiz_index": 0, "correct": true}]'


async def test_finish_mini_lesson_saves_score_and_status(repo):
    user = await repo.get_or_create_user(2004)
    session = await repo.start_mini_lesson(user.id, "Grammar", "{}", "presentation")
    score = '[{"quiz_index": 0, "correct": true}]'

    await repo.finish_mini_lesson(session.id, score)

    assert await repo.get_active_mini_lesson(user.id) is None
    cursor = await repo._conn.execute(
        "SELECT status, score_json FROM lesson_sessions WHERE id = ?", (session.id,)
    )
    row = await cursor.fetchone()
    assert row["status"] == "finished"
    assert row["score_json"] == score


async def test_save_audio_answer_persists_records(repo):
    user = await repo.get_or_create_user(2005)
    session = await repo.start_mini_lesson(user.id, "Speaking", "{}", "dialogue")

    await repo.save_audio_answer(session.id, "hello", "audio-1", "Hello!", 5)
    await repo.save_audio_answer(session.id, "goodbye", "audio-2", "Goodbye", 4)

    cursor = await repo._conn.execute(
        "SELECT word, audio_file, transcript, rating FROM audio_answers "
        "WHERE session_id = ? ORDER BY id",
        (session.id,),
    )
    rows = await cursor.fetchall()
    assert [dict(row) for row in rows] == [
        {"word": "hello", "audio_file": "audio-1", "transcript": "Hello!", "rating": 5},
        {"word": "goodbye", "audio_file": "audio-2", "transcript": "Goodbye", "rating": 4},
    ]


async def test_miniapp_migration_upgrades_legacy_lesson_sessions(tmp_path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE lesson_sessions ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "user_id INTEGER NOT NULL REFERENCES users(id), "
            "topic TEXT NOT NULL, "
            "step INTEGER NOT NULL DEFAULT 0, "
            "task_index INTEGER NOT NULL DEFAULT 0, "
            "content_json TEXT NOT NULL, "
            "status TEXT NOT NULL DEFAULT 'active', "
            "created_at TEXT NOT NULL, "
            "updated_at TEXT NOT NULL"
            ")"
        )
        connection.commit()

    legacy_repo = SQLiteRepository(str(db_path))
    await legacy_repo.connect()
    try:
        user = await legacy_repo.get_or_create_user(2006)
        cursor = await legacy_repo._conn.execute(
            "INSERT INTO lesson_sessions "
            "(user_id, topic, content_json, status, created_at, updated_at) "
            "VALUES (?, 'Legacy', '{}', 'active', 'now', 'now')",
            (user.id,),
        )
        assert cursor.lastrowid is not None
        await legacy_repo._conn.commit()
        cursor = await legacy_repo._conn.execute(
            "SELECT mode, score_json, deck_preset FROM lesson_sessions WHERE user_id = ?",
            (user.id,),
        )
        row = await cursor.fetchone()
        assert row["mode"] == "chat"
        assert row["score_json"] is None
        assert row["deck_preset"] is None
    finally:
        await legacy_repo.close()
