from collections.abc import Awaitable, Callable
from time import monotonic

from fleetops.checks.disk import DiskFacts, FileSystemFacts
from fleetops.checks.load import LoadFacts
from fleetops.checks.memory import MemoryFacts
from fleetops.checks.systemd import SystemdFacts
from fleetops.config import LoadThresholds, PercentThresholds, SystemdThresholds
from fleetops.domain.models import CheckResult
from fleetops.domain.statuses import Status, worst_status


def evaluate_load(
    facts: LoadFacts,
    thresholds: LoadThresholds,
    duration_ms: int = 0,
) -> CheckResult:
    ratio = facts.load_1m / facts.cpu_count
    if ratio >= thresholds.critical_per_cpu:
        status = Status.CRITICAL
        reason = f"Load per CPU exceeded critical threshold of {thresholds.critical_per_cpu:g}"
    elif ratio >= thresholds.warning_per_cpu:
        status = Status.WARNING
        reason = f"Load per CPU exceeded warning threshold of {thresholds.warning_per_cpu:g}"
    else:
        status = Status.OK
        reason = None
    return CheckResult(
        name="load",
        status=status,
        summary=(
            f"{facts.load_1m:g} / {facts.load_5m:g} / {facts.load_15m:g} - "
            f"{facts.cpu_count} CPU"
        ),
        metrics=facts.model_dump(),
        reason=reason,
        duration_ms=duration_ms,
    )


def evaluate_memory(
    facts: MemoryFacts,
    thresholds: PercentThresholds,
    duration_ms: int = 0,
) -> CheckResult:
    if facts.usage_percent >= thresholds.critical_percent:
        status = Status.CRITICAL
        reason = f"Memory usage exceeded critical threshold of {thresholds.critical_percent:g}%"
    elif facts.usage_percent >= thresholds.warning_percent:
        status = Status.WARNING
        reason = f"Memory usage exceeded warning threshold of {thresholds.warning_percent:g}%"
    else:
        status = Status.OK
        reason = None
    return CheckResult(
        name="memory",
        status=status,
        summary=f"{facts.usage_percent:g}% used",
        metrics=facts.model_dump(),
        reason=reason,
        duration_ms=duration_ms,
    )


def _filesystem_status(fs: FileSystemFacts, thresholds: PercentThresholds) -> Status:
    if fs.usage_percent >= thresholds.critical_percent:
        return Status.CRITICAL
    if fs.usage_percent >= thresholds.warning_percent:
        return Status.WARNING
    return Status.OK


def evaluate_disk(
    facts: DiskFacts,
    thresholds: PercentThresholds,
    duration_ms: int = 0,
) -> CheckResult:
    statuses = [_filesystem_status(fs, thresholds) for fs in facts.filesystems]
    status = worst_status(statuses)
    worst_fs = max(facts.filesystems, key=lambda fs: fs.usage_percent)
    reason = None
    if status == Status.CRITICAL:
        reason = f"Disk usage exceeded critical threshold of {thresholds.critical_percent:g}%"
    elif status == Status.WARNING:
        reason = f"Disk usage exceeded warning threshold of {thresholds.warning_percent:g}%"
    summary = (
        "all filesystems below thresholds"
        if status == Status.OK
        else f"{worst_fs.mountpoint} is {worst_fs.usage_percent:g}% full"
    )
    return CheckResult(
        name="disk",
        status=status,
        summary=summary,
        metrics={"filesystems": [fs.model_dump() for fs in facts.filesystems]},
        reason=reason,
        duration_ms=duration_ms,
    )


def evaluate_systemd(
    facts: SystemdFacts,
    thresholds: SystemdThresholds,
    duration_ms: int = 0,
) -> CheckResult:
    if facts.failed_count == 0:
        status = Status.OK
        summary = "no failed units"
        reason = None
    else:
        status = Status.CRITICAL if thresholds.critical_on_failed else Status.WARNING
        summary = f"{facts.failed_count} failed unit(s): {', '.join(facts.failed_units)}"
        reason = "systemd reported failed units"
    return CheckResult(
        name="systemd",
        status=status,
        summary=summary,
        metrics=facts.model_dump(),
        reason=reason,
        duration_ms=duration_ms,
    )


def unknown_check(
    *,
    name: str,
    summary: str,
    error: str,
    duration_ms: int,
    timed_out: bool = False,
) -> CheckResult:
    return CheckResult(
        name=name,
        status=Status.UNKNOWN,
        summary=summary,
        metrics={},
        reason=None,
        error=error,
        timed_out=timed_out,
        duration_ms=duration_ms,
    )


async def run_timed_check(
    name: str,
    action: Callable[[], Awaitable[CheckResult]],
    timeout_seconds: float,
) -> CheckResult:
    import asyncio

    started = monotonic()
    try:
        return await asyncio.wait_for(action(), timeout=timeout_seconds)
    except TimeoutError:
        return unknown_check(
            name=name,
            summary=f"{name.capitalize()} check timed out",
            error=f"timeout after {timeout_seconds:g}s",
            timed_out=True,
            duration_ms=int((monotonic() - started) * 1000),
        )
    except Exception as exc:
        return unknown_check(
            name=name,
            summary=f"{name.capitalize()} check failed",
            error=f"{type(exc).__name__}: {exc}",
            duration_ms=int((monotonic() - started) * 1000),
        )
