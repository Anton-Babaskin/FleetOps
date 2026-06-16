from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from fleetops.domain.statuses import Status, worst_status

SCHEMA_VERSION = "1.0"


class HostIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    hostname: str = Field(min_length=1)


class CheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    status: Status
    summary: str = Field(min_length=1)
    metrics: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    error: str | None = None
    timed_out: bool = False
    duration_ms: int = Field(ge=0)
    raw_ref: str | None = None


class HealthResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    host: HostIdentity
    collected_at: datetime
    duration_ms: int = Field(ge=0)
    overall_status: Status
    checks: list[CheckResult]

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version: {value}")
        return value

    @classmethod
    def from_checks(
        cls,
        *,
        host: HostIdentity,
        collected_at: datetime,
        duration_ms: int,
        checks: list[CheckResult],
    ) -> "HealthResult":
        return cls(
            host=host,
            collected_at=collected_at,
            duration_ms=duration_ms,
            overall_status=worst_status([check.status for check in checks]),
            checks=checks,
        )
