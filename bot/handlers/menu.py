"""Меню: инлайн-кнопки и команда /stats."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from storage.repo import Repository

from ..formatters import format_stats
from ..keyboards import main_menu
from .start import HELP_TEXT

router = Router()


@router.message(Command("stats"))
async def cmd_stats(message: Message, repo: Repository) -> None:
    user = await repo.get_or_create_user(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    stats = await repo.get_stats(user.id)
    await message.answer(format_stats(stats, level=user.level), reply_markup=main_menu())


@router.callback_query(F.data == "stats")
async def cb_stats(callback: CallbackQuery, repo: Repository) -> None:
    await callback.answer()
    user = await repo.get_or_create_user(
        callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    stats = await repo.get_stats(user.id)
    await callback.message.answer(format_stats(stats, level=user.level), reply_markup=main_menu())


@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(HELP_TEXT, reply_markup=main_menu())
