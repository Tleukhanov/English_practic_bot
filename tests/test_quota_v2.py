"""Квота v2: двухшаговое check/consume, cost=3 для уроков, фон под квотой."""

import pytest

from bot.quota import QuotaExceeded, QuotaGuard
from bot.lessons import _create_lesson_note
from bot.flow import _update_profile_background

from storage.repo import LessonNote, UserProfile
from storage.sqlite import SQLiteRepository


@pytest.fixture
async def repo(tmp_path):
    db = SQLiteRepository(str(tmp_path / "quota_v2.db"))
    await db.connect()
    yield db
    await db.close()


class FakeNoteService:
    def __init__(self):
        self.calls = 0

    async def generate(self, user_id, lesson_id, content, answers):
        self.calls += 1
        return LessonNote(user_id=user_id, lesson_id=lesson_id, topic=content.topic)


class FakeProfileService:
    def __init__(self):
        self.calls = 0

    async def update(self, user_id, previous, dialogue):
        self.calls += 1
        return UserProfile(user_id=user_id)


def _content(topic="x"):
    return type("C", (), {"topic": topic})()


async def test_check_raises_when_no_budget(repo):
    guard = QuotaGuard(repo, daily_limit=1)
    user = await repo.get_or_create_user(2001)
    await guard.consume(user.id)  # daily full, no extra
    with pytest.raises(QuotaExceeded):
        await guard.check(user.id)
    assert await repo.get_llm_usage(user.id, guard._today()) == 1


async def test_consume_does_not_raise_after_limit(repo):
    guard = QuotaGuard(repo, daily_limit=1)
    user = await repo.get_or_create_user(2002)
    await guard.consume(user.id)
    await guard.consume(user.id)  # no raise, just bills nothing more daily
    # extra_actions untouched
    assert await repo.get_extra_actions(user.id) == 0


async def test_lesson_cost_3_billing_extra_first_then_daily(repo):
    guard = QuotaGuard(repo, daily_limit=2)
    user = await repo.get_or_create_user(2003)
    await repo.add_extra_actions(user.id, 5)
    await guard.consume(user.id, cost=3)
    assert await repo.get_extra_actions(user.id) == 2
    assert await repo.get_llm_usage(user.id, guard._today()) == 0
    await guard.consume(user.id, cost=3)
    assert await repo.get_extra_actions(user.id) == 0
    assert await repo.get_llm_usage(user.id, guard._today()) == 1
    await guard.consume(user.id, cost=3)
    assert await repo.get_llm_usage(user.id, guard._today()) == 4
    with pytest.raises(QuotaExceeded):
        await guard.check(user.id)


async def test_lesson_cost_3_fits_in_daily(repo):
    guard = QuotaGuard(repo, daily_limit=3)
    user = await repo.get_or_create_user(2004)
    await guard.check(user.id)
    await guard.consume(user.id, cost=3)
    assert await repo.get_llm_usage(user.id, guard._today()) == 3
    with pytest.raises(QuotaExceeded):
        await guard.check(user.id)


async def test_background_lesson_note_skipped_on_quota_exceeded(repo):
    guard = QuotaGuard(repo, daily_limit=1)
    user = await repo.get_or_create_user(2005)
    await guard.consume(user.id)
    note_svc = FakeNoteService()
    note = await _create_lesson_note(user.id, 1, _content(), repo, note_svc, quota=guard)
    assert note is None
    assert note_svc.calls == 0


async def test_background_lesson_note_billed_on_success(repo):
    guard = QuotaGuard(repo, daily_limit=3)
    user = await repo.get_or_create_user(2006)
    note_svc = FakeNoteService()
    src = await repo.start_lesson(user.id, "x", "{}")
    note = await _create_lesson_note(user.id, src.id, _content(), repo, note_svc, quota=guard)
    assert note is not None
    assert note_svc.calls == 1
    assert await repo.get_llm_usage(user.id, guard._today()) == 1


async def test_background_profile_skipped_on_quota_exceeded(repo):
    guard = QuotaGuard(repo, daily_limit=1)
    user = await repo.get_or_create_user(2007)
    await guard.consume(user.id)
    prof_svc = FakeProfileService()
    await _update_profile_background(user.id, [], "hi", repo, prof_svc, quota=guard)
    assert prof_svc.calls == 0
    assert await repo.get_profile(user.id) is None


async def test_background_profile_billed_on_success(repo):
    guard = QuotaGuard(repo, daily_limit=3)
    user = await repo.get_or_create_user(2008)
    prof_svc = FakeProfileService()
    await _update_profile_background(user.id, [], "hi", repo, prof_svc, quota=guard)
    assert prof_svc.calls == 1
    assert await repo.get_llm_usage(user.id, guard._today()) == 1
