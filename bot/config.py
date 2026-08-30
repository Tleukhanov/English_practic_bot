"""Конфигурация проекта через .env (pydantic-settings)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

LLM_PRESETS: dict[str, dict[str, str]] = {
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    "ollama": {"base_url": "http://localhost:11434/v1", "model": "gemma2:2b"},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "model": "llama-3.3-70b-versatile"},
    "mistral": {"base_url": "https://api.mistral.ai/v1", "model": "mistral-small-latest"},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/", "model": "gemini-2.0-flash"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "model": "deepseek/deepseek-chat"},
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str = ""

    llm_provider: str = "deepseek"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_temperature: float = 0.3

    stt_provider: str = "faster-whisper"
    stt_model: str = "small"
    stt_api_key: str = ""

    tts_provider: str = "edge-tts"
    tts_voice: str = "en-US-JennyNeural"

    database_path: str = "data/english_bot.db"

    max_context_messages: int = 6
    max_voice_duration_sec: int = 60

    # Квота LLM на тестеров: дневной лимит LLM-действий на пользователя
    # (0 = без лимита). Промокод снимает лимит пользователю навсегда.
    llm_daily_limit: int = 30
    promo_unlimited_code: str = ""

    @property
    def resolved_llm_base_url(self) -> str:
        preset = LLM_PRESETS.get(self.llm_provider, {})
        return self.llm_base_url or preset.get("base_url", "")

    @property
    def resolved_llm_model(self) -> str:
        preset = LLM_PRESETS.get(self.llm_provider, {})
        return self.llm_model or preset.get("model", "")

    @property
    def llm_configured(self) -> bool:
        return bool(self.resolved_llm_base_url)

    @property
    def llm_ready(self) -> bool:
        """Всё есть для вызова LLM: провайдер известен, ключ не требуется для локальных."""
        if not self.resolved_llm_base_url:
            return False
        if self.llm_provider == "ollama":
            return True
        return bool(self.llm_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
