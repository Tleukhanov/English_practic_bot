"""Админ-статистика: /admin (доступно только ADMIN_TG_ID)."""

from __future__ import annotations

from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from core.analytics import format_admin_stats

from bot.config import Settings
from storage.repo import Repository

router = Router()

NOT_ADMIN_TEXT = "⛔️ Эта команда доступна только администратору."


async def _stats_text(repo: Repository) -> str:
    today = datetime.now(timezone.utc).date().isoformat()
    pending = await repo.count_pending_orders()
    revenue = await repo.sum_revenue()
    active_subs = await repo.count_active_subscriptions()
    spins = await repo.count_spins_today(today)
    return format_admin_stats(pending, revenue, active_subs, spins)


def _refresh_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔄 Обновить", callback_data="admin:refresh")]]
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message, repo: Repository, settings: Settings) -> None:
    if message.from_user.id != settings.admin_tg_id:
        await message.answer(NOT_ADMIN_TEXT)
        return
    await message.answer(await _stats_text(repo), reply_markup=_refresh_keyboard())


@router.callback_query(F.data == "admin:refresh")
async def cb_admin_refresh(callback: CallbackQuery, repo: Repository, settings: Settings) -> None:
    if callback.from_user.id != settings.admin_tg_id:
        await callback.answer("Только админ.")
        return
    text = await _stats_text(repo)
    try:
        await callback.message.edit_text(text, reply_markup=_refresh_keyboard())
    except Exception:
        await callback.message.answer(text, reply_markup=_refresh_keyboard())
    await callback.answer("Обновлено")