"""Guided onboarding flow (Фаза 13).

Новый пользователь проходит 3 шага:
1. Выбор уровня (или быстрый старт)
2. Выбор интересов
3. Готово — первый урок
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from storage.repo import Repository

from ..keyboards import main_menu

router = Router()
logger = logging.getLogger(__name__)

LEVELS = [
    ("A1", "🌱 Beginner", "Совсем начинаю"),
    ("A2", "📗 Elementary", "Понимаю простые тексты"),
    ("B1", "📘 Intermediate", "Могу поддержать беседу"),
    ("B2", "📙 Upper-Intermediate", "Свободно читаю"),
    ("C1", "📕 Advanced", "Думаю на английском"),
]


def _level_keyboard():
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"onb:level:{code}")]
        for code, label, _ in LEVELS
    ]
    buttons.append([InlineKeyboardButton(text="⚡ Быстрый старт", callback_data="onb:level:skip")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _interests_keyboard():
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    interests = [
        ("💼 Работа и карьера", "career"),
        ("🎬 Фильмы и сериалы", "movies"),
        ("🎮 Игры", "games"),
        ("✈️ Путешествия", "travel"),
        ("💻 Технологии", "tech"),
        ("📚 Наука и образование", "science"),
        ("🎵 Музыка", "music"),
        ("⚽ Спорт", "sports"),
        ("🍳 Кулинария", "cooking"),
        ("🎨 Творчество", "art"),
    ]
    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"onb:interest:{code}")]
        for label, code in interests
    ]
    buttons.append([InlineKeyboardButton(text="✅ Готово", callback_data="onb:interest:done")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _welcome_text(user_name: str) -> str:
    return (
        f"👋 Привет, {user_name}!\n\n"
        "Я — твой AI репетитор английского.\n"
        "Давай настроим твоё обучение за 2 минуты!"
    )


def _level_text() -> str:
    return "🎯 Какой у тебя уровень английского?"


def _interests_text() -> str:
    return (
        "🎬 Какие темы тебе интересны?\n"
        "Выбери одну или несколько:"
    )


def _done_text() -> str:
    return (
        "🎉 Всё готово!\n\n"
        "Вот что я знаю о тебе. Теперь давай начнём!\n\n"
        "Нажми кнопку ниже, чтобы начать первый урок."
    )


@router.callback_query(F.data.startswith("onb:level:"))
async def cb_onb_level(callback: CallbackQuery, repo: Repository) -> None:
    await callback.answer()
    code = callback.data.split(":")[-1]
    user = await repo.get_or_create_user(
        callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    if code != "skip":
        await repo.upsert_user(user.id, level=code)
        logger.info("Onboarding: user=%s level=%s", user.id, code)
    await callback.message.edit_text(
        _interests_text(),
        reply_markup=_interests_keyboard(),
    )


@router.callback_query(F.data.startswith("onb:interest:"))
async def cb_onb_interest(callback: CallbackQuery, repo: Repository) -> None:
    await callback.answer()
    code = callback.data.split(":")[-1]
    if code == "done":
        await callback.message.edit_text(
            _done_text(),
            reply_markup=main_menu(),
        )
        return

    user = await repo.get_or_create_user(
        callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    profile = await repo.get_profile(user.id)
    current = profile.interests if profile else ""
    if code not in current:
        new_interests = f"{current},{code}".strip(",") if current else code
        if profile:
            profile.interests = new_interests
            await repo.save_profile(profile)
        logger.info("Onboarding: user=%s interest=%s", user.id, code)
    await callback.answer("✅ Добавлено!", show_alert=False)
