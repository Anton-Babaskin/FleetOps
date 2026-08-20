import pytest

from fleetops.collectors.demo import DemoCollector
from fleetops.config import SnapshotConfig
from fleetops.domain.models import HostIdentity
from fleetops.services.snapshot_service import SnapshotService


@pytest.mark.asyncio
async def test_snapshot_filename_sanitizes_host_id(app_config, tmp_path) -> None:
    collector = DemoCollector(app_config)
    collector.host = HostIdentity(id="../../mail box", hostname="mail.example.com")
    service = SnapshotService(
        collector,
        SnapshotConfig(output_directory=tmp_path, retention_hours=24),
    )

    path = await service.create_snapshot()

    assert path.parent == tmp_path
    assert path.name.startswith("fleetops-mail-box-")
