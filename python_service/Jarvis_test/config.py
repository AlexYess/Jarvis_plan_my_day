"""
Centralized configuration. All env-tunable parameters live here.
Defaults are set for local development; override via environment in production.

Usage:
    from config import settings
    print(settings.database_url)
"""

import os
from dotenv import load_dotenv

# Loads .env if present (for local development).
# In production, set real env vars and skip .env.
load_dotenv()


class Settings:
    # --- Database ---
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_NAME: str = os.getenv("DB_NAME", "postgres")
    DB_USER: str = os.getenv("DB_USER", "postgres")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "postgres")

    @property
    def database_url(self) -> str:
        """psycopg/SQLAlchemy URL."""
        return (
            f"postgresql+psycopg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def database_dsn(self) -> str:
        """Plain DSN for psycopg pool."""
        return (
            f"host={self.DB_HOST} port={self.DB_PORT} "
            f"dbname={self.DB_NAME} user={self.DB_USER} "
            f"password={self.DB_PASSWORD}"
        )

    # --- LLM ---
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "claude-haiku-4-5")
    LLM_BATCH_SIZE: int = int(os.getenv("LLM_BATCH_SIZE", "30"))
    LLM_MIN_CONFIDENCE: float = float(os.getenv("LLM_MIN_CONFIDENCE", "0.05"))
    # Tags with confidence below this aren't stored (sparse output).

    # --- Service ---
    SERVICE_HOST: str = os.getenv("SERVICE_HOST", "0.0.0.0")
    SERVICE_PORT: int = int(os.getenv("SERVICE_PORT", "8000"))

    # --- Task classification ---
    # Fallback duration in minutes by top tag, used when LLM is uncertain.
    # Easy to tune without code changes once we see real data.
    DEFAULT_DURATION_BY_TAG: dict[str, int] = {
        "deep_work":    60,
        "shallow_work": 30,
        "routine":      15,
        "meeting":      30,
        "interview":    60,
        "planning":     45,
        "learning":     60,
        "exercise":     60,
        "social":       90,
        "hobby":        60,
        "errand":       30,
        "health":       60,
        "meal":         45,
        "commute":      30,
        "rest":         30,
        "work":         45,
        "personal":     30,
        "break":        30,
    }
    DURATION_FALLBACK_MINUTES: int = int(os.getenv("DURATION_FALLBACK_MINUTES", "30"))
    DURATION_CONFIDENCE_THRESHOLD: float = float(
        os.getenv("DURATION_CONFIDENCE_THRESHOLD", "0.5")
    )

    # --- Default user profile (until Layer 4 onboarding) ---
    DEFAULT_WORK_START_HOUR: int = int(os.getenv("DEFAULT_WORK_START_HOUR", "9"))
    DEFAULT_WORK_END_HOUR: int = int(os.getenv("DEFAULT_WORK_END_HOUR", "18"))
    DEFAULT_SLEEP_START_HOUR: int = int(os.getenv("DEFAULT_SLEEP_START_HOUR", "23"))
    DEFAULT_SLEEP_END_HOUR: int = int(os.getenv("DEFAULT_SLEEP_END_HOUR", "7"))
    DEFAULT_MAX_TASKS_PER_DAY: int = int(os.getenv("DEFAULT_MAX_TASKS_PER_DAY", "6"))
    DEFAULT_BUFFER_MINUTES: int = int(os.getenv("DEFAULT_BUFFER_MINUTES", "15"))


settings = Settings()