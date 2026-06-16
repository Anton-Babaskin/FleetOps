from fleetops.checks.memory import MemoryFacts, parse_meminfo
from fleetops.config import PercentThresholds
from fleetops.domain.statuses import Status
from fleetops.rules.health import evaluate_memory


def test_parse_meminfo_and_thresholds() -> None:
    facts = parse_meminfo(
        "\n".join(
            [
                "MemTotal:       1000000 kB",
                "MemAvailable:    100000 kB",
                "SwapTotal:       100000 kB",
                "SwapFree:         50000 kB",
            ]
        )
    )
    assert facts.usage_percent == 90
    result = evaluate_memory(facts, PercentThresholds(warning_percent=80, critical_percent=95))
    assert result.status == Status.WARNING


def test_memory_critical() -> None:
    facts = MemoryFacts(
        total_bytes=100,
        used_bytes=96,
        available_bytes=4,
        usage_percent=96,
        swap_total_bytes=0,
        swap_used_bytes=0,
        swap_usage_percent=0,
    )
    result = evaluate_memory(facts, PercentThresholds(warning_percent=80, critical_percent=95))
    assert result.status == Status.CRITICAL
