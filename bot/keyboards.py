"""Инлайн-клавиатуры."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📚 Начать урок", callback_data="lesson_start")],
            [InlineKeyboardButton(text="🎯 Определить уровень", callback_data="diagnostic_start")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
            [InlineKeyboardButton(text="🧠 Мой профиль", callback_data="profile")],
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


def diagnostic_keyboard() -> InlineKeyboardMarkup:
    """Кнопки диагностики: пропустить задание или завершить досрочно."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⏭️ Пропустить", callback_data="diagnostic:skip"),
                InlineKeyboardButton(text="⏹️ Завершить досрочно", callback_data="diagnostic:end"),
            ]
        ]
    )


def reveal_keyboard() -> InlineKeyboardMarkup:
    """Кнопка «Показать ошибку» — мягкий фидбек вместо вываливания всех ошибок сразу."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Показать ошибку", callback_data="practice:reveal")],
        ]
    )
