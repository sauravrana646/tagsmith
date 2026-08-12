"""Application settings via pydantic-settings."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from platformdirs import user_config_dir, user_data_dir
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = "tagsmith"
PROMPT_VERSION = "v2"

# Load .env into os.environ so provider keys (OPENROUTER_API_KEY, OPENAI_API_KEY,
# GOOGLE_API_KEY, …) are visible to Pydantic AI. Settings alone only consume TAGSMITH_*.
load_dotenv(override=False)


def default_config_dir() -> Path:
    return Path(user_config_dir(APP_NAME, appauthor=False))


def default_data_dir() -> Path:
    return Path(user_data_dir(APP_NAME, appauthor=False))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TAGSMITH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    google_client_secret_path: Path = Field(
        default_factory=lambda: default_config_dir() / "credentials.json"
    )
    token_path: Path = Field(default_factory=lambda: default_config_dir() / "token.json")
    database_url: str = Field(
        default_factory=lambda: f"sqlite:///{default_data_dir() / 'tagsmith.db'}"
    )
    rules_path: Path = Field(default_factory=lambda: default_config_dir() / "rules.yaml")

    llm_model: str = "openai:gpt-4.1-mini"
    confidence_apply: float = 0.75
    confidence_review: float = 0.5
    label_parent: str = "AI"
    needs_review_label: str = "needs-review"
    body_char_limit: int = 2000
    log_level: str = "INFO"
    # How many times Pydantic AI may retry when model JSON fails schema validation.
    llm_output_retries: int = 3

    # Phase 2 observability / cost estimates (optional).
    enable_logfire: bool = False
    # Rough USD cost used by eval reports when provider pricing is unknown.
    cost_per_1k_input_tokens: float = 0.0
    cost_per_1k_output_tokens: float = 0.0

    # Phase 3 RAG
    enable_rag: bool = True
    rag_example_k: int = 5
    rag_category_k: int = 3
    rag_embedding_dim: int = 256

    # Phase 4 — continuous operation / Pub/Sub watch
    pubsub_topic: str | None = None
    schedule_interval_seconds: int = 300
    watch_renew_hours: int = 24 * 6  # renew before the ~7-day Gmail watch expiry

    # Phase 5 — API / multi-tenant
    api_host: str = "127.0.0.1"
    api_port: int = 8080
    api_public_base_url: str = "http://127.0.0.1:8080"
    # Fernet key material (any passphrase; hashed to 32 bytes). Required for tenant tokens.
    token_encryption_key: str = ""
    # Web OAuth client (can reuse desktop JSON; prefer a Web application client).
    google_web_client_id: str = ""
    google_web_client_secret: str = ""
    google_oauth_redirect_path: str = "/auth/callback"
    # Optional Stripe (billing hooks; checkout not required for local single-user).
    stripe_api_key: str = ""
    stripe_webhook_secret: str = ""
    session_signing_key: str = ""

    @property
    def needs_review_label_name(self) -> str:
        return f"{self.label_parent}/{self.needs_review_label}"

    def gmail_label_name(self, key: str) -> str:
        return f"{self.label_parent}/{key}"

    def ensure_dirs(self) -> None:
        self.google_client_secret_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.rules_path.parent.mkdir(parents=True, exist_ok=True)
        if self.database_url.startswith("sqlite:///"):
            db_path = Path(self.database_url.removeprefix("sqlite:///"))
            db_path.parent.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
