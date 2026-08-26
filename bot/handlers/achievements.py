"""Команда /achievements — достижения и уровни (Фаза 12)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from core.achievements import check_achievements, format_achievements
from core.progress import ProgressService
from storage.repo import Repository

from ..keyboards import main_menu

router = Router()


@router.message(Command("achievements"))
async def cmd_achievements(message: Message, repo: Repository) -> None:
    user = await repo.get_or_create_user(message.from_user.id)
    service = ProgressService(repo)
    progress = await service.get_progress(user.id, level=user.level)
    achievements = check_achievements(progress)
    await message.answer(format_achievements(achievements, progress), reply_markup=main_menu())


@router.callback_query(F.data == "achievements")
async def cb_achievements(callback: CallbackQuery, repo: Repository) -> None:
    user = await repo.get_or_create_user(
        callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    service = ProgressService(repo)
    progress = await service.get_progress(user.id, level=user.level)
    achievements = check_achievements(progress)
    await callback.message.answer(format_achievements(achievements, progress), reply_markup=main_menu())
    await callback.answer()
