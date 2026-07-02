import pytest

from fleetops.collectors.ssh import SSHCollector
from fleetops.config import EnvSettings


def test_ssh_collector_requires_known_hosts(app_config) -> None:
    with pytest.raises(ValueError, match="KNOWN_HOSTS"):
        SSHCollector(app_config, EnvSettings(ssh_known_hosts_path=None))


@pytest.mark.asyncio
async def test_ssh_collector_passes_password(monkeypatch, app_config, tmp_path) -> None:
    captured = {}

    async def fake_connect(**kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop before network")

    monkeypatch.setattr("fleetops.collectors.ssh.asyncssh.connect", fake_connect)
    collector = SSHCollector(
        app_config,
        EnvSettings(ssh_known_hosts_path=tmp_path / "known_hosts", ssh_password="secret"),
    )

    with pytest.raises(RuntimeError, match="stop before network"):
        await collector._connect()

    assert captured["password"] == "secret"
