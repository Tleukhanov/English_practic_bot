"""Общая утилита: извлечение JSON-объекта из ответа LLM."""

from __future__ import annotations

import json
import re


class JsonParseError(ValueError):
    """Ответ LLM не удалось разобрать как JSON."""


def extract_json(text: str) -> dict:
    """Достаёт JSON-объект из ответа LLM, переживая ```json-обёртки и лишний текст."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise JsonParseError(f"В ответе LLM нет JSON-объекта: {text[:200]!r}")
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise JsonParseError(f"Невалидный JSON от LLM: {exc}") from exc
