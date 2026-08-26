"""Инлайн-клавиатуры."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📚 Начать урок", callback_data="lesson_start")],
            [InlineKeyboardButton(text="📖 Повторить слова", callback_data="review:start")],
            [InlineKeyboardButton(text="🎯 Определить уровень", callback_data="diagnostic_start")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
            [
                InlineKeyboardButton(text="📈 Прогресс", callback_data="progress"),
                InlineKeyboardButton(text="🏆 Достижения", callback_data="achievements"),
                InlineKeyboardButton(text="🏅 Рейтинг", callback_data="leaderboard"),
            ],
            [InlineKeyboardButton(text="🧠 Мой профиль", callback_data="profile")],
            [InlineKeyboardButton(text="🔄 Сброс", callback_data="reset")],
            [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")],
        ]
    )


def main_menu_with_srs(due_words: int = 0) -> InlineKeyboardMarkup:
    """Главное меню с указанием количества слов для повторения."""
    review_text = f"📖 Повторить слова ({due_words})" if due_words > 0 else "📖 Повторить слова"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📚 Начать урок", callback_data="lesson_start")],
            [InlineKeyboardButton(text=review_text, callback_data="review:start")],
            [InlineKeyboardButton(text="🎯 Определить уровень", callback_data="diagnostic_start")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
            [
                InlineKeyboardButton(text="📈 Прогресс", callback_data="progress"),
                InlineKeyboardButton(text="🏆 Достижения", callback_data="achievements"),
                InlineKeyboardButton(text="🏅 Рейтинг", callback_data="leaderboard"),
            ],
            [InlineKeyboardButton(text="🧠 Мой профиль", callback_data="profile")],
            [InlineKeyboardButton(text="🔄 Сброс", callback_data="reset")],
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


def lesson_recap_keyboard() -> InlineKeyboardMarkup:
    """Кнопки на финальном шаге recap — только завершить."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔁 Повторить", callback_data="lesson:repeat")],
            [InlineKeyboardButton(text="🎓 Завершить урок", callback_data="lesson:end")],
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


def topic_proposals_keyboard(proposals: list[dict]) -> InlineKeyboardMarkup:
    """Кнопки выбора темы из предложений (Фаза 2)."""
    buttons = []
    for i, p in enumerate(proposals):
        topic = p["topic"]
        desc = p["description"]
        label = f"📚 {topic} — {desc}" if desc else f"📚 {topic}"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"lesson:select_topic:{i}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
