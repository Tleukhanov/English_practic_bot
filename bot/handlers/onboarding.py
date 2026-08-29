"""Guided onboarding flow (Фаза 13).

Новый пользователь проходит 3 шага:
1. Выбор уровня (или быстрый старт)
2. Выбор интересов
3. Готово — первый урок
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery

from core.lessons import LessonService
from storage.repo import Repository, UserProfile

from .interests import ONBOARDING_INTEREST_BY_CODE, _format_interests, _parse_interests

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
        "Вот что я знаю о тебе. Подбираю темы для твоего первого урока..."
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
        await repo.set_level(user.id, level=code)
        logger.info("Onboarding: user=%s level=%s", user.id, code)
    await callback.message.edit_text(
        _interests_text(),
        reply_markup=_interests_keyboard(),
    )


@router.callback_query(F.data.startswith("onb:interest:"))
async def cb_onb_interest(
    callback: CallbackQuery,
    repo: Repository,
    lesson_service: LessonService,
) -> None:
    code = callback.data.split(":")[-1]
    if code == "done":
        await callback.answer()
        await callback.message.edit_text(_done_text())
        from bot.lessons import _start_lesson
        await _start_lesson(callback.message, repo, lesson_service, None, callback.from_user)
        return

    user = await repo.get_or_create_user(
        callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    profile = await repo.get_profile(user.id)
    if profile is None:
        profile = UserProfile(user_id=user.id)

    name = ONBOARDING_INTEREST_BY_CODE.get(code, code)
    selected = _parse_interests(profile.interests)
    if name not in selected:
        selected.add(name)
        profile.interests = _format_interests(selected)
        profile.updated_at = datetime.now(timezone.utc).isoformat()
        await repo.save_profile(profile)
        logger.info("Onboarding: user=%s interest=%s", user.id, name)
        await callback.answer("✅ Добавлено!", show_alert=False)
    else:
        await callback.answer("Уже выбрано", show_alert=False)
