"""Троттлинг LLM-действий (защита от флуда и стоимости API).

Минус: лимит действий на пользователя за окно + минимальная пауза
между действиями. Действия = текстовая/голосовая практика, /lesson,
/diagnostic. Обычные команды (/start, /help...) не троттлятся.
"""

from __future__ import annotations

import time

from aiogram import BaseMiddleware
from aiogram.types import Message

LLM_TRIGGER_COMMANDS = ("/lesson", "/diagnostic")


class LLMThrottle(BaseMiddleware):
    """Middleware на Message: ограничивает поток LLM-действий на юзера."""

    def __init__(self, window_sec: float = 60.0, limit: int = 8, min_interval: float = 3.0):
        self.window_sec = window_sec
        self.limit = limit
        self.min_interval = min_interval
        # user_id -> список timestamps разрешённых действий (monotonic)
        self._actions: dict[int, list[float]] = {}
        self._last_warned: dict[int, float] = {}

    def _is_llm_action(self, event: Message) -> bool:
        text = (event.text or "").lstrip().lower()
        if event.voice:
            return True
        if text in ("", "/start", "/help", "/reset", "/stats", "/profile", "/menu"):
            return False
        if text.startswith("/"):
            return text.startswith(LLM_TRIGGER_COMMANDS)
        return True

    def _allow(self, user_id: int) -> bool:
        now = time.monotonic()
        stamps = self._actions.setdefault(user_id, [])
        cutoff = now - self.window_sec
        stamps[:] = [s for s in stamps if s > cutoff]

        if stamps and now - stamps[-1] < self.min_interval:
            return False
        if len(stamps) >= self.limit:
            return False

        stamps.append(now)
        return True

    async def __call__(self, handler, event: Message, data: dict) -> None:
        if event.from_user is None or event.from_user.id is None:
            return await handler(event, data)
        if not self._is_llm_action(event):
            return await handler(event, data)

        user_id = event.from_user.id
        if not self._allow(user_id):
            now = time.monotonic()
            last = self._last_warned.get(user_id, 0.0)
            if now - last >= self.window_sec:
                self._last_warned[user_id] = now
                await event.answer("⏳ Не так быстро! Дай ИИ обдумать предыдущий ответ…")
            return

        return await handler(event, data)