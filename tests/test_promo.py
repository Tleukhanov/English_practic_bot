import asyncio

import pytest

from bot.config import Settings
from bot.handlers.promo import cmd_promo

from storage.sqlite import SQLiteRepository


class FakeUser:
    id = 3001
    username = "tester"
    first_name = "Tester"


class FakeMessage:
    def __init__(self, text: str, tg_id: int = 3001):
        self.text = text
        self.from_user = FakeUser()
        self.from_user.id = tg_id
        self.answers = []

    async def answer(self, text, reply_markup=None):
        self.answers.append(text)


@pytest.fixture
async def repo(tmp_path):
    db = SQLiteRepository(str(tmp_path / "promo.db"))
    await db.connect()
    yield db
    await db.close()


@pytest.fixture
def settings():
    return Settings(promo_unlimited_code="TEST-CODE", llm_daily_limit=30)


async def run(text: str, repo, s: Settings) -> FakeMessage:
    msg = FakeMessage(text)
    await cmd_promo(msg, repo, s)
    return msg


async def test_promo_activates_unlimited(repo, settings):
    msg = await run("/promo test-code", repo, settings)
    assert msg.answers
    user = await repo.get_or_create_user(3001)
    assert await repo.get_unlimited_status(user.id) is True


async def test_promo_wrong_code(repo, settings):
    msg = await run("/promo WRONG", repo, settings)
    assert msg.answers
    user = await repo.get_or_create_user(3001)
    assert await repo.get_unlimited_status(user.id) is False


async def test_promo_without_code(repo, settings):
    msg = await run("/promo", repo, settings)
    assert msg.answers
    user = await repo.get_or_create_user(3001)
    assert await repo.get_unlimited_status(user.id) is False


async def test_promo_disabled_when_code_empty(repo):
    s = Settings(promo_unlimited_code="", llm_daily_limit=30)
    msg = FakeMessage("/promo anything")
    await cmd_promo(msg, repo, s)
    assert msg.answers
    user = await repo.get_or_create_user(3001)
    assert await repo.get_unlimited_status(user.id) is False