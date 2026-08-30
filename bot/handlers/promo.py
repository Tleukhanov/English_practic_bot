"""Промокод на безлимит (/promo)."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import Settings
from storage.repo import Repository

from ..keyboards import main_menu

router = Router()
logger = logging.getLogger(__name__)

PROMO_ACTIVATED_TEXT = (
    "🎉 Промокод принят! Дневной лимит ИИ снят — практикуй без ограничений."
)


@router.message(Command("promo"))
async def cmd_promo(message: Message, repo: Repository, settings: Settings) -> None:
    user = await repo.get_or_create_user(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    code = message.text.removeprefix("/promo").strip()
    expected = (settings.promo_unlimited_code or "").strip()
    if not expected:
        await message.answer("🎟 Промокоды пока недоступны. Скоро появятся!")
        return
    if not code:
        await message.answer("📮 Отправь промокод так: /promo ТВОЙ_КОД")
        return
    if code.lower() == expected.lower():
        await repo.set_unlimited_status(user.id, True)
        await message.answer(PROMO_ACTIVATED_TEXT, reply_markup=main_menu())
        logger.info("Промокод активирован: user=%s", user.id)
    else:
        await message.answer(
            "❌ Такого промокода нет. Проверь написание или напиши разработчику: @Napaleonwww"
        )