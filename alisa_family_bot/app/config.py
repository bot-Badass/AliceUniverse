from __future__ import annotations

from functools import lru_cache
from typing import List, Set

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str = Field(alias="BOT_TOKEN")
    database_url: str = Field(alias="DATABASE_URL")
    channel_id: int = Field(alias="CHANNEL_ID")
    super_admins_raw: str = Field(alias="SUPER_ADMINS")
    donation_url: str = Field(default="https://send.monobank.ua/", alias="DONATION_URL")
    donation_card: str | None = Field(default=None, alias="DONATION_CARD")
    webhook_base_url: str | None = Field(default=None, alias="WEBHOOK_BASE_URL")
    webhook_path: str = Field(default="/webhook", alias="WEBHOOK_PATH")
    webhook_secret: str | None = Field(default=None, alias="WEBHOOK_SECRET")
    local_polling: bool = Field(default=False, alias="LOCAL_POLLING")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8080, alias="PORT")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("super_admins_raw")
    @classmethod
    def validate_super_admins_raw(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("SUPER_ADMINS must not be empty")
        return value

    @property
    def super_admins_list(self) -> List[int]:
        result: List[int] = []
        for part in self.super_admins_raw.split(","):
            part = part.strip()
            if part:
                result.append(int(part))
        return result

    @property
    def super_admins(self) -> Set[int]:
        return set(self.super_admins_list)

    @property
    def primary_super_admin(self) -> int | None:
        return self.super_admins_list[0] if self.super_admins_list else None

    @property
    def webhook_url(self) -> str | None:
        if self.local_polling:
            return None
        if not self.webhook_base_url:
            return None
        return f"{self.webhook_base_url.rstrip('/')}{self.webhook_path}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
