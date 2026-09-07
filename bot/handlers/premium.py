"""Премиум/подписка: статус, тарифы и покупка (/premium)."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import Settings
from storage.repo import Repository

from ..keyboards import main_menu
from ..quota import QuotaGuard

router = Router()
logger = logging.getLogger(__name__)


def premium_keyboard(plans: list[tuple[int, int]], coupon=None) -> InlineKeyboardMarkup:
    """Кнопки покупки подписки. Coupon — WheelCoupon|None со скидкой."""
    rows: list[list[InlineKeyboardButton]] = []
    for days, price in plans:
        final = price
        if coupon is not None and not coupon.is_expired:
            final = price - price * coupon.discount_pct // 100
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"Купить {days} дней — {final}₽ (-{coupon.discount_pct}%)",
                        callback_data=f"premium:buy:{days}",
                    )
                ]
            )
        else:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"Купить {days} дней — {price}₽",
                        callback_data=f"premium:buy:{days}",
                    )
                ]
            )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("premium"))
async def cmd_premium(
    message: Message, repo: Repository, settings: Settings, quota: QuotaGuard
) -> None:
    user = await repo.get_or_create_user(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    lines: list[str] = ["💎 <b>Лимиты и подписка</b>\n"]
    sub = await repo.get_subscription(user.id)
    if sub and sub.is_active:
        lines.append(f"✅ Подписка активна: {sub.plan_days} дн., до {sub.expires_at[:10]}")
    else:
        lines.append("➖ Подписки нет — действует дневной лимит.")
    if await repo.get_unlimited_status(user.id):
        lines.append("♾️ Промокод: <b>безлимит</b> активен")
    if settings.llm_daily_limit > 0:
        used = await repo.get_llm_usage(user.id, quota._today())
        lines.append(f"📊 ИИ-действий сегодня: {used}/{settings.llm_daily_limit}")
    extra = await repo.get_extra_actions(user.id)
    lines.append(f"🎁 Бонусных действий сверх лимита: {extra}")
    coupon = await repo.get_active_coupon(user.id)
    if coupon and not coupon.is_expired:
        lines.append(f"🎟 Купон на скидку {coupon.discount_pct}% при покупке!")
    await message.answer(
        "\n".join(lines),
        reply_markup=premium_keyboard(settings.subscription_plan_list, coupon=coupon),
    )
    logger.info("/premium: user=%s", user.id)


@router.callback_query(F.data.startswith("premium:buy:"))
async def cb_premium_buy(callback: CallbackQuery, repo: Repository, settings: Settings) -> None:
    await callback.answer()
    days_text = callback.data.removeprefix("premium:buy:")
    try:
        days = int(days_text)
    except ValueError:
        await callback.message.answer("❌ Некорректный тариф.")
        return
    plan = next((p for p in settings.subscription_plan_list if p[0] == days), None)
    if plan is None:
        await callback.answer("Не найден тариф")
        return
    user = await repo.get_or_create_user(
        callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    price = plan[1]
    coupon = await repo.get_active_coupon(user.id)
    discount = 0
    final = price
    if coupon and not coupon.is_expired:
        discount = coupon.discount_pct
        final = price - price * discount // 100
    text = f"Подписка {days} дней, цена {final}₽"
    if discount:
        text += f" (со скидкой {discount}%)"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 Оплатить", callback_data=f"premium:confirm:{days}"
                )
            ]
        ]
    )
    await callback.message.answer(text, reply_markup=keyboard)
    logger.info("premium buy: user=%s days=%s final=%s", user.id, days, final)