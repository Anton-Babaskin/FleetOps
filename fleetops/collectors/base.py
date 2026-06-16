from typing import Protocol

from fleetops.domain.models import CheckResult, HostIdentity


class Collector(Protocol):
    host: HostIdentity

    async def collect_health(self) -> list[CheckResult]:
        """Collect all health checks through a fixed, read-only command set."""

    async def collect_snapshot(self) -> list[tuple[str, str]]:
        """Collect predefined snapshot sections as title/body pairs."""

