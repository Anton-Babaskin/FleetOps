import asyncio
import logging
import sys

from fleetops.collectors.demo import DemoCollector
from fleetops.collectors.ssh import SSHCollector
from fleetops.config import EnvSettings, load_config
from fleetops.interfaces.telegram.bot import run_bot
from fleetops.services.health_service import HealthService
from fleetops.services.snapshot_service import SnapshotService


def build_collector(config, env: EnvSettings):
    if env.demo_mode:
        return DemoCollector(config)
    return SSHCollector(config, env)


async def async_main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    env = EnvSettings()
    try:
        config = load_config(env.config_path)
        if not env.telegram_bot_token:
            raise ValueError("FLEETOPS_TELEGRAM_BOT_TOKEN is required")
        collector = build_collector(config, env)
    except ValueError as exc:
        logging.error("startup failed: %s", exc)
        raise SystemExit(2) from exc

    await run_bot(
        token=env.telegram_bot_token,
        config=config,
        health_service=HealthService(collector),
        snapshot_service=SnapshotService(collector, config.snapshot),
    )


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()

