from datetime import UTC, datetime

from fleetops.domain.models import CheckResult, HealthResult, HostIdentity
from fleetops.domain.statuses import Status
from fleetops.interfaces.telegram.formatter import format_health


def test_formatter_escapes_html() -> None:
    result = HealthResult.from_checks(
        host=HostIdentity(id="demo-server", hostname="demo.example.com"),
        collected_at=datetime.now(UTC),
        duration_ms=42,
        checks=[
            CheckResult(
                name="disk",
                status=Status.WARNING,
                summary="/home <tag> is 87% full",
                duration_ms=1,
            )
        ],
    )
    text = format_health(result)
    assert "Overall: WARNING" in text
    assert "&lt;tag&gt;" in text

