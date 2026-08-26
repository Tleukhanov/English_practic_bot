"""Команда /leaderboard — рейтинг пользователей."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from core.progress import ProgressService
from storage.repo import Repository

from ..formatters import format_leaderboard
from ..keyboards import main_menu

router = Router()


@router.message(Command("leaderboard"))
async def cmd_leaderboard(message: Message, repo: Repository) -> None:
    user = await repo.get_or_create_user(message.from_user.id)
    rows = await repo.get_leaderboard(limit=10)

    current_position = None
    for i, row in enumerate(rows, 1):
        if row.user_id == user.id:
            current_position = i
            break

    if current_position is None:
        all_rows = await repo.get_leaderboard(limit=999)
        for i, row in enumerate(all_rows, 1):
            if row.user_id == user.id:
                current_position = i
                break

    await message.answer(
        format_leaderboard(rows, user.id, current_position),
        reply_markup=main_menu(),
    )


@router.callback_query(F.data == "leaderboard")
async def cb_leaderboard(callback: CallbackQuery, repo: Repository) -> None:
    user = await repo.get_or_create_user(
        callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    rows = await repo.get_leaderboard(limit=10)

    current_position = None
    for i, row in enumerate(rows, 1):
        if row.user_id == user.id:
            current_position = i
            break

    if current_position is None:
        all_rows = await repo.get_leaderboard(limit=999)
        for i, row in enumerate(all_rows, 1):
            if row.user_id == user.id:
                current_position = i
                break

    await callback.message.answer(
        format_leaderboard(rows, user.id, current_position),
        reply_markup=main_menu(),
    )
    await callback.answer()
