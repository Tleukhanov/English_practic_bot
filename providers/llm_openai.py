"""Универсальный LLM-адаптер поверх OpenAI-совместимого API.

Один класс закрывает DeepSeek, OpenAI, Ollama, Groq, Mistral, Gemini, OpenRouter —
провайдер задаётся только через base_url/api_key/model в .env.
"""

from openai import AsyncOpenAI

from .base import LLMProvider


class OpenAIChatProvider(LLMProvider):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        default_temperature: float = 0.3,
    ):
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self._model = model
        self._temperature = default_temperature

    async def chat(self, messages: list[dict[str, str]], temperature: float | None = None) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature if temperature is not None else self._temperature,
        )
        content = response.choices[0].message.content
        return (content or "").strip()
