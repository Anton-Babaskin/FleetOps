import pytest

from fleetops.collectors.base import Collector
from fleetops.collectors.demo import DemoCollector


@pytest.mark.asyncio
async def test_demo_collector_matches_interface(app_config) -> None:
    collector: Collector = DemoCollector(app_config)
    checks = await collector.collect_health()
    snapshot = await collector.collect_snapshot()
    assert collector.host.hostname == "demo.example.com"
    assert {check.name for check in checks} == {"load", "memory", "disk", "systemd"}
    assert snapshot

