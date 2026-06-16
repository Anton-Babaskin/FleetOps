import asyncio

import pytest

from fleetops.collectors.demo import DemoCollector
from fleetops.domain.statuses import Status
from fleetops.rules.health import run_timed_check


@pytest.mark.asyncio
async def test_timeout_becomes_unknown() -> None:
    async def slow():
        await asyncio.sleep(1)

    result = await run_timed_check("disk", slow, 0.01)
    assert result.status == Status.UNKNOWN
    assert result.timed_out is True
    assert result.error == "timeout after 0.01s"


@pytest.mark.asyncio
async def test_failed_check_kept_in_health(app_config) -> None:
    collector = DemoCollector(app_config, scenario="unknown")
    checks = await collector.collect_health()
    disk = next(check for check in checks if check.name == "disk")
    assert disk.status == Status.UNKNOWN
    assert len(checks) == 4

