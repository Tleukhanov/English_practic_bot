"""Тесты Mini App: валидация initData, статика и API уроков.

Без сети и Telegram: aiohttp TestClient + фейковые сервисы (repo/quota/LLM/TTS).
"""

import base64
import json
import time
from types import SimpleNamespace

import pytest
from aiohttp.test_utils import TestClient, TestServer

from bot.config import Settings
from bot.mini_api import _phrase_rating, _quiz_results
from bot.webapp import (
    compute_hash,
    create_webapp,
    parse_init_data,
    sign_init_data,
    validate_init_data,
)
from core.deck import Deck, QuizItem, VocabCard
from bot.quota import QuotaExceeded

BOT_TOKEN = "123456:TEST-token"
TG_USER_ID = 4242

DECK_JSON = json.dumps(
    {
        "title": "Coffee Around the World",
        "subtitle_ru": "Путешествие по кофейным традициям",
        "preset": "mixed",
        "emoji": "☕",
        "slides": [{"headline": "Why coffee?", "body": "A morning ritual.", "emoji": "🌅"}],
        "vocabulary": [
            {"word": "brew", "translation": "заваривать", "example": "I brew coffee."},
            {"word": "roast", "translation": "обжаривать", "example": "Beans are roasted."},
        ],
        "quiz": [
            {
                "question": "What does brew mean?",
                "options": ["заваривать", "пить", "мыть"],
                "answer_index": 0,
                "explanation_ru": "to brew — заваривать",
            }
        ],
        "dialogue": None,
    },
    ensure_ascii=False,
)


def make_init_data(user_id: int = TG_USER_ID, token: str = BOT_TOKEN, **params: str) -> str:
    """Корректный initData той же HMAC-логикой, что и валидация."""
    payload = {
        "auth_date": str(int(time.time())),
        "query_id": "AAH_test",
        "user": json.dumps({"id": user_id, "first_name": "Test", "language_code": "ru"}),
    }
    payload.update(params)
    return sign_init_data(token, payload)


# ---------- фейковые сервисы ----------


class FakeRepo:
    def __init__(self):
        self.users = {}
        self.mini_sessions = {}
        self.finished = []
        self.notes = []
        self.srs_words = []
        self.plan = None
        self.audio_answers = []

    async def get_or_create_user(self, tg_id, username=None, first_name=None):
        user = self.users.get(tg_id)
        if user is None:
            user = SimpleNamespace(id=tg_id, tg_id=tg_id, level="B1", username=username)
            self.users[tg_id] = user
        return user

    async def get_profile(self, user_id):
        return SimpleNamespace(
            goal="свободная речь",
            interests="coffee, travel",
            weak_areas="",
            preferred_format="",
            notes="",
            character="chill",
        )

    async def get_lesson_notes(self, user_id, limit=10):
        return list(self.notes)

    async def get_lesson_plan(self, user_id):
        return self.plan

    async def save_lesson_plan(self, row):
        self.plan = row

    async def count_finished_lessons(self, user_id):
        return len(self.finished)

    async def get_active_mini_lesson(self, user_id):
        return self.mini_sessions.get(user_id)

    async def start_mini_lesson(self, user_id, topic, deck_json, preset):
        session = SimpleNamespace(
            id=len(self.mini_sessions) + 1,
            user_id=user_id,
            topic=topic,
            content_json=deck_json,
            preset=preset,
            score_json=None,
            status="active",
        )
        self.mini_sessions[user_id] = session
        return session

    async def finish_mini_lesson(self, session_id, score_json=None):
        self.finished.append((session_id, score_json))
        for user_id, session in list(self.mini_sessions.items()):
            if session.id == session_id:
                self.mini_sessions.pop(user_id, None)

    async def add_lesson_note(self, note):
        self.notes.append(note)
        return len(self.notes)

    async def get_stats(self, user_id):
        return SimpleNamespace(total_turns=0, correct=0, errors=0, top_categories=[])

    async def get_practice_dates(self, user_id, limit=50):
        return []

    async def get_srs_word(self, user_id, word):
        return None

    async def add_srs_word(self, word):
        self.srs_words.append(word)

    async def get_unlimited_status(self, user_id):
        return False

    async def get_subscription(self, user_id):
        return None

    async def get_llm_usage(self, user_id, day):
        return 3

    async def get_extra_actions(self, user_id):
        return 0

    async def append_event(self, user_id, event_type, payload=None):
        return None

    async def save_audio_answer(self, session_id, word, audio_file, transcript, rating):
        self.audio_answers.append(
            {
                "session_id": session_id,
                "word": word,
                "audio_file": audio_file,
                "transcript": transcript,
                "rating": rating,
            }
        )


class FakeQuota:
    """Контракт повторяет bot.quota.QuotaGuard: check + consume(cost=...)."""

    def __init__(self, repo=None, daily_limit: int = 30, exceeded: bool = False):
        self._repo = repo
        self._daily_limit = daily_limit
        self.exceeded = exceeded
        self.check_calls = 0
        self.consume_costs = []

    async def check(self, user_id):
        self.check_calls += 1
        if self.exceeded:
            raise QuotaExceeded("квота исчерпана")

    async def consume(self, user_id, *, cost=1):
        self.consume_costs.append(cost)
        if self.exceeded:
            raise QuotaExceeded("квота исчерпана")


class FakeLLM:
    def __init__(self):
        self.calls = 0

    async def chat(self, messages, temperature=None, json_mode=False):
        self.calls += 1
        return "{}"


class FakeSRS:
    def __init__(self):
        self.added = []

    async def add_words(self, user_id, words, lesson_id=0):
        self.added.append((user_id, words, lesson_id))
        return len(words)


class FakeTTS:
    def __init__(self):
        self.calls = []

    async def synthesize(self, text, voice=None):
        self.calls.append((text, voice))
        return b"ID3-fake-mp3"


class FakeSTT:
    def __init__(self, text: str = ""):
        self.text = text
        self.calls = 0

    async def transcribe(self, wav_path):
        self.calls += 1
        return self.text


def fake_deck() -> Deck:
    return Deck(
        title="Coffee Around the World",
        subtitle_ru="Путешествие",
        preset="mixed",
        emoji="☕",
        vocabulary=[VocabCard(word="brew", translation="заваривать", example="I brew coffee.")],
        quiz=[
            QuizItem(
                question="What does brew mean?",
                options=["заваривать", "пить"],
                answer_index=0,
                explanation_ru="to brew — заваривать",
            )
        ],
    )


def make_deps(repo=None, quota=None, generator=None, **extra):
    repo = repo or FakeRepo()
    deps = {
        "repo": repo,
        "llm": FakeLLM(),
        "quota": quota or FakeQuota(repo),
        "srs": FakeSRS(),
        "tts": FakeTTS(),
    }
    if generator is not None:
        deps["deck_generator"] = generator
    deps.update(extra)
    return deps


async def make_client(deps=None, settings=None) -> TestClient:
    app = create_webapp(settings or Settings(telegram_bot_token=BOT_TOKEN), None, deps or make_deps())
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


# ---------- валидация initData ----------


def test_validate_init_data_accepts_valid_signature():
    assert validate_init_data(BOT_TOKEN, make_init_data()) == TG_USER_ID


def test_validate_init_data_rejects_tampered_payload():
    init_data = make_init_data()
    tampered = init_data.replace(f'"id": {TG_USER_ID}', f'"id": {TG_USER_ID + 1}')
    assert tampered != init_data
    assert validate_init_data(BOT_TOKEN, tampered) is None


def test_validate_init_data_rejects_wrong_token_and_garbage():
    assert validate_init_data("999:other", make_init_data()) is None
    assert validate_init_data(BOT_TOKEN, "hash=deadbeef&user=%7B%7D") is None
    assert validate_init_data(BOT_TOKEN, "") is None
    assert validate_init_data("", make_init_data()) is None


def test_validate_init_data_without_user_is_none():
    params = {"auth_date": "1", "hash": compute_hash(BOT_TOKEN, {"auth_date": "1"})}
    assert validate_init_data(BOT_TOKEN, sign_init_data(BOT_TOKEN, params)) is None


def test_data_check_string_is_sorted_and_skips_hash():
    params = {"b": "2", "a": "1", "hash": "x"}
    from bot.webapp import data_check_string

    assert data_check_string(params) == "a=1\nb=2"
    assert "hash" not in data_check_string(params)


def test_parse_init_data_reads_user_json():
    params = parse_init_data(make_init_data())
    assert json.loads(params["user"])["id"] == TG_USER_ID
    assert "hash" in params


# ---------- статика и health ----------


async def test_index_serves_mini_app_mount():
    client = await make_client()
    try:
        response = await client.get("/")
        assert response.status == 200
        body = await response.text()
        assert 'id="app"' in body
        assert "no-store" in response.headers.get("Cache-Control", "")
    finally:
        await client.close()


async def test_static_assets_are_served_with_cache_headers():
    client = await make_client()
    try:
        for path in ("/app.js", "/style.css"):
            response = await client.get(path)
            assert response.status == 200, path
            assert "max-age" in response.headers.get("Cache-Control", "")
    finally:
        await client.close()


async def test_health_returns_ok():
    client = await make_client()
    try:
        response = await client.get("/api/health")
        assert response.status == 200
        assert await response.json() == {"ok": True}
    finally:
        await client.close()


async def test_init_returns_profile_and_401_on_bad_signature():
    client = await make_client()
    try:
        ok = await client.post("/api/init", json={"initData": make_init_data()})
        assert ok.status == 200
        payload = await ok.json()
        assert payload["ok"] is True
        assert payload["user_id"] == TG_USER_ID
        assert payload["level"] == "B1"
        assert payload["quota_left"] == 27
        assert payload["character"] == "Chill Teacher"
        assert payload["interests"] == ["coffee", "travel"]

        broken = await client.post("/api/init", json={"initData": make_init_data() + "x"})
        assert broken.status == 401
        assert (await broken.json()) == {"ok": False, "error": "unauthorized"}

        missing = await client.post("/api/init", json={})
        assert missing.status == 401
    finally:
        await client.close()


async def test_tts_returns_base64_mp3():
    deps = make_deps()
    client = await make_client(deps)
    try:
        response = await client.post(
            "/api/tts", json={"initData": make_init_data(), "text": "brew", "word": "brew"}
        )
        assert response.status == 200
        payload = await response.json()
        assert base64.b64decode(payload["audio_base64"]) == b"ID3-fake-mp3"
        assert deps["tts"].calls[0][0] == "brew"
    finally:
        await client.close()


# ---------- deck API ----------


async def test_deck_new_generates_deck_and_starts_session():
    calls = []

    async def generator(llm, **kwargs):
        calls.append(kwargs)
        return fake_deck()

    repo = FakeRepo()
    quota = FakeQuota(repo)
    deps = make_deps(repo=repo, quota=quota, generator=generator)
    client = await make_client(deps)
    try:
        response = await client.post(
            "/api/deck/new",
            json={"initData": make_init_data(), "topic": "Coffee", "preset": "mixed"},
        )
        assert response.status == 200
        payload = await response.json()
        assert payload["ok"] is True
        assert payload["deck"]["title"] == "Coffee Around the World"
        assert payload["deck"]["quiz"][0]["answer_index"] == 0
        assert payload["session_id"] == 1
        assert quota.consume_costs == [1]
        assert calls[0]["topic"] == "Coffee"
        assert calls[0]["preset"] == "mixed"
        assert calls[0]["level"] == "B1"
        assert repo.get_active_mini_lesson is not None
    finally:
        await client.close()


async def test_deck_new_quota_exceeded_does_not_generate():
    async def generator(llm, **kwargs):
        raise AssertionError("генерация не должна вызываться при QuotaExceeded")

    quota = FakeQuota(exceeded=True)
    client = await make_client(make_deps(quota=quota, generator=generator))
    try:
        response = await client.post(
            "/api/deck/new", json={"initData": make_init_data(), "topic": "Coffee"}
        )
        assert response.status == 429
        payload = await response.json()
        assert payload["ok"] is False
        assert payload["error"] == "quota"
        assert "промокод" in payload["message"].lower()
        assert quota.consume_costs == []
    finally:
        await client.close()


async def test_deck_new_generation_failure_is_soft_error():
    async def generator(llm, **kwargs):
        return None

    client = await make_client(make_deps(generator=generator))
    try:
        response = await client.post(
            "/api/deck/new", json={"initData": make_init_data(), "topic": "Coffee"}
        )
        assert response.status == 502
        assert await response.json() == {"ok": False, "error": "generation_failed"}
    finally:
        await client.close()


async def test_deck_answer_checks_correctness_without_db_write():
    repo = FakeRepo()
    client = await make_client(make_deps(repo=repo))
    try:
        # кладём сессию с декой напрямую (без LLM)
        await repo.start_mini_lesson(TG_USER_ID, "Coffee", DECK_JSON, "mixed")

        good = await client.post(
            "/api/deck/answer",
            json={
                "initData": make_init_data(),
                "session_id": 1,
                "question_index": 0,
                "answer_index": 0,
            },
        )
        payload = await good.json()
        assert payload["ok"] is True
        assert payload["correct"] is True
        assert payload["explanation"] == "to brew — заваривать"

        bad = await client.post(
            "/api/deck/answer",
            json={
                "initData": make_init_data(),
                "session_id": 1,
                "question_index": 0,
                "selected_index": 1,
            },
        )
        assert (await bad.json())["correct"] is False
        assert repo.finished == []  # ответы не пишут в БД до finish
    finally:
        await client.close()


async def test_deck_answer_without_session_is_404():
    client = await make_client()
    try:
        response = await client.post(
            "/api/deck/answer",
            json={"initData": make_init_data(), "session_id": 7, "quiz_index": 0, "chosen": 0},
        )
        assert response.status == 404
        assert (await response.json())["error"] == "session_not_found"
    finally:
        await client.close()


async def test_deck_finish_runs_finalization():
    repo = FakeRepo()
    srs = FakeSRS()
    quota = FakeQuota(repo)
    deps = make_deps(repo=repo, quota=quota)
    deps["srs"] = srs
    client = await make_client(deps)
    try:
        await repo.start_mini_lesson(TG_USER_ID, "Coffee", DECK_JSON, "mixed")
        response = await client.post(
            "/api/deck/finish",
            json={
                "initData": make_init_data(),
                "session_id": 1,
                "preset": "mixed",
                "score": 1,
                "quiz_answers": [
                    {"question_index": 0, "chosen": 0, "correct": True},
                ],
                "flashcards": {"brew": False, "roast": True},
            },
        )
        assert response.status == 200
        payload = await response.json()
        assert payload["ok"] is True
        assert payload["score"] == 1
        assert payload["xp"] >= 10  # заметка урока -> +10 XP
        assert payload["repeat_words"] == ["brew"]
        # score_json сохранён, сессия закрыта
        assert repo.finished[0][0] == 1
        assert json.loads(repo.finished[0][1]) == [{"quiz_index": 0, "chosen": 0, "correct": True}]
        assert await repo.get_active_mini_lesson(TG_USER_ID) is None
        # слова деки ушли в SRS
        assert srs.added[0][1][0]["word"] == "brew"
        # заметка урока создана -> прогресс/достижения видят урок
        assert repo.notes and repo.notes[0].topic == "Coffee"
    finally:
        await client.close()


async def test_deck_finish_survives_broken_finalization():
    repo = FakeRepo()

    async def boom(*args, **kwargs):
        raise RuntimeError("SRS упал")

    client = await make_client(make_deps(repo=repo, srs=SimpleNamespace(add_words=boom)))
    try:
        await repo.start_mini_lesson(TG_USER_ID, "Coffee", DECK_JSON, "mixed")
        response = await client.post(
            "/api/deck/finish",
            json={"initData": make_init_data(), "session_id": 1, "score": 0, "flashcards": {}},
        )
        assert response.status == 200
        assert (await response.json())["ok"] is True
    finally:
        await client.close()


# ---------- голосовые реплики ----------


async def _fake_to_wav(src, dst, sample_rate=16000):
    """to_wav из providers.audio вместо реального ffmpeg — аудио-байты в тесте фейковые."""
    return None


async def test_voice_answer_returns_transcript_and_rating(monkeypatch):
    monkeypatch.setattr("providers.audio.to_wav", _fake_to_wav)
    repo = FakeRepo()
    deps = make_deps(repo=repo)
    deps["stt"] = FakeSTT("Coffee is great")
    client = await make_client(deps)
    try:
        await repo.start_mini_lesson(TG_USER_ID, "Coffee", DECK_JSON, "mixed")
        response = await client.post(
            "/api/voice/answer",
            json={
                "initData": make_init_data(),
                "audio_base64": base64.b64encode(b"fake-audio-bytes").decode(),
                "expected_line": "Coffee is great",
            },
        )
        assert response.status == 200
        payload = await response.json()
        assert payload["ok"] is True
        assert payload["transcript"] == "Coffee is great"
        assert payload["rating"] == 100
        assert payload["tip"]
        assert repo.audio_answers and repo.audio_answers[0]["rating"] == 100
    finally:
        await client.close()


async def test_voice_answer_reports_no_speech(monkeypatch):
    monkeypatch.setattr("providers.audio.to_wav", _fake_to_wav)
    repo = FakeRepo()
    deps = make_deps(repo=repo)
    deps["stt"] = FakeSTT("  ")
    client = await make_client(deps)
    try:
        await repo.start_mini_lesson(TG_USER_ID, "Coffee", DECK_JSON, "mixed")
        response = await client.post(
            "/api/voice/answer",
            json={"initData": make_init_data(), "audio_base64": base64.b64encode(b"x").decode()},
        )
        assert response.status == 400
        assert (await response.json())["error"] == "no_speech"
    finally:
        await client.close()


async def test_voice_answer_requires_valid_audio(monkeypatch):
    monkeypatch.setattr("providers.audio.to_wav", _fake_to_wav)
    client = await make_client()
    try:
        response = await client.post(
            "/api/voice/answer",
            json={"initData": make_init_data(), "audio_base64": "not base64!!!"},
        )
        assert response.status == 400
        assert (await response.json())["error"] == "audio_required"
    finally:
        await client.close()


def test_phrase_rating_meas_similarity():
    assert _phrase_rating("coffee is great", "Coffee is great") == 100
    assert _phrase_rating("coffee good", "Coffee is great") == 33
    assert _phrase_rating("", "Coffee is great") == 0
    assert _phrase_rating("totally unrelated words here", "Coffee is great") == 0
    assert _phrase_rating("anything", "") is None


async def test_quiz_results_normalizes_front_payload():
    results = _quiz_results(
        {
            "quiz_answers": [
                {"question_index": 0, "index": 0, "chosen": 2, "correct": False},
                "junk",
                {"index": 1, "answer_index": 1, "correct": True},
            ]
        }
    )
    assert results == [
        {"quiz_index": 0, "chosen": 2, "correct": False},
        {"quiz_index": 1, "chosen": 1, "correct": True},
    ]


# ---------- конфиг и отладочный режим ----------


def test_webapp_settings_defaults():
    settings = Settings(telegram_bot_token=BOT_TOKEN)
    assert settings.webapp_url == ""
    assert settings.webapp_port == 8081
    assert settings.webapp_host == "127.0.0.1"
    assert settings.webapp_insecure_auth == 0
    assert settings.webapp_enabled is False


async def test_insecure_auth_skips_signature_check():
    settings = Settings(telegram_bot_token=BOT_TOKEN, webapp_insecure_auth=1)
    client = await make_client(make_deps(), settings)
    try:
        response = await client.post("/api/init", json={"initData": "user=%7B%22id%22%3A777%7D"})
        assert response.status == 200
        assert (await response.json())["user_id"] == 777
    finally:
        await client.close()


@pytest.mark.parametrize(
    "path",
    ["/api/init", "/api/deck/new", "/api/deck/answer", "/api/deck/finish", "/api/voice/answer"],
)
async def test_all_post_endpoints_require_init_data(path):
    client = await make_client()
    try:
        response = await client.post(path, json={})
        assert response.status == 401
        assert (await response.json()) == {"ok": False, "error": "unauthorized"}
    finally:
        await client.close()
