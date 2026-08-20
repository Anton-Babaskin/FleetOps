import asyncio
import logging
import sys

from fleetops.cli import build_parser, run_cli
from fleetops.collectors.demo import DemoCollector
from fleetops.collectors.ssh import SSHCollector
from fleetops.config import EnvSettings, load_config
from fleetops.services.diagnostics_service import DiagnosticsService
from fleetops.services.health_service import HealthService
from fleetops.services.snapshot_service import SnapshotService


def build_collector(config, env: EnvSettings):
    if env.demo_mode:
        return DemoCollector(config)
    return SSHCollector(config, env)


async def async_main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = build_parser().parse_args(argv)
    env = EnvSettings()
    try:
        config = load_config(env.config_path)
        collector = build_collector(config, env)
    except ValueError as exc:
        logging.error("startup failed: %s", exc)
        raise SystemExit(2) from exc

    try:
        return await run_cli(
            args=args,
            config=config,
            diagnostics_service=DiagnosticsService(collector),
            health_service=HealthService(collector),
            snapshot_service=SnapshotService(collector, config.snapshot),
            env=env,
        )
    except ValueError as exc:
        logging.error("command failed: %s", exc)
        return 2


def main() -> None:
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        raise SystemExit(asyncio.run(async_main()))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()

