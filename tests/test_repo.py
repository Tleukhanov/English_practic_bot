import json

import pytest

from storage.sqlite import SQLiteRepository
from storage.repo import LessonNote, TopicProposal


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


async def test_get_last_correction_returns_latest_failed_phrase(repo):
    user = await repo.get_or_create_user(556)
    assert await repo.get_last_correction(user.id) is None

    await repo.add_user_message(user.id, "I good", is_correct=False)
    await repo.add_user_message(
        user.id,
        "He go school",
        is_correct=False,
        issues_json=json.dumps([{"category": "grammar", "problem": "глагол"}]),
        corrected_text="He goes to school.",
    )
    await repo.add_user_message(user.id, "Perfect now", is_correct=True, corrected_text="Perfect now.")

    last = await repo.get_last_correction(user.id)
    assert last is not None
    assert last["is_correct"] is False
    assert last["corrected_text"] == "He goes to school."
    issues = json.loads(last["issues_json"])
    assert issues == [{"category": "grammar", "problem": "глагол"}]


async def test_lesson_lifecycle(repo):
    user = await repo.get_or_create_user(600)
    session = await repo.start_lesson(user.id, "Travelling", '{"topic": "Travelling"}')
    assert session.id > 0
    assert session.step == 0
    assert session.status == "active"

    active = await repo.get_active_lesson(user.id)
    assert active is not None
    assert active.topic == "Travelling"
    assert active.content_json == '{"topic": "Travelling"}'

    await repo.update_lesson(session.id, step=2, task_index=1)
    active = await repo.get_active_lesson(user.id)
    assert active.step == 2
    assert active.task_index == 1

    await repo.finish_lesson(session.id)
    assert await repo.get_active_lesson(user.id) is None


async def test_abort_active_lessons(repo):
    user = await repo.get_or_create_user(700)
    await repo.start_lesson(user.id, "Chess", "{}")
    await repo.start_lesson(user.id, "Chess 2", "{}")
    await repo.abort_active_lessons(user.id)
    assert await repo.get_active_lesson(user.id) is None


async def test_start_lesson_replaces_prior_active(repo):
    user = await repo.get_or_create_user(710)
    first = await repo.start_lesson(user.id, "Chess", "{}")
    second = await repo.start_lesson(user.id, "Cooking", "{}")
    active = await repo.get_active_lesson(user.id)
    assert active.topic == "Cooking"
    # старый урок не остаётся активным
    cursor = await repo._conn.execute(
        "SELECT status FROM lesson_sessions WHERE id = ?", (first.id,)
    )
    row = await cursor.fetchone()
    assert row["status"] == "aborted"
    assert second.id != first.id


async def test_finish_active_lessons_closes_all(repo):
    user = await repo.get_or_create_user(720)
    first = await repo.start_lesson(user.id, "Chess", "{}")
    second = await repo.start_lesson(user.id, "Cooking", "{}")
    await repo.finish_active_lessons(user.id)
    assert await repo.get_active_lesson(user.id) is None
    cursor = await repo._conn.execute(
        "SELECT status FROM lesson_sessions WHERE id IN (?, ?)", (first.id, second.id)
    )
    statuses = {row["status"] for row in await cursor.fetchall()}
    assert statuses == {"aborted", "finished"}
    assert "active" not in statuses


async def test_active_lessons_are_per_user(repo):
    alice = await repo.get_or_create_user(801)
    bob = await repo.get_or_create_user(802)
    await repo.start_lesson(alice.id, "AI", "{}")
    assert await repo.get_active_lesson(bob.id) is None
    assert await repo.get_active_lesson(alice.id) is not None


async def test_lesson_messages_linked_and_filtered(repo):
    user = await repo.get_or_create_user(900)
    session = await repo.start_lesson(user.id, "Chess", "{}")
    other = await repo.start_lesson(user.id, "Music", "{}")
    await repo.finish_active_lessons(user.id)

    await repo.add_user_message(user.id, "I play chess", lesson_id=session.id)
    await repo.add_user_message(
        user.id,
        "I goed to gym",
        lesson_id=session.id,
        is_correct=False,
        corrected_text="I went to the gym.",
        issues_json='[{"category": "grammar", "problem": "время"}]',
    )
    await repo.add_user_message(user.id, "unrelated", lesson_id=other.id)

    messages = await repo.get_lesson_messages(session.id)
    assert [m["content"] for m in messages] == ["I play chess", "I goed to gym"]
    assert messages[1]["is_correct"] is False
    assert messages[1]["corrected_text"] == "I went to the gym."
    assert "grammar" in messages[1]["issues_json"]


async def test_lesson_notes_roundtrip(repo):
    user = await repo.get_or_create_user(901)
    session = await repo.start_lesson(user.id, "Cooking", "{}")

    note = LessonNote(
        user_id=user.id,
        lesson_id=session.id,
        topic="Cooking",
        vocabulary="+5 новых слов",
        grammar="Present Simple — ок",
        speaking="улучшение",
        mistakes="артикли",
        recommendation="повторить артикли",
    )
    note_id = await repo.add_lesson_note(note)
    assert note_id > 0

    notes = await repo.get_lesson_notes(user.id)
    assert len(notes) == 1
    saved = notes[0]
    assert saved.id == note_id
    assert saved.lesson_id == session.id
    assert saved.topic == "Cooking"
    assert saved.recommendation == "повторить артикли"
    assert saved.created_at  # дата заполняется

    other = await repo.get_lesson_notes(999999)
    assert other == []


async def test_topic_proposals_save_and_get(repo):
    user = await repo.get_or_create_user(100)
    proposals = [
        TopicProposal(topic="Cooking", description="Learn food vocabulary"),
        TopicProposal(topic="Travel", description="Explore travel phrases"),
        TopicProposal(topic="Sports", description="Sports vocabulary"),
    ]
    await repo.save_topic_proposals(user.id, proposals)

    first = await repo.get_topic_proposal(1)
    assert first is not None
    assert first.topic == "Cooking"
    assert first.user_id == user.id

    third = await repo.get_topic_proposal(3)
    assert third.topic == "Sports"

    assert await repo.get_topic_proposal(999) is None


async def test_topic_proposals_replaces_on_resave(repo):
    user = await repo.get_or_create_user(200)
    await repo.save_topic_proposals(user.id, [
        TopicProposal(topic="A", description="a"),
        TopicProposal(topic="B", description="b"),
    ])
    assert len(await repo.get_topic_proposals(user.id)) == 2
    await repo.save_topic_proposals(user.id, [
        TopicProposal(topic="C", description="c"),
    ])
    all_notes = await repo.get_topic_proposals(user.id)
    assert len(all_notes) == 1
    assert all_notes[0].topic == "C"
