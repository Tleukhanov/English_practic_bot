"""Команда /progress — полная статистика прогресса (Фаза 10)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from core.progress import ProgressService, format_progress
from storage.repo import Repository

from ..keyboards import main_menu

router = Router()


@router.message(Command("progress"))
async def cmd_progress(message: Message, repo: Repository) -> None:
    user = await repo.get_or_create_user(message.from_user.id)
    service = ProgressService(repo)
    data = await service.get_progress(user.id, level=user.level)
    await message.answer(format_progress(data), reply_markup=main_menu())


@router.callback_query(F.data == "progress")
async def cb_progress(callback: CallbackQuery, repo: Repository) -> None:
    user = await repo.get_or_create_user(
        callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    service = ProgressService(repo)
    data = await service.get_progress(user.id, level=user.level)
    await callback.message.answer(format_progress(data), reply_markup=main_menu())
    await callback.answer()
