from types import SimpleNamespace

import pytest

from fleetops.collectors.ssh import SSHCollector, SSHCommandError
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


@pytest.mark.asyncio
async def test_report_command_does_not_hide_nonzero_exit(app_config, tmp_path) -> None:
    class FakeConnection:
        async def run(self, *args, **kwargs):
            return SimpleNamespace(exit_status=1, stdout="partial output", stderr="failed")

    collector = SSHCollector(
        app_config,
        EnvSettings(ssh_known_hosts_path=tmp_path / "known_hosts"),
    )

    with pytest.raises(SSHCommandError, match="exit status 1"):
        await collector._run_report(FakeConnection(), "probe")
