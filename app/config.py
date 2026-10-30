"""Application Configuration Module.

Loads and validates environment variables using Pydantic Settings.
"""

from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application runtime settings."""

    # App meta
    APP_NAME: str = "Sanaa AI Service"
    APP_ENV: Literal["development", "production", "testing"] = "development"
    DEBUG: bool = True
    PORT: int = 8000

    # LLM Settings
    LLM_PROVIDER: str = "gemini"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-flash-lite-latest"

    # Chat & Safety
    MAX_HISTORY_TURNS: int = 10
    SAFETY_STRICT_MODE: bool = True

    # Emergency Contacts Configuration
    DEFAULT_REGION: str = "EG"
    # Verified official emergency contact hotlines by region
    VERIFIED_EMERGENCY_NUMBERS: dict = {
        "EG": {
            "GAS": "129",               # طوارئ الغاز الطبيعي
            "ELECTRICITY": "121",       # طوارئ الكهرباء
            "FIRE": "180",              # المطافئ والدفاع المدني
            "AMBULANCE": "123",         # هيئة الإسعاف المصرية
        },
        "INTERNATIONAL": {
            "GAS": "local gas authority",
            "ELECTRICITY": "local electric utility emergency",
            "FIRE": "local fire department",
            "AMBULANCE": "local medical emergency",
        },
    }

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance to avoid re-reading disk on every request."""
    return Settings()
