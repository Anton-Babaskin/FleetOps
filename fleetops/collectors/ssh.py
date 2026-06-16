import asyncio
from collections.abc import Awaitable, Callable
from time import monotonic

import asyncssh

from fleetops.checks.disk import parse_df
from fleetops.checks.load import parse_loadavg
from fleetops.checks.memory import parse_meminfo
from fleetops.checks.systemd import parse_systemctl_failed
from fleetops.config import AppConfig, EnvSettings
from fleetops.domain.models import CheckResult, HostIdentity
from fleetops.rules.health import (
    evaluate_disk,
    evaluate_load,
    evaluate_memory,
    evaluate_systemd,
    run_timed_check,
    unknown_check,
)


class SSHCommandError(RuntimeError):
    pass


class SSHCollector:
    def __init__(self, config: AppConfig, env: EnvSettings) -> None:
        if env.ssh_known_hosts_path is None:
            raise ValueError("FLEETOPS_SSH_KNOWN_HOSTS_PATH is required for SSH mode")
        self.config = config
        self.env = env
        self.host = HostIdentity(id=config.host.id, hostname=config.host.hostname)

    async def collect_health(self) -> list[CheckResult]:
        try:
            conn = await self._connect()
        except Exception as exc:
            return [
                unknown_check(
                    name=name,
                    summary=f"{name.capitalize()} check failed",
                    error=f"SSH connection failed: {type(exc).__name__}: {exc}",
                    duration_ms=0,
                )
                for name in ("load", "memory", "disk", "systemd")
            ]
        async with conn:
            checks = [
                run_timed_check(
                    "load",
                    lambda: self._load(conn),
                    self.config.timeouts.command_seconds,
                ),
                run_timed_check(
                    "memory",
                    lambda: self._memory(conn),
                    self.config.timeouts.command_seconds,
                ),
                run_timed_check(
                    "disk",
                    lambda: self._disk(conn),
                    self.config.timeouts.command_seconds,
                ),
                run_timed_check(
                    "systemd",
                    lambda: self._systemd(conn),
                    self.config.timeouts.command_seconds,
                ),
            ]
            return list(await asyncio.gather(*checks))

    async def collect_snapshot(self) -> list[tuple[str, str]]:
        commands = [
            "hostname",
            "date",
            "uptime",
            "free -h",
            "df -h",
            "df -i",
            "systemctl --failed --no-pager",
            "journalctl -p err -n 100 --no-pager",
            "dmesg --level=err,warn",
        ]
        sections: list[tuple[str, str]] = []
        try:
            conn = await self._connect()
        except Exception as exc:
            return [("ssh connection", f"ERROR: {type(exc).__name__}: {exc}")]
        async with conn:
            for command in commands:
                try:
                    output = await self._run(conn, command)
                except Exception as exc:
                    output = f"ERROR: {type(exc).__name__}: {exc}"
                sections.append((command, output))
        return sections

    async def _connect(self) -> asyncssh.SSHClientConnection:
        kwargs = {
            "host": self.config.host.hostname,
            "port": self.config.host.port,
            "username": self.config.host.username,
            "known_hosts": str(self.env.ssh_known_hosts_path),
            "login_timeout": self.config.timeouts.connection_seconds,
        }
        if self.env.ssh_private_key_path is not None:
            kwargs["client_keys"] = [str(self.env.ssh_private_key_path)]
        return await asyncssh.connect(**kwargs)

    async def _run(self, conn: asyncssh.SSHClientConnection, command: str) -> str:
        result = await conn.run(command, check=False, timeout=self.config.timeouts.command_seconds)
        if result.exit_status != 0:
            stderr = result.stderr.strip() or "remote command failed"
            raise SSHCommandError(stderr[:500])
        return result.stdout

    async def _timed_parse(
        self,
        conn: asyncssh.SSHClientConnection,
        command: str,
        parser: Callable[[str], CheckResult] | Callable[[str], Awaitable[CheckResult]],
    ) -> CheckResult:
        started = monotonic()
        output = await self._run(conn, command)
        parsed = parser(output)
        if asyncio.iscoroutine(parsed):
            parsed = await parsed
        parsed.duration_ms = int((monotonic() - started) * 1000)
        return parsed

    async def _load(self, conn: asyncssh.SSHClientConnection) -> CheckResult:
        started = monotonic()
        loadavg = await self._run(conn, "cat /proc/loadavg")
        nproc = await self._run(conn, "nproc")
        result = evaluate_load(parse_loadavg(loadavg, nproc), self.config.thresholds.load)
        result.duration_ms = int((monotonic() - started) * 1000)
        return result

    async def _memory(self, conn: asyncssh.SSHClientConnection) -> CheckResult:
        return await self._timed_parse(
            conn,
            "cat /proc/meminfo",
            lambda output: evaluate_memory(parse_meminfo(output), self.config.thresholds.memory),
        )

    async def _disk(self, conn: asyncssh.SSHClientConnection) -> CheckResult:
        return await self._timed_parse(
            conn,
            "df -B1 -PT",
            lambda output: evaluate_disk(parse_df(output), self.config.thresholds.disk),
        )

    async def _systemd(self, conn: asyncssh.SSHClientConnection) -> CheckResult:
        return await self._timed_parse(
            conn,
            "systemctl --failed --no-legend --no-pager",
            lambda output: evaluate_systemd(
                parse_systemctl_failed(output),
                self.config.thresholds.systemd,
            ),
        )
