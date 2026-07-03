import asyncio
from datetime import UTC, datetime

from fleetops.collectors.base import Collector
from fleetops.domain.models import HealthResult

SINCE_UNITS = {"m", "h", "d"}


def normalize_since(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    if len(normalized) < 2 or normalized[-1] not in SINCE_UNITS:
        raise ValueError("since must look like 30m, 1h, 24h, or 7d")
    amount = normalized[:-1]
    if not amount.isdigit() or int(amount) <= 0:
        raise ValueError("since must use a positive number")
    return normalized


class DiagnosticsService:
    def __init__(self, collector: Collector) -> None:
        self.collector = collector

    async def get_services(self) -> str:
        return await self.collector.collect_services()

    async def get_journal(self) -> str:
        return await self.collector.collect_journal()

    async def get_ports(self) -> str:
        return await self.collector.collect_ports()

    async def get_docker(self) -> str:
        return await self.collector.collect_docker()

    async def get_mail(self) -> str:
        return await self.collector.collect_mail()

    async def get_mail_queue(self) -> str:
        return await self.collector.collect_mail_queue()

    async def get_mail_dns(self) -> str:
        return await self.collector.collect_mail_dns()

    async def get_mail_tls(self) -> str:
        return await self.collector.collect_mail_tls()

    async def get_mail_logs(self, since: str | None = None) -> str:
        return await self.collector.collect_mail_logs(normalize_since(since))

    async def get_mail_rejections(self, since: str | None = None) -> str:
        return await self.collector.collect_mail_rejections(normalize_since(since))

    async def get_mail_delivery(self, since: str | None = None) -> str:
        return await self.collector.collect_mail_delivery(normalize_since(since))

    async def get_mail_stats(self, since: str | None = None) -> str:
        return await self.collector.collect_mail_stats(normalize_since(since))

    async def get_mail_search(
        self,
        *,
        mode: str,
        query: str,
        since: str | None = None,
    ) -> str:
        cleaned_query = query.strip()
        if not cleaned_query:
            raise ValueError("mail search query is required")
        if mode not in {"any", "from", "to", "ip", "domain"}:
            raise ValueError("unsupported mail search mode")
        return await self.collector.collect_mail_search(
            mode=mode,
            query=cleaned_query,
            since=normalize_since(since),
        )

    async def get_mail_service_logs(self) -> str:
        return await self.collector.collect_mail_service_logs()

    async def get_greylist(self) -> str:
        return await self.collector.collect_greylist()

    async def get_top(self) -> str:
        return await self.collector.collect_top()

    async def get_processes(self) -> str:
        return await self.collector.collect_processes()

    async def get_reboots(self) -> str:
        return await self.collector.collect_reboots()

    async def get_updates(self) -> str:
        return await self.collector.collect_updates()

    async def get_security(self) -> str:
        return await self.collector.collect_security()

    async def get_docker_logs(self) -> str:
        return await self.collector.collect_docker_logs()

    async def get_audit(self) -> str:
        return await self.collector.collect_audit()

    async def get_incident(self, since: str | None = "24h") -> str:
        normalized_since = normalize_since(since) or "24h"
        started_at = datetime.now(UTC)
        health_checks = await self.collector.collect_health()
        health = HealthResult.from_checks(
            host=self.collector.host,
            collected_at=started_at,
            duration_ms=0,
            checks=health_checks,
        )

        async def safe_collect(label: str, awaitable) -> tuple[str, str]:
            try:
                return label, await awaitable
            except Exception as exc:
                return label, f"ERROR: {type(exc).__name__}: {exc}"

        mail_stats = await safe_collect(
            "MAIL_STATS",
            self.collector.collect_mail_stats(normalized_since),
        )
        queue = await safe_collect("QUEUE", self.collector.collect_mail_queue())
        sections = await asyncio.gather(
            safe_collect("SERVICES", self.collector.collect_services()),
            safe_collect("PORTS", self.collector.collect_ports()),
            safe_collect("TOP", self.collector.collect_top()),
            safe_collect("SECURITY", self.collector.collect_security()),
        )

        lines = [
            "### INCIDENT SUMMARY",
            f"host={health.host.id} ({health.host.hostname})",
            f"overall={health.overall_status.value}",
            f"since={normalized_since}",
            f"collected_at={started_at.isoformat()}",
            "",
            "### HEALTH CHECKS",
        ]
        lines.extend(
            f"{check.name}|{check.status.value}|{check.summary}"
            for check in health.checks
        )
        for label, body in [*sections, mail_stats, queue]:
            lines.extend(["", f"### {label}", body.strip()])
        return "\n".join(lines)
