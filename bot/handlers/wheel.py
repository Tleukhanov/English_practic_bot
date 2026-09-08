"""Колесо удачи: /wheel, анимация вращения и выдача приза."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from core.wheel import (
    JACKPOT,
    SECTOR_TITLES,
    WHEEL_SECTORS,
    WheelCooldown,
    WheelPrize,
    WheelService,
)

from ..keyboards import main_menu
from storage.repo import Repository

router = Router()
logger = logging.getLogger(__name__)


def spin_keyboard() -> InlineKeyboardMarkup:
    """Кнопка запуска вращения."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🎡 Крутить", callback_data="wheel:spin")]]
    )


def wheel_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для пункта меню «Колесо удачи» (кнопка вернёт на /wheel)."""
    return spin_keyboard()


def format_wheel_legend() -> str:
    total = sum(weight for _, weight in WHEEL_SECTORS)
    lines = [
        "🎡 Колесо удачи",
        "",
        "Одна бесплатная крутка каждый день. Среди секторов:",
        "",
    ]
    for kind, weight in WHEEL_SECTORS:
        chance = round(weight / total * 100)
        lines.append(f"• {SECTOR_TITLES[kind]} — {chance}%")
    return "\n".join(lines)


def _status_line(available: bool) -> str:
    if available:
        return "\n\n🎯 Крутка доступна! Нажимай «Крутить»."
    return "\n\n⏳ Ты уже крутил сегодня. Возвращайся завтра!"


def format_wheel_prize(prize: WheelPrize) -> str:
    lines = [f"🎡 {prize.title}", "", prize.description]
    if prize.coupon_expires_at:
        try:
            expires = datetime.fromisoformat(prize.coupon_expires_at.replace("Z", "+00:00"))
            human = expires.strftime("%d.%m в %H:%M UTC")
        except ValueError:
            human = prize.coupon_expires_at
        lines.append(f"\n⏰ Купон действует до {human}")
    elif prize.kind == JACKPOT:
        lines.append("\n⏰ Безлимит активен 24 часа с момента выигрыша.")
    return "\n".join(lines)


async def _animate(status: Message) -> None:
    """Псевдо-вращение: бегущий указатель по секторам."""
    cells = ["🎯", "💸", "⚡", "🎁", "💎", "⭕"]
    for step in range(6):
        idx = step % len(cells)
        row = " ".join(f"▸{c}◂" if i == idx else c for i, c in enumerate(cells))
        await status.edit_text(f"🎡 {row}\n\nКрутим...")
        await asyncio.sleep(0.35)


async def _get_user(message: Message, repo: Repository):
    return await repo.get_or_create_user(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )


@router.message(Command("wheel"))
async def cmd_wheel(message: Message, repo: Repository) -> None:
    user = await _get_user(message, repo)
    service = WheelService(repo)
    available = await service.is_spin_available(user.id)
    await message.answer(format_wheel_legend() + _status_line(available), reply_markup=spin_keyboard())


@router.callback_query(F.data == "wheel:start")
async def cb_wheel_start(callback: CallbackQuery, repo: Repository) -> None:
    user = await _get_user(callback.message, repo)
    service = WheelService(repo)
    available = await service.is_spin_available(user.id)
    await callback.message.answer(format_wheel_legend() + _status_line(available), reply_markup=spin_keyboard())
    await callback.answer()


@router.callback_query(F.data == "wheel:spin")
async def cb_wheel_spin(callback: CallbackQuery, repo: Repository) -> None:
    user = await _get_user(callback.message, repo)
    service = WheelService(repo)
    status: Message | None = None
    try:
        if not await service.is_spin_available(user.id):
            await callback.message.edit_text("Сегодня уже крутил! Возвращайся завтра 🎡")
            await callback.answer()
            return

        status = await callback.message.edit_text("🎡 Крутим колесо...", reply_markup=None)
        prize = await service.spin(user.id)
        await _animate(status)
        await status.edit_text(format_wheel_prize(prize), reply_markup=main_menu())
        await callback.answer()
    except WheelCooldown:
        text = "Сегодня уже крутил! Возвращайся завтра 🎡"
        if status is not None:
            await status.edit_text(text)
        else:
            await callback.message.edit_text(text)
        await callback.answer()
    except Exception as exc:
        logger.exception("Ошибка колеса удачи: user=%s exc=%s", user.id, exc)
        text = "⚠️ Что-то пошло не так. Попробуй ещё раз."
        if status is not None:
            await status.edit_text(text)
        else:
            await callback.message.edit_text(text)
        await callback.answer()