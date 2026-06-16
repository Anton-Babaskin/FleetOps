import asyncio
from pathlib import Path
from time import monotonic

from fleetops.checks.disk import DiskFacts, FileSystemFacts
from fleetops.checks.load import LoadFacts
from fleetops.checks.memory import MemoryFacts
from fleetops.checks.systemd import SystemdFacts
from fleetops.config import AppConfig
from fleetops.domain.models import CheckResult, HostIdentity
from fleetops.rules.health import (
    evaluate_disk,
    evaluate_load,
    evaluate_memory,
    evaluate_systemd,
    run_timed_check,
)


class DemoCollector:
    def __init__(self, config: AppConfig, scenario: str = "warning") -> None:
        self.config = config
        self.scenario = scenario
        self.host = HostIdentity(id=config.host.id, hostname="demo.example.com")

    async def collect_health(self) -> list[CheckResult]:
        checks = [
            run_timed_check("load", self._load, self.config.timeouts.command_seconds),
            run_timed_check("memory", self._memory, self.config.timeouts.command_seconds),
            run_timed_check("disk", self._disk, self.config.timeouts.command_seconds),
            run_timed_check("systemd", self._systemd, self.config.timeouts.command_seconds),
        ]
        return list(await asyncio.gather(*checks))

    async def _load(self) -> CheckResult:
        started = monotonic()
        facts = {
            "healthy": LoadFacts(load_1m=0.42, load_5m=0.51, load_15m=0.47, cpu_count=8),
            "warning": LoadFacts(load_1m=0.76, load_5m=0.61, load_15m=0.57, cpu_count=8),
            "critical": LoadFacts(load_1m=17.2, load_5m=14.3, load_15m=11.8, cpu_count=8),
            "unknown": LoadFacts(load_1m=0.42, load_5m=0.51, load_15m=0.47, cpu_count=8),
        }[self.scenario]
        return evaluate_load(
            facts,
            self.config.thresholds.load,
            duration_ms=int((monotonic() - started) * 1000),
        )

    async def _memory(self) -> CheckResult:
        started = monotonic()
        usage = {"healthy": 41.0, "warning": 72.0, "critical": 97.0, "unknown": 41.0}[
            self.scenario
        ]
        total = 8 * 1024 * 1024 * 1024
        used = int(total * usage / 100)
        facts = MemoryFacts(
            total_bytes=total,
            used_bytes=used,
            available_bytes=total - used,
            usage_percent=usage,
            swap_total_bytes=2 * 1024 * 1024 * 1024,
            swap_used_bytes=128 * 1024 * 1024,
            swap_usage_percent=6.25,
        )
        return evaluate_memory(
            facts,
            self.config.thresholds.memory,
            duration_ms=int((monotonic() - started) * 1000),
        )

    async def _disk(self) -> CheckResult:
        if self.scenario == "unknown":
            await asyncio.sleep(self.config.timeouts.command_seconds + 0.1)
        started = monotonic()
        usage = {"healthy": 42.0, "warning": 87.0, "critical": 97.0, "unknown": 42.0}[
            self.scenario
        ]
        total = 250 * 1024 * 1024 * 1024
        used = int(total * usage / 100)
        facts = DiskFacts(
            filesystems=[
                FileSystemFacts(
                    filesystem="/dev/sda1",
                    fs_type="ext4",
                    mountpoint="/",
                    total_bytes=total,
                    used_bytes=used,
                    available_bytes=total - used,
                    usage_percent=usage,
                ),
                FileSystemFacts(
                    filesystem="/dev/sdb1",
                    fs_type="ext4",
                    mountpoint="/srv",
                    total_bytes=500 * 1024 * 1024 * 1024,
                    used_bytes=120 * 1024 * 1024 * 1024,
                    available_bytes=380 * 1024 * 1024 * 1024,
                    usage_percent=24.0,
                ),
            ]
        )
        return evaluate_disk(
            facts,
            self.config.thresholds.disk,
            duration_ms=int((monotonic() - started) * 1000),
        )

    async def _systemd(self) -> CheckResult:
        started = monotonic()
        units = [] if self.scenario == "healthy" else ["backup.service"]
        facts = SystemdFacts(failed_count=len(units), failed_units=units)
        return evaluate_systemd(
            facts,
            self.config.thresholds.systemd,
            duration_ms=int((monotonic() - started) * 1000),
        )

    async def collect_snapshot(self) -> list[tuple[str, str]]:
        return [
            ("hostname", self.host.hostname),
            ("date", "Tue Jun 16 15:30:00 UTC 2026"),
            ("uptime", "15:30:00 up 12 days, 3:14, 1 user, load average: 0.76, 0.61, 0.57"),
            ("free -h", "Mem: 8.0Gi 5.8Gi 2.2Gi\nSwap: 2.0Gi 128Mi 1.9Gi"),
            ("df -h", "/dev/sda1 250G 218G 32G 87% /"),
            ("df -i", "/dev/sda1 16M 1.1M 15M 7% /"),
            ("systemctl --failed --no-pager", "backup.service loaded failed failed Demo failure"),
            ("journalctl -p err -n 100 --no-pager", "demo error token=[REDACTED]"),
            ("dmesg --level=err,warn", "demo kernel warning"),
            ("snapshot_path_hint", str(Path(self.config.snapshot.output_directory))),
        ]

