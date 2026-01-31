"""Bot configuration."""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


# Load .env from project root
load_dotenv()


class Config:
    """Bot configuration from environment variables."""

    def __init__(self):
        self.bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.google_spreadsheet_id: Optional[str] = os.getenv("GOOGLE_SPREADSHEET_ID")

        # Parse allowed users (comma-separated list of user IDs)
        allowed_users_str = os.getenv("ALLOWED_USERS", "")
        self.allowed_users: list[int] = []
        if allowed_users_str:
            self.allowed_users = [
                int(uid.strip())
                for uid in allowed_users_str.split(",")
                if uid.strip()
            ]

        # Google credentials path
        self.credentials_path: Path = (
            Path.home() / ".expense-tracker" / "credentials.json"
        )

    def validate(self) -> list[str]:
        """Validate configuration.

        Returns:
            List of validation error messages, empty if valid.
        """
        errors = []

        if not self.bot_token:
            errors.append("TELEGRAM_BOT_TOKEN is not set in .env file")

        return errors


# Global config instance
config = Config()
