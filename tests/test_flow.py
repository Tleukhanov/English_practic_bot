from types import SimpleNamespace

from core.models import PracticeResult
from core.lessons import LessonContent

from bot.flow import practice_markup
from bot.keyboards import lesson_keyboard
from bot.lessons import _start_lesson, cb_lesson_end, cb_lesson_next
from bot.quota import QuotaExceeded


def test_practice_markup_reveal_when_incorrect_and_no_base():
    result = PracticeResult(is_correct=False, corrected_text="")
    markup = practice_markup(result)
    assert markup is not None
    assert markup.inline_keyboard[0][0].text == "🔍 Показать ошибку"


def test_practice_markup_none_when_correct():
    result = PracticeResult(is_correct=True, corrected_text="")
    assert practice_markup(result) is None


def test_practice_markup_keeps_lesson_keyboard():
    result = PracticeResult(is_correct=False, corrected_text="")
    base = lesson_keyboard()
    markup = practice_markup(result, base)
    assert markup is not None
    assert len(markup.inline_keyboard) == len(base.inline_keyboard) + 1
    assert markup.inline_keyboard[0][0].callback_data == "practice:reveal"


def test_practice_markup_binds_to_message_id():
    result = PracticeResult(is_correct=False, corrected_text="")
    markup = practice_markup(result, lesson_keyboard(), message_id=42)
    assert markup.inline_keyboard[0][0].callback_data == "practice:reveal:42"


class FakeState:
    def __init__(self, state=None):
        self._state = state
        self.clear_calls = 0
        self.set_calls = []

    async def get_state(self):
        return self._state

    async def set_state(self, s=None):
        self._state = s.state if s is not None and hasattr(s, "state") else s
        self.set_calls.append(self._state)

    async def clear(self):
        self._state = None
        self.clear_calls += 1


class BoomRepo:
    def __getattr__(self, name):
        raise AssertionError(f"BoomRepo.{name} не должен вызываться")


class FakeCallback:
    def __init__(self, data, message):
        self.data = data
        self.message = message
        self.from_user = SimpleNamespace(id=1, username="u", first_name="F")
        self.answered = []

    async def answer(self, *args, **kwargs):
        self.answered.append((args, kwargs))


class FakeMessage:
    def __init__(self):
        self.edits = []
        self.answers = []

    async def edit_text(self, text, reply_markup=None):
        self.edits.append((text, reply_markup))

    async def answer(self, text, reply_markup=None):
        self.answers.append((text, reply_markup))


class FakeLessonRepo:
    def __init__(self, session, user=None):
        self._session = session
        self.user = user or SimpleNamespace(id=1, level="A1", username="u", first_name="F")
        self.finish_called = 0
        self.start_called = 0

    async def get_or_create_user(self, uid, **kwargs):
        return self.user

    async def get_active_lesson(self, uid):
        return self._session

    async def get_active_diagnostic(self, uid):
        return None

    async def get_profile(self, uid):
        return None

    async def get_lesson_notes(self, uid, limit=None):
        return []

    async def get_lesson_plan(self, uid):
        return None

    async def finish_active_lessons(self, uid):
        self.finish_called += 1
        self._session = None

    async def start_lesson(self, uid, topic, content_json):
        self.start_called += 1
        return SimpleNamespace(id=1, topic=topic)

    def __getattr__(self, name):
        raise AssertionError(f"FakeLessonRepo.{name} не должен вызываться")


class GenerateOnceService:
    def __init__(self, content):
        self._content = content
        self.generate_calls = 0

    async def generate(self, *args, **kwargs):
        self.generate_calls += 1
        return self._content


class RacingQuota:
    def __init__(self, raise_on_consume=True):
        self.raise_on_consume = raise_on_consume
        self.check_calls = 0
        self.consume_calls = 0

    async def check(self, user_id):
        self.check_calls += 1

    async def consume(self, user_id, *, cost=1):
        self.consume_calls += 1
        if self.raise_on_consume:
            raise QuotaExceeded("гонка квоты")


class FakeTarget:
    def __init__(self):
        self.sent = []
        self.status_edits = []

    async def answer(self, text, reply_markup=None):
        self.sent.append((text, reply_markup))
        return FakeStatus(self)

    async def edit_text(self, text, reply_markup=None):
        self.status_edits.append((text, reply_markup))


class FakeStatus:
    def __init__(self, owner):
        self._owner = owner

    async def edit_text(self, text, reply_markup=None):
        self._owner.status_edits.append((text, reply_markup))

    async def answer(self, text, reply_markup=None):
        pass


async def test_corrupt_lesson_end_closes_with_menu():
    session = SimpleNamespace(id=1, content_json="not json", step=5, task_index=0)
    repo = FakeLessonRepo(session)
    state = FakeState(None)
    message = FakeMessage()
    cb = FakeCallback("lesson:end", message)

    await cb_lesson_end(cb, repo, note_service=None, state=state)

    assert repo.finish_called == 1
    assert message.edits and "повреждён" in message.edits[-1][0]
    assert state.clear_calls == 1  # свой LessonNav очищен в finally
    assert state._state is None


async def test_corrupt_lesson_next_closes_with_menu():
    session = SimpleNamespace(id=1, content_json="{" , step=3, task_index=0)
    repo = FakeLessonRepo(session)
    state = FakeState(None)
    message = FakeMessage()
    cb = FakeCallback("lesson:next", message)

    await cb_lesson_next(cb, repo, note_service=None, state=state)

    assert repo.finish_called == 1
    assert message.edits and "повреждён" in message.edits[-1][0]
    assert state.clear_calls == 1


async def test_lesson_next_preserves_review_state():
    repo = BoomRepo()
    state = FakeState("bot.handlers.review:ReviewState:answering")
    message = FakeMessage()
    cb = FakeCallback("lesson:next", message)

    await cb_lesson_next(cb, repo, note_service=None, state=state)

    assert state._state == "bot.handlers.review:ReviewState:answering"
    assert state.clear_calls == 0
    assert state.set_calls == []
    assert cb.answered  # подсказка пользователю


async def test_lesson_end_preserves_review_state():
    repo = BoomRepo()
    state = FakeState("ReviewState:answering")
    message = FakeMessage()
    cb = FakeCallback("lesson:end", message)

    await cb_lesson_end(cb, repo, note_service=None, state=state)

    assert state._state == "ReviewState:answering"
    assert state.clear_calls == 0
    assert state.set_calls == []


async def test_start_lesson_survives_quota_consume_race():
    content = LessonContent(topic="Chess", intro="Play the game!")
    repo = FakeLessonRepo(session=None)
    service = GenerateOnceService(content)
    quota = RacingQuota()
    target = FakeTarget()
    user_from = SimpleNamespace(id=1, username="u", first_name="F")

    await _start_lesson(target, repo, service, "Chess", user_from, quota)

    assert repo.start_called == 1  # урок начат, несмотря на гонку квоты
    assert quota.consume_calls == 1
    assert quota.check_calls == 1
    assert target.status_edits and "Chess" in target.status_edits[-1][0]
