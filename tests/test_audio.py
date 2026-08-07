import asyncio
import os

import pytest

from providers.audio import to_ogg_opus, to_wav


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
