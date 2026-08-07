"""STT через облачный API OpenAI whisper-1 (альтернатива локальному)."""

from openai import AsyncOpenAI

from .base import STTProvider


class OpenAIWhisperProvider(STTProvider):
    def __init__(self, api_key: str, model: str = "whisper-1"):
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def transcribe(self, audio_path: str) -> str:
        with open(audio_path, "rb") as audio_file:
            result = await self._client.audio.transcriptions.create(
                model=self._model,
                file=audio_file,
                language="en",
            )
        return (result.text or "").strip()
