"""Хэндлер /review — повторение слов по SRS (Фаза 13).

Пользователь видит слово на русском → вводит перевод → получает оценку.
Качество ответа определяет интервал следующего повторения.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from core.srs import SRSService
from storage.repo import Repository

from ..keyboards import main_menu

router = Router()
logger = logging.getLogger(__name__)


class ReviewState(StatesGroup):
    answering = State()


async def _start_review(message: Message, repo: Repository, srs: SRSService, state: FSMContext = None) -> None:
    user = await repo.get_or_create_user(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    stats = await srs.get_stats(user.id)
    if stats["due"] == 0:
        if state:
            await state.clear()
        await message.answer(
            f"🎉 Нет слов для повторения!\n"
            f"Всего слов: {stats['total']}, выучено: {stats['learned']}\n\n"
            f"Пройди урок, чтобы добавить новые слова: /lesson",
            reply_markup=main_menu(),
        )
        return

    words = await srs.get_due_words(user.id, limit=10)
    if not words:
        if state:
            await state.clear()
        await message.answer("🎉 Все слова повторены на сегодня!", reply_markup=main_menu())
        return

    if state:
        await state.set_state(ReviewState.answering)
    first = words[0]
    await message.answer(
        _review_card(first, stats["due"], 0),
        reply_markup=_review_cancel_keyboard(),
    )


def _review_card(word, total_due: int, reviewed: int) -> str:
    parts = [
        f"📖 <b>Повторение слов</b>  ({reviewed}/{total_due})",
        "",
        f"🇷🇺 <b>{word.translation}</b>",
        "",
        "Напиши это слово на английском:",
    ]
    if word.example:
        parts += ["", f"Пример: <i>{word.example}</i>"]
    return "\n".join(parts)


def _review_result_card(word, is_correct: bool, next_interval: int) -> str:
    if is_correct:
        emoji = "✅"
        verdict = "Правильно!"
    else:
        emoji = "❌"
        verdict = f"Неправильно. Правильно: <b>{word.word}</b>"

    parts = [
        f"{emoji} {verdict}",
        "",
        f"📖 <b>{word.word}</b> — {word.translation}",
        f"⏰ Следующее повторение: через {next_interval} дн.",
    ]
    return "\n".join(parts)


@router.message(Command("review"))
async def cmd_review(message: Message, repo: Repository, srs: SRSService, state: FSMContext) -> None:
    await _start_review(message, repo, srs, state)


@router.callback_query(F.data == "review:start")
async def cb_review_start(callback: CallbackQuery, repo: Repository, srs: SRSService, state: FSMContext) -> None:
    await callback.answer()
    await _start_review(callback.message, repo, srs, state)


def _review_cancel_keyboard():
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏹️ Завершить повторение", callback_data="review:cancel")]
    ])


@router.callback_query(F.data == "review:cancel")
async def cb_review_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.answer("Повторение завершено.", reply_markup=main_menu())


@router.message(ReviewState.answering)
async def on_review_answer(message: Message, repo: Repository, srs: SRSService, state: FSMContext) -> None:
    text = message.text.strip()
    if not text or len(text) < 2:
        return

    user = await repo.get_or_create_user(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    words = await srs.get_due_words(user.id, limit=10)
    if not words:
        return

    current = words[0]
    is_correct = text.lower().strip() == current.word.lower().strip()
    quality = 5 if is_correct else 1

    updated = await srs.review(current.id, quality)
    next_interval = updated.interval_days if updated else 1

    await message.answer(_review_result_card(current, is_correct, next_interval))

    remaining = await srs.get_due_words(user.id, limit=10)
    if remaining:
        next_word = remaining[0]
        stats = await srs.get_stats(user.id)
        await message.answer(
            _review_card(next_word, stats["due"], len(words) - len(remaining)),
            reply_markup=_review_cancel_keyboard(),
        )
    else:
        await state.clear()
        final_stats = await srs.get_stats(user.id)
        await message.answer(
            f"🎉 Повторение завершено!\n"
            f"Повторено: {len(words)} слов\n"
            f"Выучено: {final_stats['learned']}/{final_stats['total']}",
            reply_markup=main_menu(),
        )
