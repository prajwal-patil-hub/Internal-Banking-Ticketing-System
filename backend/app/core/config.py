"""Application settings loaded from environment variables.

Single source of truth for runtime configuration. Never read os.environ directly
elsewhere in the codebase — always go through `settings`.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- App ---
    APP_ENV: Literal["development", "staging", "production"] = "development"
    APP_NAME: str = "SUCCESS Bank API"
    APP_DEBUG: bool = False
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # --- Security ---
    JWT_SECRET: str = Field(min_length=32)
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TTL_MINUTES: int = 15
    JWT_REFRESH_TTL_DAYS: int = 7
    PASSWORD_PEPPER: str = ""

    # --- Database ---
    DATABASE_URL: str

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- S3 / MinIO ---
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_BUCKET: str = "success-attachments"
    S3_REGION: str = "us-east-1"

    # --- CORS ---
    CORS_ORIGINS: str = "http://localhost:5173"

    # --- Email ---
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "no-reply@successbank.local"

    # --- SLA defaults (used as fallback if DB policy missing) ---
    SLA_CRITICAL_MINUTES: int = 120
    SLA_HIGH_MINUTES: int = 360
    SLA_MEDIUM_MINUTES: int = 1440
    SLA_LOW_MINUTES: int = 4320

    # --- AI ---
    # AI_PROVIDER selects which LLM API the AI client routes to.
    #   groq      — recommended for local/dev: free tier, OpenAI-compatible.
    #   anthropic — production Claude.
    AI_PROVIDER: Literal["groq", "anthropic"] = "groq"
    AI_ENABLED: bool = True
    AI_MAX_TOKENS: int = 1024
    AI_CONFIDENCE_THRESHOLD: float = 0.7

    # Anthropic provider
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"

    # Groq provider (OpenAI-compatible API at https://api.groq.com/openai/v1)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"

    @property
    def ai_provider_key(self) -> str:
        """Return the API key for the currently selected provider."""
        return self.GROQ_API_KEY if self.AI_PROVIDER == "groq" else self.ANTHROPIC_API_KEY

    @property
    def ai_provider_key_env_name(self) -> str:
        return "GROQ_API_KEY" if self.AI_PROVIDER == "groq" else "ANTHROPIC_API_KEY"

    # --- Email Ingestion (IMAP) ---
    IMAP_ENABLED: bool = False
    IMAP_HOST: str = "localhost"
    IMAP_PORT: int = 993
    IMAP_USER: str = ""
    IMAP_PASSWORD: str = ""
    IMAP_MAILBOX: str = "INBOX"
    IMAP_USE_SSL: bool = True
    SUPPORT_EMAIL: str = "support@successbank.local"

    # --- Notification ---
    NOTIFICATION_EMAIL_ENABLED: bool = True
    MANAGER_EMAILS: str = ""  # comma-separated manager emails for SLA breach notifications

    @property
    def manager_email_list(self) -> list[str]:
        return [e.strip() for e in self.MANAGER_EMAILS.split(",") if e.strip()]

    @field_validator("CORS_ORIGINS")
    @classmethod
    def _strip_origins(cls, v: str) -> str:
        return ",".join(o.strip() for o in v.split(",") if o.strip())

    @property
    def cors_origin_list(self) -> list[str]:
        return [o for o in self.CORS_ORIGINS.split(",") if o]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
