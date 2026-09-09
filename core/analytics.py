"""Лёгкая аналитика: таблица событий и сборка админ-статистики.

Аналитика никогда не должна ломать основной сценарий, поэтому вызовы
``track_event`` принято использовать как есть — ошибки внутри глотаются.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from storage.repo import Repository


class EventTracker:
    def __init__(self, repo: Repository):
        self._repo = repo

    async def track(self, user_id: int, event_type: str, payload=None) -> None:
        await self._repo.append_event(user_id, event_type, payload)


async def track_event(repo: Repository, user_id: int, event_type: str, payload=None) -> None:
    """Записывает событие; любые ошибки аналитики не должны мешать основному потоку."""
    try:
        await EventTracker(repo).track(user_id, event_type, payload)
    except Exception:
        pass


def format_admin_stats(pending_orders: int, revenue: int, active_subs: int, spins_today: int) -> str:
    return "\n".join(
        [
            "⚙️ Админ-статистика",
            "",
            f"🧾 Заявок на подтверждение: {pending_orders}",
            f"💰 Выручка (подтверждённые): {revenue}₸",
            f"👤 Активных подписок: {active_subs}",
            f"🎡 Круток сегодня: {spins_today}",
        ]
    )