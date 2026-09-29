"""
Application settings loaded from environment variables / .env file.
Single source of truth for configuration - never read os.environ directly
elsewhere in the app.
"""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database - individual parts, assembled into DATABASE_URL below rather
    # than requiring callers to hand-build a connection string.
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "a11y_audit"
    POSTGRES_PORT: int = 5432

    # JWT
    JWT_SECRET_KEY: str = "insecure-dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 20
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS - comma separated string in env, parsed into a list
    CORS_ORIGINS: str = "http://localhost:3000"

    # Crawler defaults
    CRAWLER_DEFAULT_MAX_DEPTH: int = 3
    CRAWLER_DEFAULT_MAX_PAGES: int = 200
    CRAWLER_CONCURRENCY: int = 8
    CRAWLER_REQUEST_TIMEOUT_SECONDS: int = 10

    ENVIRONMENT: str = "development"

    # Optional default user, created by `python -m scripts.seed_admin` for
    # local/dev convenience. Leave blank in real deployments.
    DEFAULT_ADMIN_FULL_NAME: str = "WinVinaya Admin"
    DEFAULT_ADMIN_EMAIL: str = "info@winvinaya.com"
    DEFAULT_ADMIN_PASSWORD: str = "Testpass@123"

    # --- AI Audit Agent (Phase 2) ---
    # Multi-provider support: Anthropic Claude, Google Gemini, Groq.
    # Model IDs are configurable so they can be swapped without a code change;
    # every AI stage defaults to the same model but can be pointed at a
    # cheaper/faster one independently.
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_API_KEYS: str = ""
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com/v1"

    # GEMINI_API_KEYS is comma-separated - llm_client rotates round-robin
    # across every key given, so a 429 on one account's quota fails over to
    # the next account's own quota immediately instead of waiting out the
    # backoff.
    GEMINI_API_KEYS: str = ""
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta"

    GROQ_API_KEYS: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"

    AI_MODEL_PLANNER: str = "claude-sonnet-4-6"
    AI_MODEL_JUDGMENT: str = "claude-sonnet-4-6"
    AI_MODEL_REFLECTION: str = "claude-sonnet-4-6"

    # Tried in order, after the requested model, when a call keeps failing
    # with a quota (429) or overload (5xx) error even after that model's own
    # retries are exhausted. Ordered: Claude -> Gemini -> Groq.
    AI_MODEL_FALLBACKS: str | List[str] = [
        "claude-sonnet-4-6",
        "gemini-3.5-flash-lite",
        "gemini-3-flash-preview",
        "gemini-3.1-flash-lite",
        "gemini-2.5-flash",
        "groq/llama-3.3-70b-versatile",
        "groq/openai/gpt-oss-20b",
    ]
    AI_REQUEST_TIMEOUT_SECONDS: int = 120
    # Gemini's internal "thinking" tokens are drawn from the *same*
    # maxOutputTokens budget as the visible response (confirmed live: an
    # unbounded/dynamic thinking budget (-1) consumed most of an 8192-token
    # ceiling producing a 2-step test plan, truncating the JSON mid-string).
    # A real AuditPlan covers ~50 WCAG criteria, so both numbers below were
    # picked generously and verified end-to-end against the real API rather
    # than guessed: a bounded thinking budget keeps reasoning cost capped and
    # predictable, and 16000 leaves headroom for thinking + a large plan.
    AI_MAX_OUTPUT_TOKENS: int = 16000
    # Judgment calls are meant to be small/fast/cheap (spec requirement), so
    # they get a smaller fixed thinking budget than PLAN/REFLECT.
    AI_JUDGMENT_THINKING_BUDGET: int = 512
    AI_PLANNING_THINKING_BUDGET: int = 2048

    # WCAG conformance level every generated AuditPlan must fully cover.
    WCAG_CONFORMANCE_LEVEL: str = "AA"

    # Perceive/Execute tuning
    AI_PAGE_LOAD_TIMEOUT_MS: int = 30000
    AI_KEYBOARD_MAX_TAB_STOPS: int = 60
    AI_LOW_CONFIDENCE_THRESHOLD: float = 0.6

    # Memory / retrieval
    AI_EMBEDDING_DIMENSIONS: int = 256
    AI_MEMORY_TOP_N: int = 5
    AI_MEMORY_MIN_SIMILARITY: float = 0.2

    # Where evidence screenshots are written; served back under /static.
    AI_SCREENSHOT_DIR: str = "static/audit_screenshots"

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def anthropic_api_keys_list(self) -> List[str]:
        keys = self.ANTHROPIC_API_KEYS or self.ANTHROPIC_API_KEY
        return [key.strip() for key in keys.split(",") if key.strip()]

    @property
    def gemini_api_keys_list(self) -> List[str]:
        return [key.strip() for key in self.GEMINI_API_KEYS.split(",") if key.strip()]

    @property
    def groq_api_keys_list(self) -> List[str]:
        return [key.strip() for key in self.GROQ_API_KEYS.split(",") if key.strip()]

    @property
    def ai_model_fallbacks_list(self) -> List[str]:
        if isinstance(self.AI_MODEL_FALLBACKS, list):
            return self.AI_MODEL_FALLBACKS
        return [m.strip() for m in self.AI_MODEL_FALLBACKS.split(",") if m.strip()]

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
