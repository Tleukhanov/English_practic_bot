"""Фаза 12 — Игровые элементы: достижения, уровни, челленджи.

Достижения выдаются за milestone-ы: первый урок, серия дней, точность и т.д.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.progress import ProgressData, ProgressService
from storage.repo import Repository


@dataclass
class Achievement:
    """Одно достижение."""

    id: str
    name: str
    emoji: str
    description: str
    condition: str  # human-readable
    earned: bool = False


ACHIEVEMENTS_LIST: list[dict] = [
    {"id": "first_lesson", "name": "Первый шаг", "emoji": "👶", "description": "Завершил первый урок", "condition": "lessons >= 1"},
    {"id": "five_lessons", "name": "Пять уроков", "emoji": "📚", "description": "Завершил 5 уроков", "condition": "lessons >= 5"},
    {"id": "ten_lessons", "name": "Десять уроков", "emoji": "🏆", "description": "Завершил 10 уроков", "condition": "lessons >= 10"},
    {"id": "twenty_lessons", "name": "Мастер уроков", "emoji": "🎓", "description": "Завершил 20 уроков", "condition": "lessons >= 20"},
    {"id": "first_correct", "name": "Безупречно", "emoji": "✅", "description": "Первая идеальная фраза", "condition": "correct >= 1"},
    {"id": "fifty_turns", "name": "50 реплик", "emoji": "💬", "description": "Написал 50 фраз на английском", "condition": "turns >= 50"},
    {"id": "hundred_turns", "name": "Сотня!", "emoji": "💯", "description": "Написал 100 фраз", "condition": "turns >= 100"},
    {"id": "streak_3", "name": "Три дня подряд", "emoji": "🔥", "description": "Занимался 3 дня подряд", "condition": "streak >= 3"},
    {"id": "streak_7", "name": "Неделя без перерыва", "emoji": "🌟", "description": "7 дней подряд", "condition": "streak >= 7"},
    {"id": "streak_14", "name": "Две недели", "emoji": "💎", "description": "14 дней подряд", "condition": "streak >= 14"},
    {"id": "accuracy_80", "name": "Точный стрелок", "emoji": "🎯", "description": "Точность 80%+ (минимум 20 реплик)", "condition": "accuracy >= 80 and turns >= 20"},
    {"id": "accuracy_95", "name": "Грамматический гений", "emoji": "🧠", "description": "Точность 95%+ (минимум 30 реплик)", "condition": "accuracy >= 95 and turns >= 30"},
    {"id": "xp_100", "name": "100 XP", "emoji": "⭐", "description": "Набрал 100 XP", "condition": "xp >= 100"},
    {"id": "xp_500", "name": "500 XP", "emoji": "🌠", "description": "Набрал 500 XP", "condition": "xp >= 500"},
    {"id": "xp_1000", "name": "Тысячник", "emoji": "🏅", "description": "Набрал 1000 XP", "condition": "xp >= 1000"},
]

LEVEL_THRESHOLDS = [
    (0, "Новичок", "🌱"),
    (50, "Ученик", "📗"),
    (150, "Подмастерье", "📘"),
    (300, "Знаток", "📙"),
    (500, "Мастер", "📕"),
    (800, "Эксперт", "🏆"),
    (1200, "Гуру", "👑"),
    (2000, "Легенда", "💎"),
]


def get_level_for_xp(xp: int) -> tuple[str, str]:
    """Возвращает (название уровня, эмодзи) по XP."""
    current_level = LEVEL_THRESHOLDS[0]
    for threshold, name, emoji in LEVEL_THRESHOLDS:
        if xp >= threshold:
            current_level = (threshold, name, emoji)
    return current_level[1], current_level[2]


def get_next_level(xp: int) -> tuple[str, int] | None:
    """Возвращает (название следующего уровня, сколько XP нужно)."""
    for threshold, name, emoji in LEVEL_THRESHOLDS:
        if xp < threshold:
            return name, threshold - xp
    return None, 0


def check_achievements(p: ProgressData) -> list[Achievement]:
    """Проверяет все достижения и возвращает список с earned=True/False."""
    achievements = []
    for ach_def in ACHIEVEMENTS_LIST:
        earned = _check_condition(ach_def["condition"], p)
        achievements.append(Achievement(
            id=ach_def["id"],
            name=ach_def["name"],
            emoji=ach_def["emoji"],
            description=ach_def["description"],
            condition=ach_def["condition"],
            earned=earned,
        ))
    return achievements


def _check_condition(condition: str, p: ProgressData) -> bool:
    """Простой eval для condition строк."""
    ctx = {
        "lessons": p.total_lessons,
        "correct": p.correct,
        "turns": p.total_turns,
        "streak": p.streak_days,
        "accuracy": p.accuracy,
        "xp": p.xp,
    }
    try:
        return bool(eval(condition, {"__builtins__": {}}, ctx))
    except Exception:
        return False


def format_achievements(achievements: list[Achievement], p: ProgressData) -> str:
    """Форматирует достижения в сообщение."""
    level_name, level_emoji = get_level_for_xp(p.xp)
    next_level, xp_needed = get_next_level(p.xp)

    lines = [f"🎮 <b>Достижения</b>  {level_emoji} {level_name}", ""]

    if next_level:
        lines.append(f"⭐ XP: {p.xp}  →  {next_level} ({xp_needed} XP)")
    else:
        lines.append(f"⭐ XP: {p.xp}  — максимальный уровень!")
    lines.append("")

    earned = [a for a in achievements if a.earned]
    unearned = [a for a in achievements if not a.earned]

    if earned:
        lines.append("✅ <b>Получены:</b>")
        for a in earned:
            lines.append(f"  {a.emoji} {a.name} — {a.description}")
        lines.append("")

    if unearned:
        lines.append("🔒 <b>Ещё не получены:</b>")
        for a in unearned:
            lines.append(f"  {a.emoji} {a.name} — {a.description}")

    return "\n".join(lines)
