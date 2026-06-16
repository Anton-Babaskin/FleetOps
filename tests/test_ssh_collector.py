import pytest

from fleetops.collectors.ssh import SSHCollector
from fleetops.config import EnvSettings


def test_ssh_collector_requires_known_hosts(app_config) -> None:
    with pytest.raises(ValueError, match="KNOWN_HOSTS"):
        SSHCollector(app_config, EnvSettings(ssh_known_hosts_path=None))
