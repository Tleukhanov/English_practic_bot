"""Инлайн-клавиатуры."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📚 Начать урок", callback_data="lesson_start")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
            [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")],
        ]
    )


def lesson_keyboard() -> InlineKeyboardMarkup:
    """Кнопки навигации по уроку."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➡️ Дальше", callback_data="lesson:next")],
            [
                InlineKeyboardButton(text="🔁 Повторить", callback_data="lesson:repeat"),
                InlineKeyboardButton(text="⏹️ Завершить", callback_data="lesson:end"),
            ],
        ]
    )
