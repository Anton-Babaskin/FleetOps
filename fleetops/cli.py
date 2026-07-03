import argparse
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from fleetops.config import AppConfig, EnvSettings
from fleetops.domain.models import CheckResult
from fleetops.interfaces.telegram.bot import run_bot
from fleetops.interfaces.telegram.formatter import (
    format_audit,
    format_check_detail,
    format_docker,
    format_docker_logs,
    format_greylist,
    format_health,
    format_journal,
    format_mail,
    format_mail_delivery,
    format_mail_dns,
    format_mail_logs,
    format_mail_queue,
    format_mail_rejections,
    format_mail_search,
    format_mail_service_logs,
    format_mail_stats,
    format_mail_tls,
    format_ports,
    format_processes,
    format_reboots,
    format_security,
    format_services,
    format_status,
    format_top,
    format_updates,
)
from fleetops.security.redaction import redact
from fleetops.services.diagnostics_service import DiagnosticsService
from fleetops.services.health_service import HealthService
from fleetops.services.snapshot_service import SnapshotService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fleetops",
        description="Agentless Linux, Docker, and mail server diagnostics over SSH.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print JSON for commands that support structured output",
    )
    subparsers = parser.add_subparsers(dest="command")

    time_window_commands = {
        "mail-logs",
        "mail-stats",
        "mail-rejects",
        "mail-delivery",
    }
    search_commands = {
        "mail-search": "any",
        "mail-from": "from",
        "mail-to": "to",
        "mail-ip": "ip",
        "mail-domain": "domain",
    }

    for command in (
        "bot",
        "health",
        "load",
        "memory",
        "disk",
        "systemd",
        "services",
        "journal",
        "ports",
        "docker",
        "docker-logs",
        "mail",
        "mail-dns",
        "mail-tls",
        "mail-logs",
        "mail-stats",
        "mail-rejects",
        "mail-delivery",
        "mail-search",
        "mail-from",
        "mail-to",
        "mail-ip",
        "mail-domain",
        "mail-service-logs",
        "greylist",
        "queue",
        "top",
        "processes",
        "reboots",
        "updates",
        "security",
        "audit",
        "snapshot",
        "status",
    ):
        command_parser = subparsers.add_parser(command)
        if command in time_window_commands:
            command_parser.add_argument(
                "--since",
                help="limit mail log analysis to a window such as 30m, 1h, 24h, or 7d",
            )
        if command in search_commands:
            command_parser.add_argument("query", help="email, domain, IP, or text to search for")
            command_parser.add_argument(
                "--since",
                help="limit mail search to a window such as 30m, 1h, 24h, or 7d",
            )

    return parser


def _find_check(checks: list[CheckResult], name: str) -> CheckResult:
    for check in checks:
        if check.name == name:
            return check
    raise ValueError(f"check not found: {name}")


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


async def run_cli(
    *,
    args: argparse.Namespace,
    config: AppConfig,
    env: EnvSettings,
    diagnostics_service: DiagnosticsService,
    health_service: HealthService,
    snapshot_service: SnapshotService,
) -> int:
    command = args.command or "bot"

    if command == "bot":
        if not env.telegram_bot_token:
            raise ValueError("FLEETOPS_TELEGRAM_BOT_TOKEN is required for bot mode")
        await run_bot(
            token=env.telegram_bot_token,
            config=config,
            demo_mode=env.demo_mode,
            diagnostics_service=diagnostics_service,
            health_service=health_service,
            snapshot_service=snapshot_service,
        )
        return 0

    if command == "health":
        result = await health_service.get_health()
        if args.json:
            print(json.dumps(result.model_dump(mode="json"), indent=2, default=_json_default))
        else:
            print(format_health(result))
        return 0

    if command in {"load", "memory", "disk", "systemd"}:
        result = await health_service.get_health()
        check = _find_check(result.checks, command)
        if args.json:
            print(json.dumps(check.model_dump(mode="json"), indent=2, default=_json_default))
        else:
            print(format_check_detail(check))
        return 0

    diagnostics_commands: dict[str, Callable[[], Awaitable[str]]] = {
        "services": diagnostics_service.get_services,
        "journal": diagnostics_service.get_journal,
        "ports": diagnostics_service.get_ports,
        "docker": diagnostics_service.get_docker,
        "docker-logs": diagnostics_service.get_docker_logs,
        "mail": diagnostics_service.get_mail,
        "mail-dns": diagnostics_service.get_mail_dns,
        "mail-tls": diagnostics_service.get_mail_tls,
        "mail-logs": lambda: diagnostics_service.get_mail_logs(args.since),
        "mail-stats": lambda: diagnostics_service.get_mail_stats(args.since),
        "mail-rejects": lambda: diagnostics_service.get_mail_rejections(args.since),
        "mail-delivery": lambda: diagnostics_service.get_mail_delivery(args.since),
        "mail-service-logs": diagnostics_service.get_mail_service_logs,
        "greylist": diagnostics_service.get_greylist,
        "queue": diagnostics_service.get_mail_queue,
        "top": diagnostics_service.get_top,
        "processes": diagnostics_service.get_processes,
        "reboots": diagnostics_service.get_reboots,
        "updates": diagnostics_service.get_updates,
        "security": diagnostics_service.get_security,
        "audit": diagnostics_service.get_audit,
    }
    formatters = {
        "services": format_services,
        "journal": format_journal,
        "ports": format_ports,
        "docker": format_docker,
        "docker-logs": format_docker_logs,
        "mail": format_mail,
        "mail-dns": format_mail_dns,
        "mail-tls": format_mail_tls,
        "mail-logs": format_mail_logs,
        "mail-stats": format_mail_stats,
        "mail-rejects": format_mail_rejections,
        "mail-delivery": format_mail_delivery,
        "mail-service-logs": format_mail_service_logs,
        "greylist": format_greylist,
        "queue": format_mail_queue,
        "top": format_top,
        "processes": format_processes,
        "reboots": format_reboots,
        "updates": format_updates,
        "security": format_security,
        "audit": format_audit,
    }
    search_modes = {
        "mail-search": "any",
        "mail-from": "from",
        "mail-to": "to",
        "mail-ip": "ip",
        "mail-domain": "domain",
    }
    if command in search_modes:
        mode = search_modes[command]
        raw = await diagnostics_service.get_mail_search(
            mode=mode,
            query=args.query,
            since=args.since,
        )
        if args.json:
            print(
                json.dumps(
                    {
                        "command": command,
                        "mode": mode,
                        "query": args.query,
                        "since": args.since,
                        "output": redact(raw),
                    },
                    indent=2,
                )
            )
        else:
            print(format_mail_search(raw, mode=mode, query=args.query, since=args.since))
        return 0

    if command in diagnostics_commands:
        raw = await diagnostics_commands[command]()
        if args.json:
            print(json.dumps({"command": command, "output": redact(raw)}, indent=2))
        else:
            print(formatters[command](raw))
        return 0

    if command == "snapshot":
        path = await snapshot_service.create_snapshot()
        print(path)
        return 0

    if command == "status":
        print(
            format_status(
                hostname=config.host.hostname,
                host_id=config.host.id,
                demo_mode=env.demo_mode,
                allowed_user_count=len(config.telegram.allowed_user_ids),
                started_at=datetime.now(UTC),
            )
        )
        return 0

    raise ValueError(f"unknown command: {command}")
