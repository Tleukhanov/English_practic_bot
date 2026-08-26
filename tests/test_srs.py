"""Tests for Phase 13 — SRS Service."""

import pytest
from datetime import datetime, timezone, timedelta

from core.srs import SRSService
from storage.repo import SRSWord


class FakeRepo:
    def __init__(self):
        self.words: dict[int, list[SRSWord]] = {}
        self._id_counter = 1

    async def add_srs_word(self, word: SRSWord) -> int:
        word.id = self._id_counter
        self._id_counter += 1
        self.words.setdefault(word.user_id, []).append(word)
        return word.id

    async def get_srs_word(self, user_id: int, word: str) -> SRSWord | None:
        for w in self.words.get(user_id, []):
            if w.word == word:
                return w
        return None

    async def get_srs_word_by_id(self, word_id: int) -> SRSWord | None:
        for words in self.words.values():
            for w in words:
                if w.id == word_id:
                    return w
        return None

    async def get_srs_words(self, user_id: int, limit: int = 100) -> list[SRSWord]:
        return sorted(self.words.get(user_id, []), key=lambda w: w.next_review)[:limit]

    async def update_srs_word(self, word: SRSWord) -> None:
        pass


@pytest.mark.asyncio
async def test_add_words():
    repo = FakeRepo()
    svc = SRSService(repo)
    count = await svc.add_words(1, [
        {"word": "hello", "translation": "привет", "example": "Hello!"},
        {"word": "world", "translation": "мир", "example": "World!"},
    ])
    assert count == 2
    assert len(repo.words[1]) == 2


@pytest.mark.asyncio
async def test_add_words_skips_duplicates():
    repo = FakeRepo()
    svc = SRSService(repo)
    await svc.add_words(1, [{"word": "hello", "translation": "привет"}])
    count = await svc.add_words(1, [{"word": "hello", "translation": "привет"}])
    assert count == 0
    assert len(repo.words[1]) == 1


@pytest.mark.asyncio
async def test_add_words_skips_empty():
    repo = FakeRepo()
    svc = SRSService(repo)
    count = await svc.add_words(1, [{"word": "", "translation": "привет"}])
    assert count == 0


@pytest.mark.asyncio
async def test_get_due_words_empty():
    repo = FakeRepo()
    svc = SRSService(repo)
    words = await svc.get_due_words(1)
    assert words == []


@pytest.mark.asyncio
async def test_get_due_words():
    repo = FakeRepo()
    svc = SRSService(repo)
    now = datetime.now(timezone.utc).isoformat()
    word = SRSWord(id=1, user_id=1, word="hello", next_review=now)
    await repo.add_srs_word(word)
    words = await svc.get_due_words(1)
    assert len(words) == 1


@pytest.mark.asyncio
async def test_get_due_words_skips_future():
    repo = FakeRepo()
    svc = SRSService(repo)
    future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    word = SRSWord(id=1, user_id=1, word="hello", next_review=future)
    await repo.add_srs_word(word)
    words = await svc.get_due_words(1)
    assert len(words) == 0


@pytest.mark.asyncio
async def test_review_correct():
    repo = FakeRepo()
    svc = SRSService(repo)
    now = datetime.now(timezone.utc).isoformat()
    word = SRSWord(id=1, user_id=1, word="hello", next_review=now, interval_days=1)
    await repo.add_srs_word(word)
    updated = await svc.review(1, quality=5)
    assert updated is not None
    assert updated.correct_count == 1
    assert updated.interval_days >= 1


@pytest.mark.asyncio
async def test_review_incorrect():
    repo = FakeRepo()
    svc = SRSService(repo)
    now = datetime.now(timezone.utc).isoformat()
    word = SRSWord(id=1, user_id=1, word="hello", next_review=now, interval_days=5)
    await repo.add_srs_word(word)
    updated = await svc.review(1, quality=1)
    assert updated is not None
    assert updated.correct_count == 0
    assert updated.interval_days == 1


@pytest.mark.asyncio
async def test_review_nonexistent():
    repo = FakeRepo()
    svc = SRSService(repo)
    result = await svc.review(999, quality=5)
    assert result is None


@pytest.mark.asyncio
async def test_get_stats():
    repo = FakeRepo()
    svc = SRSService(repo)
    now = datetime.now(timezone.utc).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    await repo.add_srs_word(SRSWord(id=1, user_id=1, word="hello", next_review=now))
    await repo.add_srs_word(SRSWord(id=2, user_id=1, word="world", next_review=future))
    await repo.add_srs_word(SRSWord(id=3, user_id=1, word="test", next_review=now, correct_count=3))
    stats = await svc.get_stats(1)
    assert stats["total"] == 3
    assert stats["due"] == 2
    assert stats["learned"] == 1
