"""Команды /start и /help."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

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


@router.message(CommandStart())
async def cmd_start(message: Message, repo: Repository) -> None:
    await repo.get_or_create_user(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    name = message.from_user.first_name or "друг"
    await message.answer(WELCOME_TEXT.format(name=name), reply_markup=main_menu())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=main_menu())
