"""Application settings via pydantic-settings."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from platformdirs import user_config_dir, user_data_dir
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = "tagsmith"
PROMPT_VERSION = "v1"

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
