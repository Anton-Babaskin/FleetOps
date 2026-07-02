import asyncio
from pathlib import Path
from time import monotonic

from fleetops.checks.disk import DiskFacts, FileSystemFacts
from fleetops.checks.load import LoadFacts
from fleetops.checks.memory import MemoryFacts
from fleetops.checks.systemd import SystemdFacts
from fleetops.config import AppConfig
from fleetops.domain.models import CheckResult, HostIdentity
from fleetops.rules.health import (
    evaluate_disk,
    evaluate_load,
    evaluate_memory,
    evaluate_systemd,
    run_timed_check,
)


class DemoCollector:
    def __init__(self, config: AppConfig, scenario: str = "warning") -> None:
        self.config = config
        self.scenario = scenario
        self.host = HostIdentity(id=config.host.id, hostname="demo.example.com")

    async def collect_health(self) -> list[CheckResult]:
        checks = [
            run_timed_check("load", self._load, self.config.timeouts.command_seconds),
            run_timed_check("memory", self._memory, self.config.timeouts.command_seconds),
            run_timed_check("disk", self._disk, self.config.timeouts.command_seconds),
            run_timed_check("systemd", self._systemd, self.config.timeouts.command_seconds),
        ]
        return list(await asyncio.gather(*checks))

    async def _load(self) -> CheckResult:
        started = monotonic()
        facts = {
            "healthy": LoadFacts(load_1m=0.42, load_5m=0.51, load_15m=0.47, cpu_count=8),
            "warning": LoadFacts(load_1m=0.76, load_5m=0.61, load_15m=0.57, cpu_count=8),
            "critical": LoadFacts(load_1m=17.2, load_5m=14.3, load_15m=11.8, cpu_count=8),
            "unknown": LoadFacts(load_1m=0.42, load_5m=0.51, load_15m=0.47, cpu_count=8),
        }[self.scenario]
        return evaluate_load(
            facts,
            self.config.thresholds.load,
            duration_ms=int((monotonic() - started) * 1000),
        )

    async def _memory(self) -> CheckResult:
        started = monotonic()
        usage = {"healthy": 41.0, "warning": 72.0, "critical": 97.0, "unknown": 41.0}[
            self.scenario
        ]
        total = 8 * 1024 * 1024 * 1024
        used = int(total * usage / 100)
        facts = MemoryFacts(
            total_bytes=total,
            used_bytes=used,
            available_bytes=total - used,
            usage_percent=usage,
            swap_total_bytes=2 * 1024 * 1024 * 1024,
            swap_used_bytes=128 * 1024 * 1024,
            swap_usage_percent=6.25,
        )
        return evaluate_memory(
            facts,
            self.config.thresholds.memory,
            duration_ms=int((monotonic() - started) * 1000),
        )

    async def _disk(self) -> CheckResult:
        if self.scenario == "unknown":
            await asyncio.sleep(self.config.timeouts.command_seconds + 0.1)
        started = monotonic()
        usage = {"healthy": 42.0, "warning": 87.0, "critical": 97.0, "unknown": 42.0}[
            self.scenario
        ]
        total = 250 * 1024 * 1024 * 1024
        used = int(total * usage / 100)
        facts = DiskFacts(
            filesystems=[
                FileSystemFacts(
                    filesystem="/dev/sda1",
                    fs_type="ext4",
                    mountpoint="/",
                    total_bytes=total,
                    used_bytes=used,
                    available_bytes=total - used,
                    usage_percent=usage,
                ),
                FileSystemFacts(
                    filesystem="/dev/sdb1",
                    fs_type="ext4",
                    mountpoint="/srv",
                    total_bytes=500 * 1024 * 1024 * 1024,
                    used_bytes=120 * 1024 * 1024 * 1024,
                    available_bytes=380 * 1024 * 1024 * 1024,
                    usage_percent=24.0,
                ),
            ]
        )
        return evaluate_disk(
            facts,
            self.config.thresholds.disk,
            duration_ms=int((monotonic() - started) * 1000),
        )

    async def _systemd(self) -> CheckResult:
        started = monotonic()
        units = [] if self.scenario == "healthy" else ["backup.service"]
        facts = SystemdFacts(failed_count=len(units), failed_units=units)
        return evaluate_systemd(
            facts,
            self.config.thresholds.systemd,
            duration_ms=int((monotonic() - started) * 1000),
        )

    async def collect_snapshot(self) -> list[tuple[str, str]]:
        return [
            ("hostname", self.host.hostname),
            ("date", "Tue Jun 16 15:30:00 UTC 2026"),
            ("uptime", "15:30:00 up 12 days, 3:14, 1 user, load average: 0.76, 0.61, 0.57"),
            ("free -h", "Mem: 8.0Gi 5.8Gi 2.2Gi\nSwap: 2.0Gi 128Mi 1.9Gi"),
            ("df -h", "/dev/sda1 250G 218G 32G 87% /"),
            ("df -i", "/dev/sda1 16M 1.1M 15M 7% /"),
            ("systemctl --failed --no-pager", "backup.service loaded failed failed Demo failure"),
            ("journalctl -p err -n 100 --no-pager", "demo error token=[REDACTED]"),
            ("dmesg --level=err,warn", "demo kernel warning"),
            ("snapshot_path_hint", str(Path(self.config.snapshot.output_directory))),
        ]

    async def collect_services(self) -> str:
        return "\n".join(
            [
                "ssh.service loaded active running OpenBSD Secure Shell server",
                "cron.service loaded active running Regular background program processing daemon",
                "backup.service loaded failed failed Demo backup failure",
            ]
        )

    async def collect_journal(self) -> str:
        return "\n".join(
            [
                "2026-06-16T15:29:50Z demo-server kernel: demo warning",
                "2026-06-16T15:29:55Z demo-server app: token=[REDACTED]",
            ]
        )

    async def collect_ports(self) -> str:
        return "\n".join(
            [
                "tcp LISTEN 0 4096 0.0.0.0:22 0.0.0.0:* users:((\"sshd\",pid=100,fd=3))",
                "tcp LISTEN 0 4096 0.0.0.0:443 0.0.0.0:* users:((\"nginx\",pid=200,fd=6))",
                "udp UNCONN 0 0 127.0.0.53:53 0.0.0.0:* users:((\"systemd-resolve\",pid=50,fd=12))",
            ]
        )

    async def collect_docker(self) -> str:
        return "\n".join(
            [
                "## docker ps",
                "NAMES STATUS PORTS",
                "api Up 2 hours 127.0.0.1:8000->8000/tcp",
                "",
                "## docker system df",
                "TYPE TOTAL ACTIVE SIZE RECLAIMABLE",
                "Images 3 2 1.2GB 300MB (25%)",
            ]
        )

    async def collect_mail(self) -> str:
        return "\n".join(
            [
                "postfix.service active",
                "dovecot.service active",
                "nginx.service active",
                "opendkim.service active",
            ]
        )

    async def collect_mail_queue(self) -> str:
        return "Mail queue is empty"

    async def collect_mail_dns(self) -> str:
        return "\n".join(
            [
                "## identity",
                "hostname=mail.example.com",
                "postfix_mydomain=example.com",
                "",
                "## DNS",
                "### example.com",
                "MX:",
                "10 mail.example.com.",
                "SPF:",
                '"v=spf1 mx -all"',
                "DMARC:",
                '"v=DMARC1; p=quarantine"',
            ]
        )

    async def collect_mail_tls(self) -> str:
        return "\n".join(
            [
                "## mail.example.com",
                "### TLS port 993",
                "subject=CN = mail.example.com",
                "notBefore=Jul 1 00:00:00 2026 GMT",
                "notAfter=Sep 29 00:00:00 2026 GMT",
            ]
        )

    async def collect_mail_logs(self) -> str:
        return "\n".join(
            [
                "postfix/smtp[124]: ABC123: to=<user@example.com>, status=sent",
                "postfix/smtpd[125]: NOQUEUE: reject: RCPT from bad.example[203.0.113.66]",
            ]
        )

    async def collect_mail_rejections(self) -> str:
        return (
            "postfix/smtpd[125]: NOQUEUE: reject: RCPT from bad.example[203.0.113.66]: "
            "554 5.7.1 <user@example.com>: Relay access denied; "
            "from=<bad@sender.test> to=<user@example.com> proto=ESMTP helo=<bad.example>"
        )

    async def collect_mail_delivery(self) -> str:
        return (
            "postfix/smtp[124]: ABC123: to=<user@example.com>, "
            "relay=mx.example.com[203.0.113.25]:25, status=sent (250 2.0.0 ok)"
        )

    async def collect_mail_stats(self) -> str:
        return "\n".join(
            [
                "== MAIL STATS SUMMARY ==",
                "sent=42",
                "deferred=3",
                "bounced=1",
                "rejected=9",
                "greylisted=4",
                "from_domains=5",
                "to_domains=7",
                "",
                "== TOP FROM DOMAINS ==",
                "18 example.org",
                "12 sender.test",
                "",
                "== TOP TO DOMAINS ==",
                "24 example.com",
                "8 gmail.com",
                "",
                "== TOP ROUTES ==",
                "10 example.org -> example.com -> 127.0.0.1",
                "",
                "== TOP RELAYS ==",
                "30 127.0.0.1",
                "",
                "== TOP REJECT REASONS ==",
                "5 Relay access denied",
                "4 Greylisted",
                "",
                "== TOP VOLUME FROM DOMAINS ==",
                "2.4 MB 18 example.org",
            ]
        )

    async def collect_mail_service_logs(self) -> str:
        return "2026-06-16T15:29:55Z demo postfix/smtp[123]: status=sent"

    async def collect_greylist(self) -> str:
        return "\n".join(
            [
                "== GREYLIST SUMMARY ==",
                "greylisted=12",
                "passed=8",
                "rejected=0",
                "whitelisted=2",
                "",
                "== TOP CLIENT IPs ==",
                "  7 203.0.113.10",
                "",
                "== RECENT EVENTS ==",
                "postgrey[123]: action=greylist, client_address=203.0.113.10, sender=a@test",
            ]
        )

    async def collect_top(self) -> str:
        return "\n".join(
            [
                "top - 15:30:00 up 12 days, 3:14, 1 user, load average: 0.76, 0.61, 0.57",
                "Tasks: 112 total, 1 running, 111 sleeping",
                "%Cpu(s): 4.1 us, 1.2 sy, 94.7 id",
                "MiB Mem : 8192 total, 1800 free, 5900 used, 492 buff/cache",
            ]
        )

    async def collect_processes(self) -> str:
        return "\n".join(
            [
                "## CPU",
                "PID PPID USER STAT %CPU %MEM ELAPSED COMMAND",
                "200 1 root S 12.5 3.1 01:20:14 python",
                "",
                "## Memory",
                "PID PPID USER STAT %CPU %MEM ELAPSED COMMAND",
                "300 1 postgres S 2.1 14.2 2-03:10 postgres",
            ]
        )

    async def collect_reboots(self) -> str:
        return "system boot 2026-06-04 08:00\nup 12 days, 3 hours"

    async def collect_updates(self) -> str:
        return "Listing...\nopenssl/jammy-updates 3.0.2-0ubuntu1 amd64 [upgradable]"

    async def collect_security(self) -> str:
        return "\n".join(
            [
                "## sessions",
                "fleetops pts/0 2026-06-16 15:10",
                "",
                "## firewall/services",
                "ufw.service active",
                "fail2ban.service active",
            ]
        )

    async def collect_docker_logs(self) -> str:
        return "## api\nINFO demo request completed\nWARNING token=[REDACTED]"

    async def collect_audit(self) -> str:
        return "\n".join(
            [
                "== AUDIT CONTEXT ==",
                "[PASS] hostname looks like FQDN",
                "[WARN] demo package updates are pending: 3",
                "",
                "== SSHD CONFIG ==",
                "[CRITICAL] SSH root login and password authentication are both enabled",
                "[WARN] SSH X11Forwarding=yes",
                "",
                "== MAIL RELAY ==",
                "[PASS] Postfix reject_unauth_destination is present",
                "[PASS] Postfix mynetworks does not include 0.0.0.0/0 or ::/0",
                "",
                "== SUMMARY ==",
                "PASS: 3",
                "INFO: 0",
                "WARN: 2",
                "CRITICAL: 1",
                "RESULT: CRITICAL",
            ]
        )

