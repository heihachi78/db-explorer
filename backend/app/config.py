from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded exclusively from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    oracle_user: str | None = None
    oracle_password: str | None = None
    oracle_dsn: str | None = None
    oracle_mode: Literal["thin", "thick"] = "thin"

    app_port: int = Field(default=8000, ge=1, le=65535)
    app_data_dir: Path = Path("data")
    app_log_level: str = "INFO"
    app_cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    @field_validator("app_cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def database_path(self) -> Path:
        return self.app_data_dir / "oracle_graph.db"

    @property
    def next_database_path(self) -> Path:
        return self.app_data_dir / "oracle_graph.next.db"

    @property
    def export_dir(self) -> Path:
        return self.app_data_dir / "exports"

    @property
    def oracle_configured(self) -> bool:
        return all((self.oracle_user, self.oracle_password, self.oracle_dsn))


@lru_cache
def get_settings() -> Settings:
    return Settings()
