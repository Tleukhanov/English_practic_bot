import pytest

from bot.rate_limit import LLMThrottle


class FakeUser:
    def __init__(self, user_id):
        self.id = user_id


class FakeMessage:
    def __init__(self, text: str = "", voice=None, user_id: int = 100):
        self.text = text
        self.voice = voice
        self.from_user = FakeUser(user_id)
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append(text)


async def _ok_handler(event, data):
    return "OK"


@pytest.fixture
def throttle():
    return LLMThrottle(window_sec=60.0, limit=3, min_interval=0.0)


async def test_min_interval_respected():
    t = LLMThrottle(window_sec=60.0, limit=10, min_interval=10.0)
    msg = FakeMessage(text="hi", user_id=9)
    assert await t(_ok_handler, msg, {}) == "OK"
    assert await t(_ok_handler, msg, {}) is None


async def test_regular_commands_not_throttled(throttle):
    msg = FakeMessage(text="/start", user_id=1)
    for _ in range(20):
        res = await throttle(_ok_handler, msg, {})
        assert res == "OK"


async def test_llm_actions_limited(throttle):
    msg = FakeMessage(text="Hello world!", user_id=2)
    for _ in range(3):
        res = await throttle(_ok_handler, msg, {})
        assert res == "OK"
    res = await throttle(_ok_handler, msg, {})
    assert res is None
    assert msg.answers


async def test_voice_is_limited(throttle):
    msg = FakeMessage(voice=object(), user_id=3)
    assert await throttle(_ok_handler, msg, {}) == "OK"
    assert await throttle(_ok_handler, msg, {}) == "OK"
    assert await throttle(_ok_handler, msg, {}) == "OK"
    assert await throttle(_ok_handler, msg, {}) is None


async def test_single_char_text_practice_limited(throttle):
    msg = FakeMessage(text="a", user_id=4)
    for _ in range(3):
        assert await throttle(_ok_handler, msg, {}) == "OK"
    assert await throttle(_ok_handler, msg, {}) is None