"""Tests for Phase 13 — Weak Areas targeted practice."""

import pytest
from datetime import datetime, timezone, timedelta

from core.weak_areas import WeakAreaService
from storage.repo import WeakArea


class FakeRepo:
    """Fake repo for unit tests."""

    def __init__(self):
        self.weak_areas: dict[int, list[WeakArea]] = {}
        self._id_counter = 1

    async def get_weak_areas(self, user_id: int) -> list[WeakArea]:
        return sorted(
            self.weak_areas.get(user_id, []),
            key=lambda w: w.incorrect_count * 2 - w.correct_count,
            reverse=True,
        )

    async def upsert_weak_area(
        self, user_id: int, area: str,
        incorrect_increment: int = 0, correct_increment: int = 0,
        last_seen: str = "",
    ):
        if user_id not in self.weak_areas:
            self.weak_areas[user_id] = []
        for wa in self.weak_areas[user_id]:
            if wa.area == area:
                wa.incorrect_count += incorrect_increment
                wa.correct_count += correct_increment
                if last_seen:
                    wa.last_seen = last_seen
                return
        self.weak_areas[user_id].append(WeakArea(
            id=self._id_counter, user_id=user_id, area=area,
            incorrect_count=incorrect_increment, correct_count=correct_increment,
            last_seen=last_seen, created_at=last_seen,
        ))
        self._id_counter += 1

    async def delete_weak_area(self, user_id: int, area: str):
        if user_id in self.weak_areas:
            self.weak_areas[user_id] = [w for w in self.weak_areas[user_id] if w.area != area]


class FakeIssue:
    def __init__(self, category: str):
        self.category = category


@pytest.mark.asyncio
async def test_upsert_creates_new_area():
    repo = FakeRepo()
    svc = WeakAreaService(repo)
    await svc.update_from_practice(1, [FakeIssue("grammar")], is_correct=False)
    areas = await repo.get_weak_areas(1)
    assert len(areas) == 1
    assert areas[0].area == "grammar"
    assert areas[0].incorrect_count == 1


@pytest.mark.asyncio
async def test_upsert_increments_existing():
    repo = FakeRepo()
    svc = WeakAreaService(repo)
    await svc.update_from_practice(1, [FakeIssue("grammar")], is_correct=False)
    await svc.update_from_practice(1, [FakeIssue("grammar")], is_correct=False)
    areas = await repo.get_weak_areas(1)
    assert len(areas) == 1
    assert areas[0].incorrect_count == 2


@pytest.mark.asyncio
async def test_get_top_for_prompt_empty():
    repo = FakeRepo()
    svc = WeakAreaService(repo)
    prompt = await svc.get_top_for_prompt(1)
    assert prompt == ""


@pytest.mark.asyncio
async def test_get_top_for_prompt_with_areas():
    repo = FakeRepo()
    svc = WeakAreaService(repo)
    now = datetime.now(timezone.utc).isoformat()
    await repo.upsert_weak_area(1, "grammar", incorrect_increment=3, last_seen=now)
    await repo.upsert_weak_area(1, "vocabulary", incorrect_increment=1, last_seen=now)
    prompt = await svc.get_top_for_prompt(1)
    assert "grammar" in prompt
    assert "vocabulary" in prompt
    assert "weak areas" in prompt.lower() or "ask about" in prompt.lower()


@pytest.mark.asyncio
async def test_decay_removes_old_areas():
    repo = FakeRepo()
    svc = WeakAreaService(repo)
    old_time = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
    await repo.upsert_weak_area(1, "grammar", correct_increment=5, last_seen=old_time)
    await svc.decay(1)
    areas = await repo.get_weak_areas(1)
    assert len(areas) == 0


@pytest.mark.asyncio
async def test_decay_keeps_recent_areas():
    repo = FakeRepo()
    svc = WeakAreaService(repo)
    now = datetime.now(timezone.utc).isoformat()
    await repo.upsert_weak_area(1, "grammar", correct_increment=5, last_seen=now)
    await svc.decay(1)
    areas = await repo.get_weak_areas(1)
    assert len(areas) == 1


@pytest.mark.asyncio
async def test_decay_keeps_areas_with_few_correct():
    repo = FakeRepo()
    svc = WeakAreaService(repo)
    old_time = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
    await repo.upsert_weak_area(1, "grammar", correct_increment=2, last_seen=old_time)
    await svc.decay(1)
    areas = await repo.get_weak_areas(1)
    assert len(areas) == 1


@pytest.mark.asyncio
async def test_normalize_area():
    svc = WeakAreaService(FakeRepo())
    assert svc._normalize_area(FakeIssue("grammar")) == "grammar"
    assert svc._normalize_area(FakeIssue("vocabulary")) == "vocabulary"
    assert svc._normalize_area(FakeIssue("word_order")) == "word order"
    assert svc._normalize_area(FakeIssue("")) == ""


def test_priority_score_high_errors():
    now = datetime.now(timezone.utc).isoformat()
    wa = WeakArea(incorrect_count=5, correct_count=0, last_seen=now)
    assert wa.priority_score > 2.0


def test_priority_score_low_errors():
    now = datetime.now(timezone.utc).isoformat()
    wa = WeakArea(incorrect_count=1, correct_count=5, last_seen=now)
    high_wa = WeakArea(incorrect_count=5, correct_count=0, last_seen=now)
    assert wa.priority_score < high_wa.priority_score


def test_priority_score_old_area():
    now = datetime.now(timezone.utc).isoformat()
    old = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
    recent = WeakArea(incorrect_count=3, correct_count=0, last_seen=now)
    aged = WeakArea(incorrect_count=3, correct_count=0, last_seen=old)
    assert recent.priority_score > aged.priority_score


@pytest.mark.asyncio
async def test_practice_correct_increments_correct():
    repo = FakeRepo()
    svc = WeakAreaService(repo)
    now = datetime.now(timezone.utc).isoformat()
    await repo.upsert_weak_area(1, "grammar", incorrect_increment=3, last_seen=now)
    await svc.update_from_practice(1, [], is_correct=True, corrected_text="I went to school")
    areas = await repo.get_weak_areas(1)
    assert any(a.correct_count > 0 for a in areas)
