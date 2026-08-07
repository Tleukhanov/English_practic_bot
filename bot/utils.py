"""Вспомогательные функции для бота."""

from __future__ import annotations

import html


def escape(text: object) -> str:
    return html.escape(str(text), quote=False)


def is_mostly_cyrillic(text: str) -> bool:
    """True, если текст в основном на кириллице (значит, не английский)."""
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return False
    cyrillic = sum(1 for ch in letters if "\u0400" <= ch <= "\u04FF")
    return cyrillic / len(letters) > 0.5
