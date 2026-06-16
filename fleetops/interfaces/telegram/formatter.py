import html

from fleetops.domain.models import CheckResult, HealthResult
from fleetops.domain.statuses import Status

ICONS = {
    Status.OK: "OK",
    Status.WARNING: "WARNING",
    Status.CRITICAL: "CRITICAL",
    Status.UNKNOWN: "UNKNOWN",
}


def _line_for_check(check: CheckResult) -> str:
    name = check.name.capitalize() if check.name != "systemd" else "systemd"
    return f"{ICONS[check.status]} {name}: {html.escape(check.summary)}"


def format_health(result: HealthResult) -> str:
    lines = [
        html.escape(result.host.hostname),
        "",
        f"Overall: {result.overall_status.value.upper()}",
        f"Collection: {result.duration_ms} ms",
        "",
    ]
    lines.extend(_line_for_check(check) for check in result.checks)
    return "\n".join(lines)

