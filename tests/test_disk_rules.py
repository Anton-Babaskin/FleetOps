from fleetops.checks.disk import parse_df
from fleetops.config import PercentThresholds
from fleetops.domain.statuses import Status
from fleetops.rules.health import evaluate_disk


def test_disk_multiple_filesystems_selects_worst() -> None:
    facts = parse_df(
        "\n".join(
            [
                "Filesystem Type 1B-blocks Used Available Use% Mounted on",
                "/dev/sda1 ext4 100 40 60 40% /",
                "tmpfs tmpfs 100 90 10 90% /run",
                "/dev/sdb1 ext4 100 87 13 87% /home",
            ]
        )
    )
    result = evaluate_disk(facts, PercentThresholds(warning_percent=85, critical_percent=95))
    assert result.status == Status.WARNING
    assert "/home" in result.summary
    assert len(result.metrics["filesystems"]) == 2


def test_disk_critical() -> None:
    facts = parse_df(
        "\n".join(
            [
                "Filesystem Type 1B-blocks Used Available Use% Mounted on",
                "/dev/sda1 ext4 100 96 4 96% /",
            ]
        )
    )
    result = evaluate_disk(facts, PercentThresholds(warning_percent=85, critical_percent=95))
    assert result.status == Status.CRITICAL
