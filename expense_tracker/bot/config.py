"""Bot configuration using Pydantic Settings."""

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram settings
    telegram_bot_token: str = Field(
        default="",
        description="Telegram bot token from @BotFather",
    )

    # Access control
    allowed_users: list[int] = Field(
        default_factory=list,
        description="List of allowed Telegram user IDs (empty = allow all)",
    )
    admin_ids: list[int] = Field(
        default_factory=list,
        description="List of admin Telegram IDs for notifications",
    )

    # Google Sheets
    google_spreadsheet_id: str | None = Field(
        default=None,
        description="Google Sheets spreadsheet ID",
    )

    # AI Providers (for future use)
    ai_providers: str | None = Field(
        default=None,
        description="JSON array of AI providers with failover support",
    )

    # Encryption key for sensitive data (auto-generated if not set)
    encryption_key: str = Field(
        default="default-expense-tracker-key-change-in-production",
        description="Secret key for encrypting sensitive data",
    )

    # Cloudflare R2 settings
    r2_account_id: str | None = Field(default=None, description="Cloudflare account ID")
    r2_access_key_id: str | None = Field(default=None, description="R2 Access Key ID")
    r2_secret_access_key: str | None = Field(default=None, description="R2 Secret Access Key")
    r2_bucket_name: str = Field(default="expense-tracker-backups", description="R2 bucket name")

    @field_validator("allowed_users", "admin_ids", mode="before")
    @classmethod
    def parse_int_list(cls, v: Any) -> list[int]:
        """Parse comma-separated or JSON list of integers."""
        if v is None or v == "":
            return []
        if isinstance(v, list):
            return [int(x) for x in v]
        if isinstance(v, str):
            v = v.strip()
            # Try JSON format first: [1, 2, 3]
            if v.startswith("["):
                try:
                    parsed = json.loads(v)
                    return [int(x) for x in parsed]
                except json.JSONDecodeError:
                    pass
            # Fallback to comma-separated: 1,2,3
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return []

    @field_validator("ai_providers", mode="before")
    @classmethod
    def parse_ai_providers(cls, v: Any) -> str | None:
        """Validate AI providers JSON string."""
        if v is None or v == "":
            return None
        if isinstance(v, str):
            try:
                providers = json.loads(v)
                if not isinstance(providers, list):
                    raise ValueError("AI providers must be a JSON array")
                for idx, provider in enumerate(providers):
                    if not isinstance(provider, dict):
                        raise ValueError(f"Provider {idx} must be a JSON object")
                    if "name" not in provider:
                        raise ValueError(f"Provider {idx} missing 'name' field")
                    if "api_key" not in provider:
                        raise ValueError(f"Provider {idx} missing 'api_key' field")
                return v
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in ai_providers: {e}")
        return None

    def get_ai_providers(self) -> list[dict]:
        """Parse and return AI providers list."""
        if not self.ai_providers:
            return []
        return json.loads(self.ai_providers)

    # Computed properties for paths
    @property
    def data_dir(self) -> Path:
        """Data directory (respects HOME env var for Docker)."""
        return Path.home() / ".expense-tracker"

    @property
    def database_path(self) -> Path:
        """Path to SQLite database."""
        return self.data_dir / "expenses.db"

    @property
    def backups_dir(self) -> Path:
        """Path to backups directory."""
        return self.data_dir / "backups"

    @property
    def credentials_path(self) -> Path:
        """Path to Google credentials JSON."""
        return self.data_dir / "credentials.json"

    @property
    def r2_endpoint_url(self) -> str | None:
        """Generate R2 endpoint URL from account ID."""
        if self.r2_account_id:
            return f"https://{self.r2_account_id}.r2.cloudflarestorage.com"
        return None

    @property
    def r2_enabled(self) -> bool:
        """Check if R2 is properly configured."""
        return all([self.r2_account_id, self.r2_access_key_id, self.r2_secret_access_key])

    def ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)

    def validate(self) -> list[str]:
        """Validate configuration.

        Returns:
            List of validation error messages, empty if valid.
        """
        errors = []
        if not self.telegram_bot_token:
            errors.append("TELEGRAM_BOT_TOKEN is not set")
        return errors


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached settings instance (singleton pattern)."""
    return Settings()


# Backward compatibility alias
config = get_settings()
