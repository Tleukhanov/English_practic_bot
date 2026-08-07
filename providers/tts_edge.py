"""TTS через бесплатный edge-tts (голоса Microsoft, нужен интернет)."""

import edge_tts

from .base import TTSProvider


class EdgeTTSProvider(TTSProvider):
    def __init__(self, voice: str = "en-US-JennyNeural"):
        self._voice = voice

    async def synthesize(self, text: str, voice: str | None = None) -> bytes:
        communicate = edge_tts.Communicate(text, voice or self._voice)
        chunks: list[bytes] = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
        return b"".join(chunks)
