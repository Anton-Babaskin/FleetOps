from datetime import UTC, datetime, timedelta
from pathlib import Path

from fleetops.collectors.base import Collector
from fleetops.config import SnapshotConfig
from fleetops.security.redaction import redact


class SnapshotService:
    def __init__(self, collector: Collector, config: SnapshotConfig) -> None:
        self.collector = collector
        self.config = config

    async def create_snapshot(self) -> Path:
        self.config.output_directory.mkdir(parents=True, exist_ok=True)
        self.cleanup_old_snapshots()
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        filename = f"fleetops-{self.collector.host.id}-{timestamp}.snapshot.txt"
        path = self.config.output_directory / filename
        sections = await self.collector.collect_snapshot()
        lines = [
            f"FleetOps snapshot for {self.collector.host.hostname}",
            f"Collected at: {timestamp}",
            "",
        ]
        for title, body in sections:
            lines.extend([f"## {title}", redact(body), ""])
        path.write_text("\n".join(lines), encoding="utf-8")
        path.chmod(0o600)
        return path

    def cleanup_old_snapshots(self) -> None:
        if not self.config.output_directory.exists():
            return
        cutoff = datetime.now(UTC) - timedelta(hours=self.config.retention_hours)
        for path in self.config.output_directory.glob("*.snapshot.txt"):
            modified = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            if modified < cutoff:
                path.unlink(missing_ok=True)
