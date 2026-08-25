"""Команды /start и /help."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from storage.repo import Repository

from ..keyboards import main_menu

router = Router()

WELCOME_TEXT = """Привет, {name}! 👋

Я — твой репетитор английского по переписке.

✍️ Пиши или 🎤 говори по-английски — я проверю твою фразу, укажу на ошибки и объясню, как их исправить, а потом продолжу диалог.

🎯 <b>Начни с диагностики уровня</b> (кнопка «Определить уровень») — тогда уроки будут подобраны под тебя.

Пример:
Ты: <i>I go to school yesterday</i>
Я: ❌ Есть ошибка!
   • Грамматика: использовано Present Simple для прошлого времени
   Правильно: <i>went</i>
   📝 Исправленный вариант: <i>I went to school yesterday.</i>

Начнём? Просто напиши первую фразу!"""

HELP_TEXT = """ℹ️ <b>Как пользоваться:</b>

📚 <b>Структурированный урок</b> — /lesson (или кнопка в меню): слова, ключевые идеи, грамматика и задания по одной теме.

🎯 <b>Диагностика уровня</b> — /diagnostic: короткие задания, после которых я определю твой уровень (A1–C1) и буду подстраивать уроки под тебя.

✍️ Отправь текст на английском — проверю и объясню ошибки.
🎤 Отправь голосовое сообщение — распознаю, проверю и отвечу голосом.

📊 <b>Статистика</b> — /stats или кнопка в меню: уровень, количество реплик, точность, частые ошибки.

🧠 <b>Мой профиль</b> — /profile: что я запомнил о тебе (цель, интересы, слабые места). Профиль заполняется сам по ходу практики.

💡 Совет: старайся говорить полными предложениями, так тренировка полезнее."""

RETENTION_COMEBACK = (
    "👋 С возвращением, {name}!\n\n"
    "⏰ Ты не занимался уже {hours}ч.\n"
    "{weak_line}"
    "{streak_line}\n\n"
    "Хочешь продолжить?"
)

RETENTION_NO_WEAK = (
    "👋 С возвращением, {name}!\n\n"
    "⏰ Ты не занимался уже {hours}ч.\n"
    "{streak_line}\n\n"
    "Готов к новому уроку?"
)


def _build_retention_message(name: str, info) -> str | None:
    """Формирует персонализированное приветствие на основе retention данных."""
    if info.total_lessons == 0 or info.last_practice_hours is None:
        return None

    if info.last_practice_hours < 24:
        return None

    weak_line = ""
    if info.weak_areas:
        weak_line = "📝 Твои слабые темы: " + ", ".join(info.weak_areas[:3]) + ". "

    streak_line = ""
    if info.streak_days > 1:
        streak_line = f"🔥 Серия: {info.streak_days} дней подряд!"

    if info.weak_areas:
        return RETENTION_COMEBACK.format(
            name=name,
            hours=info.last_practice_hours,
            weak_line=weak_line,
            streak_line=streak_line,
        )
    else:
        return RETENTION_NO_WEAK.format(
            name=name,
            hours=info.last_practice_hours,
            streak_line=streak_line,
        )


@router.message(CommandStart())
async def cmd_start(message: Message, repo: Repository) -> None:
    from core.retention import RetentionService

    await repo.get_or_create_user(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    await repo.abort_active_lessons(message.from_user.id)
    await repo.abort_active_diagnostics(message.from_user.id)

    name = message.from_user.first_name or "друг"

    retention_service = RetentionService(repo)
    info = await retention_service.get_retention_info(message.from_user.id)
    greeting = _build_retention_message(name, info)

    if greeting:
        await message.answer(greeting, reply_markup=main_menu())
    else:
        await message.answer(WELCOME_TEXT.format(name=name), reply_markup=main_menu())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=main_menu())


@router.message(Command("reset"))
async def cmd_reset(message: Message, repo: Repository) -> None:
    await repo.abort_active_lessons(message.from_user.id)
    await repo.abort_active_diagnostics(message.from_user.id)
    await message.answer("🔄 Состояние сброшено. Можешь начать заново!", reply_markup=main_menu())


@router.callback_query(F.data == "reset")
async def cb_reset(callback: CallbackQuery, repo: Repository) -> None:
    await repo.abort_active_lessons(callback.from_user.id)
    await repo.abort_active_diagnostics(callback.from_user.id)
    await callback.answer("🔄 Сброшено")
    await callback.message.answer("🔄 Состояние сброшено. Можешь начать заново!", reply_markup=main_menu())
