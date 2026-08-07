"""Работа с аудио через ffmpeg.

imageio-ffmpeg поставляет статический бинарник ffmpeg в составе пакета,
поэтому ставить ffmpeg в систему не нужно — работает на Windows/macOS/Linux.
"""

import asyncio

from imageio_ffmpeg import get_ffmpeg_exe

_FFMPEG: str | None = None


def ffmpeg_exe() -> str:
    global _FFMPEG
    if _FFMPEG is None:
        _FFMPEG = get_ffmpeg_exe()
    return _FFMPEG


async def _run(args: list[str]) -> None:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    code = await proc.wait()
    if code != 0:
        raise RuntimeError(f"ffmpeg завершился с кодом {code}: {' '.join(args)}")


async def to_wav(src: str, dst: str, sample_rate: int = 16000) -> None:
    """Конвертация любого аудио (в т.ч. .ogg) в wav 16кГц моно — формат для Whisper."""
    await _run([
        ffmpeg_exe(), "-y", "-i", src,
        "-ar", str(sample_rate), "-ac", "1",
        "-f", "wav", dst,
    ])


async def to_ogg_opus(src: str, dst: str, bitrate: str = "48k") -> None:
    """Конвертация mp3 -> ogg/opus — единственный формат голосовых в Telegram."""
    await _run([
        ffmpeg_exe(), "-y", "-i", src,
        "-c:a", "libopus", "-b:a", bitrate,
        "-f", "ogg", dst,
    ])
