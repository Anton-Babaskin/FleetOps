from datetime import UTC, datetime
from time import monotonic

from fleetops.collectors.base import Collector
from fleetops.domain.models import HealthResult


class HealthService:
    def __init__(self, collector: Collector) -> None:
        self.collector = collector

    async def get_health(self) -> HealthResult:
        started = monotonic()
        collected_at = datetime.now(UTC)
        checks = await self.collector.collect_health()
        return HealthResult.from_checks(
            host=self.collector.host,
            collected_at=collected_at,
            duration_ms=int((monotonic() - started) * 1000),
            checks=checks,
        )

