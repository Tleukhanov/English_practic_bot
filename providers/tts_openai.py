"""TTS через облачный API OpenAI (альтернатива edge-tts)."""

from openai import AsyncOpenAI

from .base import TTSProvider


class OpenAITTSProvider(TTSProvider):
    def __init__(self, api_key: str, voice: str = "alloy"):
        self._client = AsyncOpenAI(api_key=api_key)
        self._voice = voice

    async def synthesize(self, text: str, voice: str | None = None) -> bytes:
        response = await self._client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice=voice or self._voice,
            input=text,
        )
        return response.content
