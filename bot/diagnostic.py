"""Диагностика уровня (Фаза 3): /diagnostic, ответы на задания, оценка уровня.

Пользователь проходит «лестницу» заданий текстом или голосом, после последнего
ответа (или досрочного завершения) бот определяет уровень CEFR и сохраняет его.
"""

from __future__ import annotations

import json
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from core.diagnostic import (
    DiagnosticAssessment,
    DiagnosticService,
    diagnostic_tasks_from_json,
    diagnostic_tasks_to_json,
    estimate_level_heuristic,
)
from storage.repo import Repository

from .flow import get_or_create_user
from .formatters import format_diagnostic_question, format_level_result
from .keyboards import diagnostic_keyboard, main_menu
from .quota import QUOTA_EXCEEDED_TEXT, QuotaExceeded, QuotaGuard

router = Router()
logger = logging.getLogger(__name__)


def _answers_of(session) -> list[str]:
    if not session.answers_json:
        return []
    try:
        parsed = json.loads(session.answers_json)
    except (json.JSONDecodeError, TypeError):
        return []
    return [str(a) for a in parsed] if isinstance(parsed, list) else []


async def _assess_and_finish(
    target: Message,
    repo: Repository,
    diagnostic_service: DiagnosticService,
    session,
    quota: QuotaGuard | None = None,
) -> None:
    """Оценивает уровень по ответам, сохраняет его и закрывает сессию диагностики."""
    questions = diagnostic_tasks_from_json(session.questions_json)
    answers = _answers_of(session)
    if quota is not None:
        try:
            await quota.consume(session.user_id)
        except QuotaExceeded:
            assessment = DiagnosticAssessment(level=estimate_level_heuristic(answers))
            await repo.set_level(session.user_id, assessment.level)
            await repo.finish_diagnostic(session.id)
            await target.answer(format_level_result(assessment, estimated=True), reply_markup=main_menu())
            logger.info("Уровень оценён эвристикой (лимит LLM): user=%s level=%s", session.user_id, assessment.level)
            return
    try:
        assessment = await diagnostic_service.assess(questions, answers)
        estimated = False
    except Exception as exc:
        logger.exception("Ошибка оценки уровня: %s", exc)
        assessment = DiagnosticAssessment(level=estimate_level_heuristic(answers))
        estimated = True
    await repo.set_level(session.user_id, assessment.level)
    await repo.finish_diagnostic(session.id)
    await target.answer(format_level_result(assessment, estimated=estimated), reply_markup=main_menu())
    logger.info("Уровень определён: user=%s level=%s", session.user_id, assessment.level)


async def _show_next_task(target, repo: Repository, session) -> None:
    questions = diagnostic_tasks_from_json(session.questions_json)
    answers = _answers_of(session)
    if len(answers) >= len(questions):
        return
    task = questions[len(answers)]
    await target.answer(
        format_diagnostic_question(task, len(answers) + 1, len(questions)),
        reply_markup=diagnostic_keyboard(),
    )


async def process_diagnostic_answer(
    message: Message,
    repo: Repository,
    diagnostic_service: DiagnosticService,
    text: str,
    quota: QuotaGuard | None = None,
) -> bool:
    """Отвечает на задание диагностики, если она активна. True — сообщение ушло в диагностику."""
    user = await get_or_create_user(message, repo)
    session = await repo.get_active_diagnostic(user.id)
    if session is None:
        return False

    if session.updated_at:
        from datetime import datetime, timezone
        try:
            updated = datetime.fromisoformat(session.updated_at.replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - updated).total_seconds() / 3600
            if age_hours > 1:
                await repo.abort_active_diagnostics(user.id)
                await message.answer(
                    "⏰ Диагностика устарела (прошло больше часа) и была завершена.\n"
                    "Начни заново: /diagnostic",
                )
                return True
        except (ValueError, TypeError):
            pass

    await repo.append_diagnostic_answer(session.id, text)
    questions = diagnostic_tasks_from_json(session.questions_json)
    answers = _answers_of(session)
    if len(answers) >= len(questions):
        await _assess_and_finish(message, repo, diagnostic_service, session, quota=quota)
        return True

    await _show_next_task(message, repo, session)
    return True


async def _start_diagnostic(target, repo: Repository, diagnostic_service: DiagnosticService, user_from, quota: QuotaGuard | None = None) -> None:
    user = await repo.get_or_create_user(
        user_from.id,
        username=user_from.username,
        first_name=user_from.first_name,
    )
    if await repo.get_active_diagnostic(user.id):
        await target.answer(
            "🎯 Диагностика уже идёт! Ответь на текущее задание или нажми «⏹️ Завершить досрочно»."
        )
        return
    if await repo.get_active_lesson(user.id):
        await target.answer(
            "📚 Сначала закончи текущий урок (жми «➡️ Дальше» до конца или «⏹️ Завершить»), "
            "затем пройди диагностику: /diagnostic"
        )
        return

    if quota is not None:
        try:
            await quota.consume(user.id)
        except QuotaExceeded:
            await target.answer(QUOTA_EXCEEDED_TEXT)
            return

    status = await target.answer("⏳ Составляю диагностические задания...")
    try:
        tasks = await diagnostic_service.generate_tasks()
    except Exception as exc:
        logger.exception("Ошибка генерации заданий диагностики: %s", exc)
        await status.edit_text("⚠️ Не удалось составить задания. Проверь LLM_API_KEY в .env и попробуй ещё раз.")
        return
    if not tasks:
        await status.edit_text("🤔 Не удалось составить задания. Попробуй ещё раз.")
        return

    session = await repo.start_diagnostic(user.id, diagnostic_tasks_to_json(tasks))
    await status.edit_text(
        format_diagnostic_question(tasks[0], 1, len(tasks)),
        reply_markup=diagnostic_keyboard(),
    )
    logger.info("Диагностика начата: user=%s session=%s", user.id, session.id)


@router.message(Command("diagnostic"))
async def cmd_diagnostic(message: Message, repo: Repository, diagnostic_service: DiagnosticService, quota: QuotaGuard | None = None) -> None:
    await _start_diagnostic(message, repo, diagnostic_service, message.from_user, quota)


@router.callback_query(F.data == "diagnostic_start")
async def cb_diagnostic_start(callback: CallbackQuery, repo: Repository, diagnostic_service: DiagnosticService, quota: QuotaGuard | None = None) -> None:
    await callback.answer()
    await _start_diagnostic(callback.message, repo, diagnostic_service, callback.from_user, quota)


@router.callback_query(F.data == "diagnostic:skip")
async def cb_diagnostic_skip(
    callback: CallbackQuery,
    repo: Repository,
    diagnostic_service: DiagnosticService,
    quota: QuotaGuard | None = None,
) -> None:
    user = await repo.get_or_create_user(
        callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    session = await repo.get_active_diagnostic(user.id)
    if session is None:
        await callback.answer("Диагностика уже завершена")
        return
    await callback.answer()
    await repo.append_diagnostic_answer(session.id, "")
    questions = diagnostic_tasks_from_json(session.questions_json)
    answers = _answers_of(session)
    if len(answers) >= len(questions):
        await _assess_and_finish(callback.message, repo, diagnostic_service, session, quota=quota)
        return
    await _show_next_task(callback.message, repo, session)


@router.callback_query(F.data == "diagnostic:end")
async def cb_diagnostic_end(
    callback: CallbackQuery,
    repo: Repository,
    diagnostic_service: DiagnosticService,
    quota: QuotaGuard | None = None,
) -> None:
    user = await repo.get_or_create_user(
        callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    session = await repo.get_active_diagnostic(user.id)
    if session is None:
        await callback.answer("Диагностика уже завершена")
        return
    await callback.answer()
    if not any(a.strip() for a in _answers_of(session)):
        await repo.abort_active_diagnostics(user.id)
        await callback.message.edit_text(
            "⏹️ Диагностика отменена. Вернёшься, когда будешь готов: /diagnostic",
            reply_markup=main_menu(),
        )
        return
    await _assess_and_finish(callback.message, repo, diagnostic_service, session, quota=quota)
