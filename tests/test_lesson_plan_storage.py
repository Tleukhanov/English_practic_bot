import pytest

from storage.sqlite import SQLiteRepository
from storage.repo import LessonPlanRow


@pytest.fixture
async def repo(tmp_path):
    db = SQLiteRepository(str(tmp_path / "test.db"))
    await db.connect()
    yield db
    await db.close()


async def test_lesson_plan_save_get_roundtrip(repo):
    user = await repo.get_or_create_user(1001, username="alice")
    assert await repo.get_lesson_plan(user.id) is None

    plan = LessonPlanRow(
        user_id=user.id,
        plan_json='[{"day": 1, "topic": "Present Simple"}]',
        horizon=7,
        based_on_lessons=3,
        generated_at="2026-09-22T00:00:00+00:00",
    )
    await repo.save_lesson_plan(plan)

    saved = await repo.get_lesson_plan(user.id)
    assert saved is not None
    assert saved.user_id == user.id
    assert saved.plan_json == plan.plan_json
    assert saved.horizon == 7
    assert saved.based_on_lessons == 3
    assert saved.generated_at == "2026-09-22T00:00:00+00:00"


async def test_lesson_plan_upsert_overwrites(repo):
    user = await repo.get_or_create_user(1002, username="bob")
    await repo.save_lesson_plan(LessonPlanRow(user_id=user.id, plan_json='["old"]', horizon=7))
    await repo.save_lesson_plan(
        LessonPlanRow(
            user_id=user.id,
            plan_json='["new"]',
            horizon=14,
            based_on_lessons=5,
            generated_at="2026-09-22T12:00:00+00:00",
        )
    )

    cursor = await repo._conn.execute(
        "SELECT COUNT(*) AS cnt FROM user_lesson_plans WHERE user_id = ?", (user.id,)
    )
    row = await cursor.fetchone()
    assert row["cnt"] == 1

    saved = await repo.get_lesson_plan(user.id)
    assert saved.plan_json == '["new"]'
    assert saved.horizon == 14
    assert saved.based_on_lessons == 5


async def test_lesson_plan_get_missing_user_returns_none(repo):
    assert await repo.get_lesson_plan(999999) is None


async def test_count_finished_lessons(repo):
    user = await repo.get_or_create_user(1003, username="carol")
    assert await repo.count_finished_lessons(user.id) == 0

    await repo.start_lesson(user.id, "Travelling", "{}")
    await repo.finish_active_lessons(user.id)
    assert await repo.count_finished_lessons(user.id) == 1


async def test_count_finished_lessons_ignores_aborted(repo):
    user = await repo.get_or_create_user(1004, username="dave")

    # завершённый урок
    await repo.start_lesson(user.id, "Chess", "{}")
    await repo.finish_active_lessons(user.id)
    # первый активный урок прерван при перезапуске, второй aborted-сессия
    await repo.start_lesson(user.id, "Music", "{}")
    await repo.start_lesson(user.id, "Cooking", "{}")
    await repo.abort_active_lessons(user.id)

    assert await repo.count_finished_lessons(user.id) == 1

    cursor = await repo._conn.execute(
        "SELECT status, COUNT(*) AS cnt FROM lesson_sessions WHERE user_id = ? GROUP BY status",
        (user.id,),
    )
    statuses = {row["status"] for row in await cursor.fetchall()}
    assert statuses == {"finished", "aborted"}
