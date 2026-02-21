"""
Conduit configuration.

Resolution order (highest priority first):
  1. Environment variables   (CONDUIT_DATABASE__URL=...)
  2. YAML config file        (conduit.yaml)
  3. Defaults defined here
"""

from __future__ import annotations

import os
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class LogFormat(StrEnum):
    JSON = "json"
    CONSOLE = "console"


class ServerSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4


class DatabaseSettings(BaseModel):
    url: str = "postgresql+asyncpg://conduit:conduit_dev@localhost:5432/conduit"
    pool_size: int = 20
    max_overflow: int = 10
    echo: bool = False


class RedisSettings(BaseModel):
    url: str = "redis://localhost:6379/0"
    key_prefix: str = "conduit:"


class AuthSettings(BaseModel):
    master_api_key: str = ""


class LoggingSettings(BaseModel):
    level: LogLevel = LogLevel.INFO
    format: LogFormat = LogFormat.JSON


class ProviderDeploymentConfig(BaseModel):
    name: str
    provider: str
    model_name: str
    api_key: str = ""
    api_base: str = ""
    priority: int = 1
    is_active: bool = True


class RoutingSettings(BaseModel):
    default_strategy: str = "priority"
    fallback_enabled: bool = True
    max_retries: int = 2
    retry_delay_ms: int = 500


class CacheSettings(BaseModel):
    enabled: bool = False
    default_ttl_seconds: int = 3600
    semantic_threshold: float = 0.95


class Settings(BaseSettings):
    """Root settings — merges env vars, YAML, and defaults."""

    model_config = SettingsConfigDict(
        env_prefix="CONDUIT_",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    env: str = "development"
    server: ServerSettings = Field(default_factory=ServerSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    providers: list[ProviderDeploymentConfig] = Field(default_factory=list)
    routing: RoutingSettings = Field(default_factory=RoutingSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)

    # Convenience aliases for flat env vars
    master_api_key: str = ""
    log_level: str = ""

    def model_post_init(self, __context: Any) -> None:
        # Allow flat env vars to override nested ones
        if self.master_api_key:
            self.auth.master_api_key = self.master_api_key
        if self.log_level:
            self.logging.level = LogLevel(self.log_level.upper())

        # Resolve ${ENV_VAR} references in provider API keys
        for provider in self.providers:
            if provider.api_key.startswith("${") and provider.api_key.endswith("}"):
                env_var = provider.api_key[2:-1]
                provider.api_key = os.environ.get(env_var, "")


def _load_yaml_config() -> dict[str, Any]:
    """Load YAML config file if it exists."""
    search_paths = [
        Path("conduit.yaml"),
        Path("config/conduit.yaml"),
        Path("/app/config/conduit.yaml"),
        Path("/etc/conduit/conduit.yaml"),
    ]
    for path in search_paths:
        if path.is_file():
            with open(path) as f:
                return yaml.safe_load(f) or {}
    return {}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached settings instance."""
    yaml_data = _load_yaml_config()
    return Settings(**yaml_data)