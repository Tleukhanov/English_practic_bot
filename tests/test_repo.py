import json

import pytest

from storage.sqlite import SQLiteRepository


@pytest.fixture
async def repo(tmp_path):
    db = SQLiteRepository(str(tmp_path / "test.db"))
    await db.connect()
    yield db
    await db.close()


async def test_get_or_create_user_creates_and_reuses(repo):
    first = await repo.get_or_create_user(111, username="alice")
    second = await repo.get_or_create_user(111, username="alice")
    assert first.id == second.id
    assert first.tg_id == 111


async def test_history_returns_only_dialogue_in_order(repo):
    user = await repo.get_or_create_user(222, username="bob")
    await repo.add_user_message(user.id, "I go yesterday", is_correct=False)
    await repo.add_assistant_message(user.id, "Try: I went yesterday.")
    await repo.add_user_message(user.id, "I went yesterday", is_correct=True)
    history = await repo.get_history(user.id, limit=10)
    assert history == [
        {"role": "user", "content": "I go yesterday"},
        {"role": "assistant", "content": "Try: I went yesterday."},
        {"role": "user", "content": "I went yesterday"},
    ]


async def test_history_limits(repo):
    user = await repo.get_or_create_user(333)
    for i in range(5):
        await repo.add_user_message(user.id, f"m{i}")
    history = await repo.get_history(user.id, limit=3)
    assert [h["content"] for h in history] == ["m2", "m3", "m4"]


async def test_stats_counts_and_categories(repo):
    user = await repo.get_or_create_user(444)
    await repo.add_user_message(
        user.id,
        "I good boy",
        is_correct=False,
        issues_json=json.dumps([
            {"category": "grammar", "problem": "нет глагола"},
            {"category": "vocabulary", "problem": "слово"},
        ]),
    )
    await repo.add_user_message(
        user.id,
        "I am a good boy",
        is_correct=False,
        issues_json=json.dumps([{"category": "grammar", "problem": "артикль"}]),
    )
    await repo.add_user_message(user.id, "Perfect sentence", is_correct=True)
    stats = await repo.get_stats(user.id)
    assert stats.total_turns == 3
    assert stats.correct == 1
    assert stats.errors == 2
    assert stats.top_categories == [("grammar", 2), ("vocabulary", 1)]


async def test_stats_empty(repo):
    user = await repo.get_or_create_user(555)
    stats = await repo.get_stats(user.id)
    assert stats.total_turns == 0
    assert stats.correct == 0
    assert stats.errors == 0
    assert stats.top_categories == []
