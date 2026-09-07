"""Telegram Payments: инвойс за подписку, PreCheckout, подтверждение оплаты."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery

from bot.config import Settings
from storage.repo import Repository, Subscription, WheelCoupon

from ..keyboards import main_menu

router = Router()
logger = logging.getLogger(__name__)


def resolve_price(plan_price: int, coupon: WheelCoupon | None) -> tuple[int, int]:
    """Итоговая цена и скидка для тарифа. Без активного купона — без скидки."""
    if coupon is not None and not coupon.is_expired:
        discount_pct = coupon.discount_pct
        final_price = plan_price - plan_price * discount_pct // 100
        return final_price, discount_pct
    return plan_price, 0


def build_payload(days: int, user_id: int, coupon_id: int = 0) -> str:
    """Payload инвойса: sub:<days>:<user_id>:<coupon_id>."""
    return f"sub:{days}:{user_id}:{coupon_id}"


def discount_from_amount(full_price: int, paid_amount: int) -> int:
    """Процент скидки из полной цены тарифа и фактически оплаченной суммы."""
    if full_price <= 0:
        return 0
    return round((full_price - paid_amount) / full_price * 100)


async def apply_paid_subscription(
    repo: Repository,
    user_id: int,
    days: int,
    charge_id: str,
    amount: int,
    currency: str,
    discount_pct: int,
    coupon_id: int = 0,
) -> Subscription | None:
    """Идемпотентно записывает платёж и выдаёт подписку.

    None — платёж с таким charge_id уже применялся (подписка не удваивается).
    """
    if await repo.find_payment(charge_id) is not None:
        return None
    await repo.create_payment(user_id, charge_id, amount, currency, days, discount_pct)
    subscription = await repo.grant_subscription(user_id, days)
    if coupon_id > 0:
        coupon = await repo.get_active_coupon(user_id)
        if coupon is not None and coupon.id == coupon_id:
            await repo.mark_coupon_used(coupon_id)
    logger.info("Подписка применена: user=%s days=%s charge=%s", user_id, days, charge_id)
    return subscription


async def _safe_answer(callback: CallbackQuery, text: str | None = None) -> None:
    try:
        await callback.answer(text)
    except Exception:
        logger.exception("Не удалось ответить на callback: %s", callback.id)


@router.callback_query(F.data.startswith("premium:confirm:"))
async def cb_premium_confirm(callback: CallbackQuery, repo: Repository, settings: Settings) -> None:
    days_text = callback.data.removeprefix("premium:confirm:")
    try:
        days = int(days_text)
    except ValueError:
        await _safe_answer(callback, "Некорректный тариф.")
        return

    plan = next((p for p in settings.subscription_plan_list if p[0] == days), None)
    if plan is None:
        await _safe_answer(callback, "Такого тарифа нет")
        return

    if not settings.payments_provider_token:
        await _safe_answer(callback)
        try:
            await callback.message.answer(
                "💳 Платежи скоро будут доступны! А пока пиши разработчику: @Napaleonwww"
            )
        except Exception:
            logger.exception("Не удалось сообщить о недоступности платежей")
        return

    user = await repo.get_or_create_user(
        callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    coupon = await repo.get_active_coupon(user.id)
    final_price, discount_pct = resolve_price(plan[1], coupon)
    coupon_id = coupon.id if coupon is not None and not coupon.is_expired else 0
    description = (
        f"Полный доступ к ИИ на {days} дн. (скидка {discount_pct}%)"
        if discount_pct
        else f"Полный доступ к ИИ на {days} дн."
    )
    try:
        await callback.message.answer_invoice(
            title="English tutor — безлимит LLM",
            description=description,
            payload=build_payload(days, user.id, coupon_id),
            provider_token=settings.payments_provider_token,
            currency=settings.payments_currency,
            prices=[LabeledPrice(label=f"Подписка {days} дн.", amount=final_price)],
        )
    except Exception:
        logger.exception("Не удалось выставить инвойс: user=%s days=%s", user.id, days)
    await _safe_answer(callback)
    logger.info("Инвойс выставлен: user=%s days=%s final=%s", user.id, days, final_price)


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery) -> None:
    try:
        await query.answer(ok=True)
    except Exception:
        logger.exception("Ошибка pre-checkout: %s", query.id)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message, repo: Repository, settings: Settings) -> None:
    try:
        payment = message.successful_payment
        parts = (payment.invoice_payload or "").split(":")
        if len(parts) < 3:
            await message.answer(
                "❌ Не удалось распознать платёж. Напиши разработчику: @Napaleonwww",
                reply_markup=main_menu(),
            )
            return
        try:
            days = int(parts[1])
            user_id = int(parts[2])
        except (IndexError, ValueError):
            await message.answer(
                "❌ Не удалось распознать платёж. Напиши разработчику: @Napaleonwww",
                reply_markup=main_menu(),
            )
            return
        try:
            coupon_id = int(parts[3])
        except (IndexError, ValueError):
            coupon_id = 0

        plan = next((p for p in settings.subscription_plan_list if p[0] == days), None)
        full_price = plan[1] if plan else payment.total_amount
        discount_pct = discount_from_amount(full_price, payment.total_amount)

        subscription = await apply_paid_subscription(
            repo,
            user_id,
            days,
            payment.telegram_payment_charge_id,
            payment.total_amount,
            payment.currency,
            discount_pct,
            coupon_id=coupon_id,
        )
        if subscription is None:
            logger.warning("Повторная оплата: user=%s charge=%s", user_id, payment.telegram_payment_charge_id)
            await message.answer("✅ Подписка уже активирована", reply_markup=main_menu())
            return

        await message.answer(
            f"✅ Оплата принята! Подписка {days} дн. активна до {subscription.expires_at[:10]}",
            reply_markup=main_menu(),
        )
        logger.info(
            "Оплата принята: user=%s days=%s charge=%s discount=%s%%",
            user_id,
            days,
            payment.telegram_payment_charge_id,
            discount_pct,
        )
    except Exception:
        logger.exception(
            "Ошибка обработки successful_payment: user=%s",
            getattr(message.from_user, "id", "?"),
        )
        try:
            await message.answer(
                "❌ Не удалось применить платёж. Напиши разработчику: @Napaleonwww",
                reply_markup=main_menu(),
            )
        except Exception:
            logger.exception("Не удалось отправить сообщение об ошибке оплаты")