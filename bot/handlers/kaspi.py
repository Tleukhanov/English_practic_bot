"""Kaspi QR оплата подписки с ручным подтверждением по чеку.

Пользователь оплачивает переводом с комментарием (order_code), жмёт
«Я оплатил», присылает скриншот/чек. Админ подтверждает или отклоняет.
"""

from __future__ import annotations

import asyncio
import logging
import random
import string
import uuid

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from core.analytics import track_event

from bot.config import Settings
from storage.repo import KaspiOrder, Repository, Subscription

router = Router()
logger = logging.getLogger(__name__)

FALLBACK_DEVELOPER = "@Napaleonwww"


ORDER_CODE_ALPHABET = string.ascii_uppercase + string.digits
ORDER_CODE_LENGTH = 8

_order_locks: dict[int, asyncio.Lock] = {}


def _order_lock() -> asyncio.Lock:
    """Per-event-loop lock: экземпляры Lock привязаны к текущему loop (pytest меняет loop на тест)."""
    loop_id = id(asyncio.get_running_loop())
    lock = _order_locks.get(loop_id)
    if lock is None:
        lock = asyncio.Lock()
        _order_locks[loop_id] = lock
    return lock


def _make_order_code() -> str:
    return "BOT-" + "".join(random.choices(ORDER_CODE_ALPHABET, k=ORDER_CODE_LENGTH))


async def _make_unique_order_code(repo: Repository) -> str:
    """Уникальный среди не-отменённых заказов код комментария (с ретраем)."""
    for _ in range(32):
        code = _make_order_code()
        if not await repo.is_order_code_taken(code):
            return code
    return "BOT-" + uuid.uuid4().hex[:ORDER_CODE_LENGTH].upper()


async def ensure_pending_order(repo: Repository, user_id: int, days: int, price: int) -> KaspiOrder:
    """Возвращает единственный живой pending-заказ на тариф days.

    Старые pending отменяются в той же транзакции, что и создание нового.
    Купон здесь НЕ сжигается — он сгорает только при подтверждении в _grant_order.
    """
    async with _order_lock():
        pending = await repo.get_pending_order(user_id)
        if pending is not None and pending.plan_days == days:
            return pending
        coupon = await repo.get_active_coupon(user_id)
        discount = coupon.discount_pct if coupon is not None else 0
        coupon_id = coupon.id if coupon is not None else 0
        final = price - price * discount // 100
        order_code = await _make_unique_order_code(repo)
        return await repo.replace_pending_order(
            user_id, days, final, discount, coupon_id, order_code
        )


def _confirm_keyboard(order_id: int, photo_file_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить", callback_data=f"kaspi:confirm:{order_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить", callback_data=f"kaspi:reject:{order_id}"
                ),
            ]
        ]
    )


async def _grant_order(repo: Repository, order: KaspiOrder) -> Subscription | None:
    """Выдаёт подписку и сжигает купон для подтверждённого заказа (идемпотентно)."""
    confirmed = await repo.approve_order(order.id)
    if confirmed is None:
        return None
    subscription = await repo.grant_subscription(order.user_id, order.plan_days)
    if order.coupon_id > 0:
        coupon = await repo.get_active_coupon(order.user_id)
        if coupon is not None and coupon.id == order.coupon_id:
            await repo.mark_coupon_used(order.coupon_id, order.user_id)
    await track_event(repo, order.user_id, "kaspi_order_approved")
    logger.info("Kaspi-подписка выдана: user=%s days=%s order=%s", order.user_id, order.plan_days, order.id)
    return subscription


@router.callback_query(F.data.startswith("kaspi:pay:"))
async def cb_kaspi_pay(callback: CallbackQuery, repo: Repository, settings: Settings) -> None:
    await callback.answer()
    days_text = callback.data.removeprefix("kaspi:pay:")
    try:
        days = int(days_text)
    except ValueError:
        await callback.message.answer("❌ Некорректный тариф.")
        return
    plan = next((p for p in settings.subscription_plan_list if p[0] == days), None)
    if plan is None:
        await callback.message.answer("❌ Такого тарифа нет.")
        return
    user = await repo.get_or_create_user(
        callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )

    try:
        purchase = await ensure_pending_order(repo, user.id, days, plan[1])
    except Exception:
        logger.exception("Kaspi-ошибка при создании заказа: user=%s days=%s", user.id, days)
        await callback.message.answer(
            "❌ Не удалось создать заказ. Попробуй ещё раз или напиши: " + FALLBACK_DEVELOPER
        )
        return

    await track_event(repo, user.id, "kaspi_order_created", {"days": purchase.plan_days, "amount": purchase.amount})

    text = (
        f"💳 Оплати по Kaspi QR: <b>{purchase.amount}₸</b> за {purchase.plan_days} дн."
        + (f" (скидка {purchase.discount_pct}%)" if purchase.discount_pct else "")
        + "\n\n"
        + "📲 Открой Kaspi → Платежи → Перевод по QR и оплати эту сумму.\n"
        + f"💬 В комментарии к переводу укажи: <code>{purchase.order_code}</code>\n\n"
        + "После оплаты жми <b>«Я оплатил»</b> и пришли скриншот/чек — "
        + "проверим и активируем подписку."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Я оплатил", callback_data="kaspi:paid")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="kaspi:cancel")],
        ]
    )
    try:
        if settings.kaspi_qr_path:
            await callback.message.answer_photo(
                FSInputFile(settings.kaspi_qr_path),
                caption=text,
                reply_markup=keyboard,
            )
        else:
            await callback.message.answer(
                "🖼 <b>Вот QR для оплаты</b>\n\n" + text,
                reply_markup=keyboard,
            )
    except Exception:
        logger.exception("Ошибка показа QR: user=%s", user.id)
        await callback.message.answer(
            "❌ Не удалось показать QR. Попробуй позже или напиши: " + FALLBACK_DEVELOPER
        )
    logger.info("Kaspi-заказ создан: user=%s days=%s code=%s", user.id, days, purchase.order_code)


@router.callback_query(F.data == "kaspi:cancel")
async def cb_kaspi_cancel(callback: CallbackQuery, repo: Repository) -> None:
    await callback.answer()
    user = await repo.get_or_create_user(
        callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    purchase = await repo.get_pending_order(user.id)
    if purchase is None:
        await callback.message.edit_text("Активного заказа нет. Выбери тариф: /premium")
        return
    await repo.cancel_order(purchase.id)
    await callback.message.edit_text(
        "❌ Заказ отменён. Скидка-купон при этом не тратится — он сгорит только при "
        "подтверждённой оплате. Если передумаешь — загляни в /premium 😉"
    )
    logger.info("Kaspi-заказ отменён: user=%s order=%s", user.id, purchase.id)


@router.callback_query(F.data == "kaspi:paid")
async def cb_kaspi_paid(callback: CallbackQuery, repo: Repository) -> None:
    await callback.answer()
    user = await repo.get_or_create_user(
        callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    purchase = await repo.get_pending_order(user.id)
    if purchase is None:
        await callback.message.answer(
            "⚠️ Нет активного заказа. Нажми /premium и выбери тариф."
        )
        return
    if purchase.photo_file_id:
        await callback.message.answer(
            "✅ Чек уже получен! Скоро проверим и активируем подписку."
        )
        return
    await callback.message.answer(
        f"📷 Отлично! Оплачено {purchase.amount}₸ (комментарий {purchase.order_code}).\n"
        + "Пришли <b>скриншот или чек</b> из Kaspi как фото — проверим."
    )


@router.message(F.photo)
async def on_check_photo(message: Message, repo: Repository, settings: Settings) -> None:
    user = await repo.get_or_create_user(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    purchase = await repo.get_pending_order(user.id)
    if purchase is None:
        await message.answer(
            "📷 Фото получил, но активного заказа нет. Хочешь подписку? Нажми /premium"
        )
        return
    if purchase.photo_file_id:
        await message.answer("✅ Чек уже получен! Ждём проверки — подписка вот-вот активируется.")
        return

    photo_file_id = message.photo[-1].file_id
    await repo.attach_photo(purchase.id, photo_file_id)
    await track_event(repo, user.id, "kaspi_photo_submitted")
    await message.answer(
        f"✅ Чек получен ({purchase.amount}₸, {purchase.order_code}). "
        "Проверяем, обычно до 30 минут… Если задержка — напиши " + FALLBACK_DEVELOPER
    )

    if not settings.admin_tg_id:
        await message.answer(
            "⚠️ Админ пока не подключён (ADMIN_TG_ID). Напиши ему в личку: " + FALLBACK_DEVELOPER
        )
        return

    caption = (
        f"🧾 <b>Kaspi-чек</b> #{purchase.id}\n"
        f"👤 tg_id: {message.from_user.id}\n"
        f"📦 Подписка: {purchase.plan_days} дн. на {purchase.amount}₸"
        + (f" (скидка {purchase.discount_pct}%)" if purchase.discount_pct else "")
        + f"\n💬 Комментарий: <code>{purchase.order_code}</code>"
    )
    try:
        await message.bot.send_photo(
            settings.admin_tg_id,
            photo_file_id,
            caption=caption,
            reply_markup=_confirm_keyboard(purchase.id, photo_file_id),
        )
    except Exception:
        logger.exception("Не удалось переслать чек админу: order=%s", purchase.id)


@router.callback_query(F.data.startswith("kaspi:confirm:"))
async def cb_kaspi_confirm(callback: CallbackQuery, repo: Repository, settings: Settings) -> None:
    if callback.from_user.id != settings.admin_tg_id:
        await callback.answer("Только админ подтверждает оплаты.")
        return
    try:
        order_id = int(callback.data.removeprefix("kaspi:confirm:"))
    except ValueError:
        await callback.answer("Некорректный заказ.")
        return
    order = await repo.get_order(order_id)
    if order is None or order.status != KaspiOrder.STATUS_PENDING:
        await callback.answer("Заказ уже обработан.")
        return
    await _grant_order(repo, order)
    await callback.answer("Подписка выдана ✅")
    try:
        await callback.message.delete()
    except Exception:
        pass
    user = await repo.get_user(order.user_id)
    if user is not None:
        try:
            await callback.bot.send_message(
                user.tg_id,
                f"🎉 Оплата подтверждена! Подписка {order.plan_days} дн. активирована. Спасибо! 💛",
            )
        except Exception:
            logger.exception("Не удалось уведомить пользователя: order=%s", order.id)


@router.callback_query(F.data.startswith("kaspi:reject:"))
async def cb_kaspi_reject(callback: CallbackQuery, repo: Repository, settings: Settings) -> None:
    if callback.from_user.id != settings.admin_tg_id:
        await callback.answer("Только админ отклоняет оплаты.")
        return
    try:
        order_id = int(callback.data.removeprefix("kaspi:reject:"))
    except ValueError:
        await callback.answer("Некорректный заказ.")
        return
    order = await repo.get_order(order_id)
    if order is None or order.status != KaspiOrder.STATUS_PENDING:
        await callback.answer("Заказ уже обработан.")
        return
    await repo.cancel_order(order.id)
    await track_event(repo, order.user_id, "kaspi_order_rejected")
    await callback.answer("Оплата отклонена ❌")
    try:
        await callback.message.delete()
    except Exception:
        pass
    user = await repo.get_user(order.user_id)
    if user is not None:
        try:
            await callback.bot.send_message(
                user.tg_id,
                "❌ Чек не подошёл. Напиши разработчику: " + FALLBACK_DEVELOPER,
            )
        except Exception:
            logger.exception("Не удалось уведомить пользователя: order=%s", order.id)