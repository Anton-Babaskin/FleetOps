from fleetops.checks.load import LoadFacts
from fleetops.config import LoadThresholds
from fleetops.domain.statuses import Status
from fleetops.rules.health import evaluate_load


def test_load_thresholds() -> None:
    thresholds = LoadThresholds(warning_per_cpu=1.0, critical_per_cpu=2.0)
    ok = evaluate_load(LoadFacts(load_1m=1, load_5m=1, load_15m=1, cpu_count=2), thresholds)
    warning = evaluate_load(LoadFacts(load_1m=2, load_5m=1, load_15m=1, cpu_count=2), thresholds)
    critical = evaluate_load(LoadFacts(load_1m=4, load_5m=1, load_15m=1, cpu_count=2), thresholds)
    assert ok.status == Status.OK
    assert warning.status == Status.WARNING
    assert critical.status == Status.CRITICAL
