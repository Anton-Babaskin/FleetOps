from fleetops.checks.systemd import parse_systemctl_failed
from fleetops.config import SystemdThresholds
from fleetops.domain.statuses import Status
from fleetops.rules.health import evaluate_systemd


def test_systemd_ok() -> None:
    facts = parse_systemctl_failed("0 loaded units listed.")
    assert evaluate_systemd(facts, SystemdThresholds(critical_on_failed=False)).status == Status.OK


def test_systemd_warning_or_critical() -> None:
    facts = parse_systemctl_failed("backup.service loaded failed failed Backup failed")
    warning = evaluate_systemd(facts, SystemdThresholds(critical_on_failed=False))
    critical = evaluate_systemd(facts, SystemdThresholds(critical_on_failed=True))
    assert warning.status == Status.WARNING
    assert critical.status == Status.CRITICAL
