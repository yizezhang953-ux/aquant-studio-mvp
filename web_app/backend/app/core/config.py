from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AQuant Studio API"
    app_env: str = "local"
    api_v1_prefix: str = "/api/v1"
    live_trading_enabled: bool = False
    database_url: str = "sqlite:///./aquant_web_app.db"
    redis_url: str = "redis://localhost:6379/0"
    auth_token_ttl_hours: int = 24
    allowed_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    market_data_provider: str = "demo_a_share"
    tushare_token: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
