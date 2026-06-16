import pytest

from fleetops.config import AppConfig


@pytest.fixture
def app_config() -> AppConfig:
    return AppConfig.model_validate(
        {
            "host": {
                "id": "demo-server",
                "hostname": "server.example.com",
                "port": 22,
                "username": "fleetops",
            },
            "telegram": {"allowed_user_ids": [123456789]},
            "thresholds": {
                "load": {"warning_per_cpu": 1.0, "critical_per_cpu": 2.0},
                "memory": {"warning_percent": 80, "critical_percent": 95},
                "disk": {"warning_percent": 85, "critical_percent": 95},
                "systemd": {"critical_on_failed": False},
            },
            "timeouts": {"connection_seconds": 10, "command_seconds": 0.01},
            "snapshot": {"output_directory": "snapshots-test", "retention_hours": 24},
        }
    )
