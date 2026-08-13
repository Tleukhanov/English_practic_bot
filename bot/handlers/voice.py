"""Голосовая практика: голосовое -> Whisper -> проверка -> ответ текстом + озвучка.

Если у пользователя идёт диагностика уровня — сообщение уходит в диагностику.
Если идёт структурированный урок — ответ получает клавиатуру урока.
"""

from __future__ import annotations

import logging
import os
import tempfile
import uuid

from aiogram import F, Router
from aiogram.types import FSInputFile, Message

from bot.config import Settings
from core.diagnostic import DiagnosticService
from core.practice import PracticeParseError, PracticeService
from providers.audio import to_ogg_opus, to_wav
from providers.base import STTProvider, TTSProvider
from storage.repo import Repository

from ..diagnostic import process_diagnostic_answer
from ..flow import get_or_create_user, run_practice
from ..keyboards import lesson_keyboard
from ..utils import escape

router = Router()
logger = logging.getLogger(__name__)


def _temp_paths(chat_id: int, message_id: int) -> tuple[str, str]:
    unique = f"voice_{chat_id}_{message_id}_{uuid.uuid4().hex[:6]}"
    base = os.path.join(tempfile.gettempdir(), unique)
    return f"{base}.ogg", f"{base}.wav"


def _spoken_text(result) -> str:
    """Что бот говорит голосом: естественная реплика диалога, не пересказ пользователя."""
    return (result.spoken_reply or result.next_question).strip()


def _cleanup(*paths: str) -> None:
    for path in paths:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except OSError:
            logger.warning("Не удалось удалить временный файл: %s", path)


async def _speak(
    message: Message,
    tts: TTSProvider,
    text: str,
    chat_id: int,
    message_id: int,
) -> None:
    """Синтезирует текст в голосовое и отправляет его пользователю.

    Ошибки не роняют основной поток — голосовое это бонус к текстовому ответу.
    """
    if not text:
        return
    try:
        audio = await tts.synthesize(text)
    except Exception:
        logger.exception("Ошибка TTS")
        return
    if not audio:
        return

    unique = f"tts_{chat_id}_{message_id}_{uuid.uuid4().hex[:6]}"
    base = os.path.join(tempfile.gettempdir(), unique)
    mp3_path = f"{base}.mp3"
    ogg_path = f"{base}.ogg"
    try:
        with open(mp3_path, "wb") as f:
            f.write(audio)
        await to_ogg_opus(mp3_path, ogg_path)
        await message.answer_voice(voice=FSInputFile(ogg_path))
    except Exception:
        logger.exception("Не удалось отправить голосовое")
    finally:
        _cleanup(mp3_path, ogg_path)


@router.message(F.voice)
async def on_voice(
    message: Message,
    repo: Repository,
    stt: STTProvider,
    tts: TTSProvider,
    practice: PracticeService,
    diagnostic_service: DiagnosticService,
    settings: Settings,
) -> None:
    voice = message.voice
    if voice.duration and voice.duration > settings.max_voice_duration_sec:
        await message.answer(
            f"⏱️ Слишком длинное сообщение ({voice.duration} сек). "
            f"Ограничение — {settings.max_voice_duration_sec} сек. Разбей на части."
        )
        return

    user = await repo.get_or_create_user(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    session = await repo.get_active_lesson(user.id)
    reply_markup = lesson_keyboard() if session is not None else None

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

    if await process_diagnostic_answer(message, repo, diagnostic_service, text):
        return

    prefix = f"🎤 Вы сказали: <i>{escape(text)}</i>"
    try:
        turn = await run_practice(
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

    await status.edit_text(turn.reply, reply_markup=reply_markup)
    await _speak(
        message,
        tts,
        _spoken_text(turn.result),
        message.chat.id,
        message.message_id,
    )
