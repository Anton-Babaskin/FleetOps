from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from fleetops.domain.models import CheckResult, HealthResult, HostIdentity
from fleetops.domain.statuses import Status


def test_health_contract_and_overall_priority() -> None:
    checks = [
        CheckResult(name="load", status=Status.OK, summary="ok", duration_ms=1),
        CheckResult(name="disk", status=Status.UNKNOWN, summary="unknown", duration_ms=1),
        CheckResult(name="memory", status=Status.WARNING, summary="warning", duration_ms=1),
        CheckResult(name="systemd", status=Status.CRITICAL, summary="critical", duration_ms=1),
    ]
    result = HealthResult.from_checks(
        host=HostIdentity(id="demo-server", hostname="demo.example.com"),
        collected_at=datetime.now(UTC),
        duration_ms=10,
        checks=checks,
    )
    assert result.schema_version == "1.0"
    assert result.overall_status == Status.CRITICAL


def test_unsupported_schema_version_rejected() -> None:
    with pytest.raises(ValidationError):
        HealthResult.model_validate(
            {
                "schema_version": "2.0",
                "host": {"id": "demo-server", "hostname": "demo.example.com"},
                "collected_at": "2026-06-16T15:30:00Z",
                "duration_ms": 1,
                "overall_status": "ok",
                "checks": [],
            }
        )

