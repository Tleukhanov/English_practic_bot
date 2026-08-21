"""Команда /character — выбор персонажа (Фаза 8)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from core.characters import get_character, list_characters
from storage.repo import Repository

router = Router()


def _character_list_text() -> str:
    lines = ["🎭 <b>Выбери персонажа:</b>\n"]
    for c in list_characters():
        lines.append(f"{c.emoji} <b>{c.name}</b> — {c.description}")
    return "\n".join(lines)


@router.message(Command("character"))
async def cmd_character(message: Message, repo: Repository) -> None:
    user = await repo.get_or_create_user(message.from_user.id)
    profile = await repo.get_profile(user.id)
    current = profile.character if profile else ""
    current_name = get_character(current).name if current else "Обычный учитель"

    buttons = []
    for c in list_characters():
        marker = " ✓" if c.id == current else ""
        buttons.append(
            [{"text": f"{c.emoji} {c.name}{marker}", "callback_data": f"character:set:{c.id}"}]
        )

    from aiogram.types import InlineKeyboardMarkup
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer(
        _character_list_text() + f"\n\nТекущий: <b>{current_name}</b>",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("character:set:"))
async def cb_set_character(callback: CallbackQuery, repo: Repository) -> None:
    character_id = callback.data.split(":")[-1]
    character = get_character(character_id)

    user = await repo.get_or_create_user(
        callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    profile = await repo.get_profile(user.id)
    if profile is None:
        from storage.repo import UserProfile
        profile = UserProfile(user_id=user.id)

    from datetime import datetime, timezone
    profile.character = character.id
    profile.updated_at = datetime.now(timezone.utc).isoformat()
    await repo.save_profile(profile)

    await callback.answer(f"{character.emoji} {character.name} выбран!")
    await callback.message.edit_text(
        f"{character.emoji} Персонаж: <b>{character.name}</b>\n\n{character.description}\n\n"
        f"Теперь все уроки и практика будут в этом стиле. Смени: /character"
    )
