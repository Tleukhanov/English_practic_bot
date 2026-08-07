"""STT через локальный faster-whisper (CTranslate2, работает на CPU)."""

import asyncio

from faster_whisper import WhisperModel

from .base import STTProvider


class FasterWhisperProvider(STTProvider):
    """Ленивая загрузка модели: качается при первом распознавании, не при старте бота."""

    def __init__(self, model_name: str = "small", device: str = "cpu", compute_type: str = "int8"):
        self._model_name = model_name
        self._device = device
        self._compute_type = compute_type
        self._model: WhisperModel | None = None

    def _ensure_model(self) -> WhisperModel:
        if self._model is None:
            self._model = WhisperModel(
                self._model_name,
                device=self._device,
                compute_type=self._compute_type,
            )
        return self._model

    def _run(self, audio_path: str) -> str:
        model = self._ensure_model()
        segments, _info = model.transcribe(audio_path, language="en", vad_filter=True)
        return "".join(segment.text for segment in segments).strip()

    async def transcribe(self, audio_path: str) -> str:
        return await asyncio.to_thread(self._run, audio_path)
