"""STT через локальный faster-whisper (CTranslate2, работает на CPU)."""

import asyncio

from faster_whisper import WhisperModel

from .base import STTProvider


class FasterWhisperProvider(STTProvider):
    def __init__(self, model_name: str = "small", device: str = "cpu", compute_type: str = "int8"):
        self._model = WhisperModel(model_name, device=device, compute_type=compute_type)

    def _run(self, audio_path: str) -> str:
        segments, _info = self._model.transcribe(audio_path, language="en", vad_filter=True)
        return "".join(segment.text for segment in segments).strip()

    async def transcribe(self, audio_path: str) -> str:
        return await asyncio.to_thread(self._run, audio_path)
