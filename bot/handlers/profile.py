"""Профиль пользователя (Фаза 4): команда /profile и кнопка в меню.

Профиль ведёт сам бот по ходу практики; здесь — посмотреть, что он запомнил.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from storage.repo import Repository

from ..formatters import format_profile
from ..keyboards import main_menu

router = Router()


async def _show_profile(target, repo: Repository, user_from) -> None:
    user = await repo.get_or_create_user(
        user_from.id,
        username=user_from.username,
        first_name=user_from.first_name,
    )
    profile = await repo.get_profile(user.id)
    await target.answer(format_profile(profile, user.level), reply_markup=main_menu())


@router.message(Command("profile"))
async def cmd_profile(message: Message, repo: Repository) -> None:
    await _show_profile(message, repo, message.from_user)


@router.callback_query(F.data == "profile")
async def cb_profile(callback: CallbackQuery, repo: Repository) -> None:
    await callback.answer()
    await _show_profile(callback.message, repo, callback.from_user)
