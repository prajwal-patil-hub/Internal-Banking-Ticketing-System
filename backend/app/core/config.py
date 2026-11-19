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
    # Binds all interfaces because the process runs inside a container and is
    # reached from outside it; 127.0.0.1 would be unreachable. Exposure is
    # decided by the compose/ingress port mapping, not here.
    APP_HOST: str = "0.0.0.0"  # noqa: S104
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
    # LLM_PROVIDER: "ollama" (local via Ollama) | "anthropic" (cloud) | "none" (disabled)
    LLM_PROVIDER: Literal["ollama", "anthropic", "none"] = "ollama"
    # Ollama base URL — from inside Docker container use host.docker.internal
    LLM_BASE_URL: str = "http://host.docker.internal:11434"
    LLM_MODEL: str = "glm4"
    # Anthropic (only used when LLM_PROVIDER=anthropic)
    ANTHROPIC_API_KEY: str = ""
    AI_ENABLED: bool = True
    AI_MAX_TOKENS: int = 1024
    AI_CONFIDENCE_THRESHOLD: float = 0.7

    # --- AI cost and latency controls ---
    # Chat replies are capped far below AI_MAX_TOKENS (which still governs the
    # one-shot extraction calls). An assistant answering a support question
    # needs a few sentences; left unbounded a local model will happily produce
    # a thousand-token essay, and the user waits for every one of them.
    AI_CHAT_MAX_TOKENS: int = 400
    # Characters of grounding context. A local model re-reads the entire prompt
    # each turn, so this is a per-message tax, not a one-off.
    AI_CONTEXT_CHAR_BUDGET: int = 6000
    # Characters of prior conversation replayed. Bounds a long chat instead of
    # letting it grow until it crowds out the context block.
    AI_HISTORY_CHAR_BUDGET: int = 4000
    # Sampling: low temperature because this assistant reports facts from the
    # context block rather than writing prose.
    AI_TEMPERATURE: float = 0.2
    # Per-user AI calls allowed per minute.
    AI_RATE_LIMIT_PER_MINUTE: int = 20
    # Local models are slow on first token (model load + no GPU batching).
    # GLM-4 on an M2 Mac routinely needs 30-90s for a cold request.
    AI_TIMEOUT_SECONDS: float = 180.0
    # Keep the model resident in Ollama between requests to avoid cold starts.
    AI_KEEP_ALIVE: str = "10m"

    # --- Knowledge base (RAG) ---
    KB_ENABLED: bool = True
    #: Ollama embedding model. Changing this invalidates every stored vector —
    #: the model name is recorded on each document version so a mismatch is
    #: detectable rather than silently returning nonsense neighbours.
    KB_EMBEDDING_MODEL: str = "nomic-embed-text"
    #: Must match the `Vector(...)` dimension in the migration. Changing it
    #: requires a migration and a full re-index, not just a config edit.
    KB_EMBEDDING_DIM: int = 768
    #: Largest knowledge-base upload. Higher than the 15 MB attachment cap
    #: because policy manuals are legitimately large.
    KB_MAX_UPLOAD_BYTES: int = 40 * 1024 * 1024
    #: Target chunk size and overlap, measured in characters (a ~4 chars/token
    #: proxy). Chunks split on headings first and only fall back to size.
    KB_CHUNK_CHARS: int = 2048
    KB_CHUNK_OVERLAP_CHARS: int = 256
    #: Candidates pulled from each retrieval arm before fusion.
    KB_RETRIEVAL_TOP_K: int = 50
    #: Passages actually placed in the prompt after fusion.
    KB_CONTEXT_TOP_N: int = 8
    #: Below this derived confidence the service abstains rather than answering.
    KB_MIN_CONFIDENCE: float = 0.35
    #: Hard ceiling on passages produced by one document.
    #:
    #: Ingestion runs inline and issues one embedding round trip per batch, so
    #: an unbounded document holds the single local model — and with it chat
    #: and email intake — for as long as it takes. A 40 MB text file would
    #: otherwise yield ~20k passages and ~1250 sequential round trips.
    KB_MAX_CHUNKS_PER_DOCUMENT: int = 4000

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
