from typing import Protocol

from fleetops.domain.models import CheckResult, HostIdentity


class Collector(Protocol):
    host: HostIdentity

    async def collect_health(self) -> list[CheckResult]:
        """Collect all health checks through a fixed, read-only command set."""

    async def collect_snapshot(self) -> list[tuple[str, str]]:
        """Collect predefined snapshot sections as title/body pairs."""

    async def collect_services(self) -> str:
        """Collect a bounded service status summary through systemd."""

    async def collect_journal(self) -> str:
        """Collect recent warning/error journal lines with a fixed limit."""

    async def collect_ports(self) -> str:
        """Collect listening TCP/UDP sockets with process names when available."""

    async def collect_docker(self) -> str:
        """Collect Docker container and disk usage summary when Docker is installed."""

    async def collect_docker_deep(self) -> str:
        """Collect bounded Docker health, restart, resource, and disk details."""

    async def collect_mail(self) -> str:
        """Collect common mail service status summary when mail services are installed."""

    async def collect_mail_queue(self) -> str:
        """Collect a bounded mail queue summary when postqueue is installed."""

    async def collect_mail_dns(self) -> str:
        """Collect DNS records relevant for a mail server."""

    async def collect_mail_tls(self) -> str:
        """Collect bounded TLS certificate details for common mail endpoints."""

    async def collect_mail_logs(self, since: str | None = None) -> str:
        """Collect bounded mail delivery, receive, reject, defer, and bounce logs."""

    async def collect_mail_rejections(self, since: str | None = None) -> str:
        """Collect bounded rejected mail flow events."""

    async def collect_mail_delivery(self, since: str | None = None) -> str:
        """Collect bounded sent/deferred/bounced mail flow events."""

    async def collect_mail_stats(self, since: str | None = None) -> str:
        """Collect bounded aggregate Postfix mail flow statistics."""

    async def collect_mail_search(
        self,
        *,
        mode: str,
        query: str,
        since: str | None = None,
    ) -> str:
        """Collect bounded mail flow events matching a fixed search mode."""

    async def collect_mail_service_logs(self) -> str:
        """Collect bounded mail service lifecycle and configuration logs."""

    async def collect_greylist(self) -> str:
        """Collect bounded postgrey statistics and recent greylisting events."""

    async def collect_top(self) -> str:
        """Collect a bounded top snapshot."""

    async def collect_processes(self) -> str:
        """Collect top processes sorted by CPU and memory."""

    async def collect_reboots(self) -> str:
        """Collect reboot and uptime history."""

    async def collect_updates(self) -> str:
        """Collect package update summary when a known package manager is installed."""

    async def collect_security(self) -> str:
        """Collect bounded login, firewall, and security service status."""

    async def collect_docker_logs(self, container: str | None = None) -> str:
        """Collect bounded logs for one selected or a small number of Docker containers."""

    async def collect_audit(self) -> str:
        """Collect a bounded read-only security and mail audit."""

