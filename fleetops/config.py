from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FLEETOPS_", env_file=".env", extra="ignore")

    config_path: Path = Path("config/hosts.yml")
    demo_mode: bool = False
    telegram_bot_token: str | None = None
    ssh_private_key_path: Path | None = None
    ssh_known_hosts_path: Path | None = None
    ssh_password: str | None = None


class HostConfig(BaseModel):
    id: str = Field(min_length=1)
    hostname: str = Field(min_length=1)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1)


class TelegramConfig(BaseModel):
    allowed_user_ids: list[int] = Field(min_length=1)


class LoadThresholds(BaseModel):
    warning_per_cpu: float = Field(gt=0)
    critical_per_cpu: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_order(self) -> "LoadThresholds":
        if self.critical_per_cpu <= self.warning_per_cpu:
            raise ValueError("load critical_per_cpu must be greater than warning_per_cpu")
        return self


class PercentThresholds(BaseModel):
    warning_percent: float = Field(ge=0, le=100)
    critical_percent: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_order(self) -> "PercentThresholds":
        if self.critical_percent <= self.warning_percent:
            raise ValueError("critical_percent must be greater than warning_percent")
        return self


class SystemdThresholds(BaseModel):
    critical_on_failed: bool = False


class Thresholds(BaseModel):
    load: LoadThresholds
    memory: PercentThresholds
    disk: PercentThresholds
    systemd: SystemdThresholds


class TimeoutConfig(BaseModel):
    connection_seconds: float = Field(gt=0)
    command_seconds: float = Field(gt=0)


class SnapshotConfig(BaseModel):
    output_directory: Path
    retention_hours: int = Field(ge=1)


class AppConfig(BaseModel):
    host: HostConfig
    telegram: TelegramConfig
    thresholds: Thresholds
    timeouts: TimeoutConfig
    snapshot: SnapshotConfig

    @field_validator("telegram")
    @classmethod
    def validate_telegram_ids(cls, value: TelegramConfig) -> TelegramConfig:
        if any(user_id <= 0 for user_id in value.allowed_user_ids):
            raise ValueError("telegram allowed_user_ids must be positive numeric IDs")
        return value


def load_config(path: Path) -> AppConfig:
    try:
        data: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"configuration file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML configuration: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("configuration root must be a YAML mapping")
    try:
        return AppConfig.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"invalid configuration: {exc}") from exc

