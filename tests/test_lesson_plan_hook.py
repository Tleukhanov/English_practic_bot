"""Bot layer: план уроков после каждых 12 завершённых уроков.

Проверяем хук _maybe_generate_plan и подстановку плановой темы в _start_lesson.
Используем фейки репозитория/LLM и вызываем функции напрямую.
"""

from types import SimpleNamespace

import pytest

from bot.formatters import format_lesson_plan
from bot.lessons import _maybe_generate_plan, _start_lesson
from bot.quota import QuotaExceeded
from core.lesson_plan import LessonPlan, LessonPlanService, PlannedLesson
from core.lessons import LessonContent
from storage.repo import LessonPlanRow, UserProfile


def make_plan(count: int = 12) -> LessonPlan:
    return LessonPlan(
        goal="Уверенно говорить о путешествиях",
        lessons=[
            PlannedLesson(number=i, topic=f"Plan Topic {i}", focus=f"focus {i}", reason=f"reason {i}")
            for i in range(1, count + 1)
        ],
    )


def make_row(plan: LessonPlan, *, based_on: int = 0, horizon: int = 12) -> LessonPlanRow:
    return LessonPlanRow(
        user_id=1,
        plan_json=plan.to_json(),
        horizon=horizon,
        based_on_lessons=based_on,
        generated_at="2026-09-22T00:00:00+00:00",
    )


class FakeUser:
    id = 1
    level = "A1"
    username = "alice"
    first_name = "Alice"


class FakeQuota:
    def __init__(self, *, exhausted: bool = False):
        self.exhausted = exhausted
        self.checked: list[int] = []
        self.consumed: list[tuple[int, int]] = []

    async def check(self, user_id: int) -> None:
        self.checked.append(user_id)
        if self.exhausted:
            raise QuotaExceeded("квота исчерпана")

    async def consume(self, user_id: int, *, cost: int = 1) -> None:
        self.consumed.append((user_id, cost))


class FakeMessage:
    def __init__(self):
        self.answers: list[str] = []
        self.edits: list[str] = []

    async def answer(self, text, reply_markup=None):
        self.answers.append(text)
        return self

    async def edit_text(self, text, reply_markup=None):
        self.edits.append(text)


class FakeRepo:
    def __init__(self, *, completed: int = 0, plan_row: LessonPlanRow | None = None, profile=None):
        self.completed = completed
        self.plan_row = plan_row
        self.profile = profile or UserProfile(user_id=1)
        self.saved_plan: LessonPlanRow | None = None
        self.saved_proposals = []

    async def get_or_create_user(self, tg_id, username=None, first_name=None):
        return FakeUser()

    async def get_active_lesson(self, user_id):
        return None

    async def get_active_diagnostic(self, user_id):
        return None

    async def count_finished_lessons(self, user_id):
        return self.completed

    async def get_lesson_plan(self, user_id):
        return self.plan_row

    async def save_lesson_plan(self, plan: LessonPlanRow) -> None:
        self.saved_plan = plan

    async def get_lesson_notes(self, user_id, limit=10):
        return []

    async def get_profile(self, user_id):
        return self.profile

    async def save_topic_proposals(self, user_id, proposals):
        self.saved_proposals = proposals

    async def start_lesson(self, user_id, topic, content_json):
        return SimpleNamespace(id=1)


class RecordingPlanService:
    def __init__(self, plan: LessonPlan | None = None, *, error: Exception | None = None):
        self.plan = plan
        self.error = error
        self.calls: list[dict] = []

    async def generate(self, *, level, profile, recent_topics, completed_lessons) -> LessonPlan:
        self.calls.append(
            dict(level=level, profile=profile, recent_topics=recent_topics, completed_lessons=completed_lessons)
        )
        if self.error is not None:
            raise self.error
        return self.plan


class RecordingLessonService:
    def __init__(self):
        self.proposals_calls = 0
        self.generate_calls: list[dict] = []

    async def generate_proposals(self, **kwargs):
        self.proposals_calls += 1
        return [{"topic": "Free Topic", "description": "desc"}]

    async def generate(self, topic: str, **kwargs):
        self.generate_calls.append({"topic": topic, **kwargs})
        return LessonContent(topic=topic, intro="Hello!")


async def test_hook_below_threshold_no_generation():
    repo = FakeRepo(completed=11)
    svc = RecordingPlanService(make_plan())
    msg = FakeMessage()
    await _maybe_generate_plan(msg, FakeUser(), repo, svc, FakeQuota())
    assert svc.calls == []
    assert repo.saved_plan is None
    assert msg.answers == []


async def test_hook_generates_at_12():
    plan = make_plan()
    repo = FakeRepo(completed=12)
    svc = RecordingPlanService(plan)
    quota = FakeQuota()
    msg = FakeMessage()
    await _maybe_generate_plan(msg, FakeUser(), repo, svc, quota)
    assert len(svc.calls) == 1
    assert svc.calls[0]["completed_lessons"] == 12
    assert repo.saved_plan is not None
    assert repo.saved_plan.based_on_lessons == 12
    assert repo.saved_plan.horizon == 12
    assert msg.answers == [format_lesson_plan(plan, completed=12)]
    assert quota.consumed == [(1, 1)]


async def test_hook_skips_when_plan_still_relevant():
    repo = FakeRepo(completed=13, plan_row=make_row(make_plan(), based_on=12))
    svc = RecordingPlanService(make_plan())
    msg = FakeMessage()
    await _maybe_generate_plan(msg, FakeUser(), repo, svc, FakeQuota())
    assert svc.calls == []
    assert repo.saved_plan is None
    assert msg.answers == []


async def test_hook_regenerates_at_24():
    repo = FakeRepo(completed=24, plan_row=make_row(make_plan(), based_on=12))
    svc = RecordingPlanService(make_plan())
    msg = FakeMessage()
    await _maybe_generate_plan(msg, FakeUser(), repo, svc, FakeQuota())
    assert len(svc.calls) == 1
    assert repo.saved_plan is not None
    assert repo.saved_plan.based_on_lessons == 24
    assert len(msg.answers) == 1


async def test_hook_quota_exceeded_silently_skips():
    repo = FakeRepo(completed=12)
    svc = RecordingPlanService(make_plan())
    msg = FakeMessage()
    await _maybe_generate_plan(msg, FakeUser(), repo, svc, FakeQuota(exhausted=True))
    assert svc.calls == []
    assert repo.saved_plan is None
    assert msg.answers == []


async def test_hook_generate_failure_does_not_raise():
    repo = FakeRepo(completed=12)
    svc = RecordingPlanService(error=RuntimeError("llm down"))
    msg = FakeMessage()
    await _maybe_generate_plan(msg, FakeUser(), repo, svc, FakeQuota())
    assert repo.saved_plan is None
    assert msg.answers == []


async def test_start_lesson_uses_plan_topic_and_skips_proposals():
    plan = make_plan()
    repo = FakeRepo(completed=12, plan_row=make_row(plan, based_on=12))
    lessons = RecordingLessonService()
    target = FakeMessage()
    user_from = SimpleNamespace(id=1, username="alice", first_name="Alice")
    await _start_lesson(target, repo, lessons, None, user_from, quota=None)
    assert lessons.proposals_calls == 0
    assert len(lessons.generate_calls) == 1
    call = lessons.generate_calls[0]
    assert call["topic"] == plan.lessons[0].topic
    assert call["plan_hint"] is not None
    assert "Plan lesson 1/12" in call["plan_hint"]
    assert "Продолжаю по плану" in target.answers[0]


async def test_start_lesson_without_plan_uses_proposals():
    repo = FakeRepo(completed=5, plan_row=None)
    lessons = RecordingLessonService()
    target = FakeMessage()
    user_from = SimpleNamespace(id=1, username="alice", first_name="Alice")
    await _start_lesson(target, repo, lessons, None, user_from, quota=None)
    assert lessons.proposals_calls == 1
    assert lessons.generate_calls == []