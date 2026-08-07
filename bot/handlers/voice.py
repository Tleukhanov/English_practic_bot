"""Голосовая практика: голосовое -> Whisper -> проверка -> ответ текстом (и голосом в след. шаге)."""

from __future__ import annotations

import logging
import os
import tempfile
import uuid

from aiogram import F, Router
from aiogram.types import Message

from bot.config import Settings
from core.practice import PracticeParseError, PracticeService
from providers.audio import to_wav
from providers.base import STTProvider
from storage.repo import Repository

from ..flow import get_or_create_user, run_practice
from ..utils import escape

router = Router()
logger = logging.getLogger(__name__)


def _temp_paths(chat_id: int, message_id: int) -> tuple[str, str]:
    unique = f"voice_{chat_id}_{message_id}_{uuid.uuid4().hex[:6]}"
    base = os.path.join(tempfile.gettempdir(), unique)
    return f"{base}.ogg", f"{base}.wav"


def _cleanup(*paths: str) -> None:
    for path in paths:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except OSError:
            logger.warning("Не удалось удалить временный файл: %s", path)


@router.message(F.voice)
async def on_voice(
    message: Message,
    repo: Repository,
    stt: STTProvider,
    practice: PracticeService,
    settings: Settings,
) -> None:
    voice = message.voice
    if voice.duration and voice.duration > settings.max_voice_duration_sec:
        await message.answer(
            f"⏱️ Слишком длинное сообщение ({voice.duration} сек). "
            f"Ограничение — {settings.max_voice_duration_sec} сек. Разбей на части."
        )
        return

    await repo.get_or_create_user(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    status = await message.answer("🎧 Слушаю...")
    ogg_path, wav_path = _temp_paths(message.chat.id, message.message_id)

    try:
        file = await message.bot.get_file(voice.file_id)
        await message.bot.download_file(file.file_path, destination=ogg_path)
        await to_wav(ogg_path, wav_path)
        text = (await stt.transcribe(wav_path)).strip()
    except Exception as exc:
        logger.exception("Ошибка обработки голосового: %s", exc)
        await status.edit_text("😕 Не получилось разобрать голосовое. Попробуй ещё раз.")
        return
    finally:
        _cleanup(ogg_path, wav_path)

    if not text:
        await status.edit_text("🤷 Не расслышал слов. Попробуй говорить чётче и ближе к микрофону.")
        return

    prefix = f"🎤 Вы сказали: <i>{escape(text)}</i>"
    try:
        reply = await run_practice(
            message,
            repo,
            practice,
            settings,
            text,
            prefix=prefix,
        )
    except PracticeParseError as exc:
        logger.warning("Не удалось разобрать ответ LLM: %s", exc)
        await status.edit_text(f"{prefix}\n\n🤔 Не смог разобрать ответ модели. Попробуй сформулировать ещё раз.")
        return
    except Exception as exc:
        logger.exception("Ошибка при обращении к LLM: %s", exc)
        await status.edit_text(
            f"{prefix}\n\n⚠️ Что-то пошло не так при обращении к модели. "
            "Проверь LLM_API_KEY и LLM_PROVIDER в .env и попробуй ещё раз."
        )
        return

    await status.edit_text(reply)
