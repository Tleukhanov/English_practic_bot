"""Команда /interests — выбор интересов пользователя (Фаза 7).

Пользователь выбирает темы, которые ему интересны. Интересы влияют на
генерацию тем уроков и предложений.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from datetime import datetime, timezone

from ..keyboards import main_menu

from storage.repo import Repository, UserProfile

router = Router()

PREDEFINED_INTERESTS = [
    ("🎮", "Games"),
    ("🎵", "Music"),
    ("💻", "Programming / AI"),
    ("⚽", "Sports"),
    ("🎬", "Movies / Anime"),
    ("🍳", "Cooking"),
    ("✈️", "Travel"),
    ("📚", "Science"),
    ("🎨", "Art / Design"),
    ("💼", "Career"),
    ("🏋️", "Fitness"),
    ("🎲", "Board Games / Chess"),
    ("🐾", "Animals / Nature"),
]

# Коды интересов онбординга -> названия в словаре /interests.
# Онбординг не должен перезаписывать интересы, а только добавлять.
ONBOARDING_INTEREST_BY_CODE = {
    "career": "Career",
    "movies": "Movies / Anime",
    "games": "Games",
    "travel": "Travel",
    "tech": "Programming / AI",
    "science": "Science",
    "music": "Music",
    "sports": "Sports",
    "cooking": "Cooking",
    "art": "Art / Design",
}


def _parse_interests(raw: str) -> set[str]:
    if not raw:
        return set()
    return {i.strip() for i in raw.split(",") if i.strip()}


def _format_interests(interests: set[str]) -> str:
    return ", ".join(sorted(interests)) if interests else ""


def _interests_keyboard(current: str) -> InlineKeyboardMarkup:
    selected = _parse_interests(current)
    buttons = []
    for emoji, name in PREDEFINED_INTERESTS:
        marker = " ✅" if name in selected else ""
        buttons.append([
            InlineKeyboardButton(
                text=f"{emoji} {name}{marker}",
                callback_data=f"interests:toggle:{name}",
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="✅ Готово", callback_data="interests:done"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("interests"))
async def cmd_interests(message: Message, repo: Repository) -> None:
    user = await repo.get_or_create_user(message.from_user.id)
    profile = await repo.get_profile(user.id)
    current = _format_interests(_parse_interests(profile.interests if profile else ""))

    text = (
        "🎯 <b>Выбери свои интересы:</b>\n\n"
        "Нажми на тему, чтобы включить/выключить. "
        "Уроки будут строиться вокруг выбранных тем.\n\n"
    )
    if current:
        text += f"Сейчас выбрано: <b>{current}</b>"
    else:
        text += "<i>Пока ничего не выбрано</i>"

    await message.answer(text, reply_markup=_interests_keyboard(current))


@router.callback_query(F.data.startswith("interests:toggle:"))
async def cb_toggle_interest(callback: CallbackQuery, repo: Repository) -> None:
    interest_name = callback.data.split(":", 2)[-1]
    user = await repo.get_or_create_user(
        callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    profile = await repo.get_profile(user.id)
    if profile is None:
        profile = UserProfile(user_id=user.id)

    selected = _parse_interests(profile.interests)
    if interest_name in selected:
        selected.discard(interest_name)
    else:
        selected.add(interest_name)

    profile.interests = _format_interests(selected)
    profile.updated_at = datetime.now(timezone.utc).isoformat()
    await repo.save_profile(profile)

    await callback.answer(f"{'✅' if interest_name in selected else '❌'} {interest_name}")
    await callback.message.edit_reply_markup(reply_markup=_interests_keyboard(profile.interests))


@router.callback_query(F.data == "interests:done")
async def cb_interests_done(callback: CallbackQuery, repo: Repository) -> None:
    user = await repo.get_or_create_user(
        callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    profile = await repo.get_profile(user.id)
    current = _format_interests(_parse_interests(profile.interests if profile else ""))

    if current:
        text = f"🎯 Интересы сохранены: <b>{current}</b>\n\nТеперь уроки будут строиться вокруг этих тем."
    else:
        text = "Интересы очищены. Уроки будут на общие темы."

    await callback.answer()
    await callback.message.edit_text(text, reply_markup=main_menu())
