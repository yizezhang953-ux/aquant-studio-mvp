from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AQuant Studio API"
    app_env: str = "local"
    api_v1_prefix: str = "/api/v1"
    live_trading_enabled: bool = False
    database_url: str = "sqlite:///./aquant_web_app.db"
    auth_token_ttl_hours: int = 24
    allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173", "http://localhost:3000"]
    backup_dir: str = "runtime/backups"

    # Accounts. Administrators write the shared market data and re-seed the database.
    # Grant the role with: python -m app.tasks.database_maintenance make-admin you@example.com
    # first_user_is_admin (default: only when APP_ENV=local) makes the first registered account admin.
    first_user_is_admin: bool | None = None
    allow_registration: bool = True
    password_hash_iterations: int = 600_000
    login_max_failures: int = 5
    login_lockout_minutes: int = 15

    # Database lifecycle: run Alembic migrations at startup and seed templates/sample data once.
    run_migrations_on_startup: bool = True
    seed_on_startup: bool = True

    # Request limits for market-data imports.
    max_upload_bytes: int = 5 * 1024 * 1024
    max_import_bars: int = 50_000

    # Real market data (Tencent quotes / HKEX board lots / Frankfurter FX). Disable on hosts
    # without outbound internet access.
    market_data_network_enabled: bool = True

    @property
    def first_user_admin_enabled(self) -> bool:
        return self.app_env == "local" if self.first_user_is_admin is None else self.first_user_is_admin

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_comma_separated(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
