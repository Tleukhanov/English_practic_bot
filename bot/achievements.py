"""Анонс достижений: показывает только НОВЫЕ, не повторяет уже показанные.

Достижения считаются из живой статистики (монотонны), поэтому повторный показ
всех заработанных превращается в спам. Здесь мы ведём таблицу user_achievements —
какие достижения уже были показаны, и объявляем только прирост.
"""

from __future__ import annotations

import logging

from storage.repo import Repository

logger = logging.getLogger(__name__)


async def announce_new_achievements(target, user, repo: Repository, *, reply_markup) -> None:
    """Сообщает только о новых достижениях. Молча возвращается, если их нет."""
    from core.achievements import check_achievements
    from core.progress import ProgressService

    progress_svc = ProgressService(repo)
    progress = await progress_svc.get_progress(user.id, level=user.level)
    achievements = check_achievements(progress)
    earned = [a for a in achievements if a.earned]
    if not earned:
        return

    shown = await repo.get_shown_achievements(user.id)
    if not shown:
        # Пользователь, который занимался до появления этой механики, не должен
        # получать вал уведомлений за старые достижения — помечаем их показанными.
        stats = await repo.get_stats(user.id)
        notes = await repo.get_lesson_notes(user.id, limit=20)
        if stats.total_turns >= 50 or len(notes) >= 5:
            await repo.save_shown_achievements(user.id, [a.id for a in earned])
            return

    shown_set = set(shown)
    new = [a for a in earned if a.id not in shown_set]
    if not new:
        return

    await repo.save_shown_achievements(user.id, [a.id for a in earned])
    text = "\n".join(f"{a.emoji} {a.name}" for a in new)
    try:
        await target.answer(f"<b>Новые достижения!</b>\n\n{text}", reply_markup=reply_markup)
        logger.info("Достижения показаны: user=%s new=%s", user.id, [a.id for a in new])
    except Exception:
        logger.exception("Не удалось показать достижения user=%s", user.id)