import asyncio
import os
from types import SimpleNamespace

import pytest

from bot.handlers.voice import on_voice
from providers.audio import to_ogg_opus, to_wav


class Boom:
    def __getattr__(self, name):
        raise AssertionError(f"не должен вызываться: {name}")


class StubState:
    def __init__(self, state=None):
        self._state = state
        self.clear_calls = 0

    async def get_state(self):
        return self._state

    async def set_state(self, s=None):
        self._state = s

    async def clear(self):
        self._state = None
        self.clear_calls += 1


class StubMessage:
    def __init__(self):
        self.answers = []
        self.voice = SimpleNamespace(duration=2, file_id="x")
        self.chat = SimpleNamespace(id=1)
        self.message_id = 1
        self.from_user = SimpleNamespace(id=1, username="u", first_name="F")

    async def answer(self, text, reply_markup=None):
        self.answers.append((text, reply_markup))


async def test_voice_during_review_returns_hint_without_stt():
    msg = StubMessage()
    boom = Boom()
    state = StubState("bot.handlers.review:ReviewState:answering")

    await on_voice(
        msg,
        boom,
        boom,
        boom,
        boom,
        boom,
        boom,
        boom,
        state=state,
    )

    assert msg.answers and "повторение" in msg.answers[0][0]
    assert state.clear_calls == 0  # FSM повторения не тронут


async def _generate_ogg(path: str) -> None:
    from providers.audio import ffmpeg_exe

    proc = await asyncio.create_subprocess_exec(
        ffmpeg_exe(),
        "-y",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=1",
        "-c:a",
        "libopus",
        "-f",
        "ogg",
        path,
    )
    assert (await proc.wait()) == 0


async def test_to_wav_from_ogg_roundtrip(tmp_path):
    src_ogg = str(tmp_path / "test.ogg")
    wav = str(tmp_path / "test.wav")
    ogg_out = str(tmp_path / "out.ogg")

    await _generate_ogg(src_ogg)
    assert os.path.getsize(src_ogg) > 0

    await to_wav(src_ogg, wav)
    assert os.path.exists(wav) and os.path.getsize(wav) > 0

    await to_ogg_opus(wav, ogg_out)
    assert os.path.exists(ogg_out) and os.path.getsize(ogg_out) > 0


async def test_to_wav_missing_input_raises(tmp_path):
    with pytest.raises(RuntimeError):
        await to_wav(str(tmp_path / "missing.ogg"), str(tmp_path / "out.wav"))
