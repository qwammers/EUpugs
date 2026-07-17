from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="backend/.env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(alias="DATABASE_URL")
    session_secret: str = Field(alias="SESSION_SECRET")
    session_cookie_name: str = Field(default="hostedpugs_session", alias="SESSION_COOKIE_NAME")
    session_max_age_seconds: int = Field(default=2_592_000, alias="SESSION_MAX_AGE_SECONDS")
    discord_client_id: str = Field(alias="DISCORD_CLIENT_ID")
    discord_client_secret: str = Field(alias="DISCORD_CLIENT_SECRET")
    discord_redirect_uri: str = Field(alias="DISCORD_REDIRECT_URI")
    discord_bot_token: str = Field(alias="DISCORD_BOT_TOKEN")
    discord_guild_id: str = Field(alias="DISCORD_GUILD_ID")
    discord_log_channel_id: str = Field(alias="DISCORD_LOG_CHANNEL_ID")
    discord_admin_role_ids: str = Field(default="", alias="DISCORD_ADMIN_ROLE_IDS")
    frontend_origin: str = Field(alias="FRONTEND_ORIGIN")
    frontend_url: str | None = Field(default=None, alias="FRONTEND_URL")
    api_base_url: str = Field(alias="API_BASE_URL")
    enable_auto_migrate: bool = Field(default=True, alias="ENABLE_AUTO_MIGRATE")
    logstf_sync_limit: int = Field(default=20, alias="LOGSTF_SYNC_LIMIT")

    @property
    def admin_role_ids(self) -> list[str]:
        return [value.strip() for value in self.discord_admin_role_ids.split(",") if value.strip()]

    @property
    def login_redirect_url(self) -> str:
        return (self.frontend_url or self.frontend_origin).rstrip("/")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
