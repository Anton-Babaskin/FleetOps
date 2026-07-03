from datetime import UTC, datetime

from fleetops.domain.models import CheckResult, HealthResult, HostIdentity
from fleetops.domain.statuses import Status
from fleetops.interfaces.telegram.formatter import (
    format_audit,
    format_check_detail,
    format_docker,
    format_greylist,
    format_health,
    format_incident,
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
    format_ports_detail,
    format_processes,
    format_services,
    format_services_detail,
    format_status,
    format_updates,
)


def test_formatter_escapes_html() -> None:
    result = HealthResult.from_checks(
        host=HostIdentity(id="demo-server", hostname="demo.example.com"),
        collected_at=datetime.now(UTC),
        duration_ms=42,
        checks=[
            CheckResult(
                name="disk",
                status=Status.WARNING,
                summary="/home <tag> is 87% full",
                duration_ms=1,
            )
        ],
    )
    text = format_health(result)
    assert "🟡 WARNING overall" in text
    assert "&lt;tag&gt;" in text


def test_status_formatter_escapes_html() -> None:
    text = format_status(
        hostname="prod <host>",
        host_id="mailbox",
        demo_mode=False,
        allowed_user_count=1,
        started_at=datetime.now(UTC),
    )

    assert "Mode: 🔐 ssh" in text
    assert "prod &lt;host&gt;" in text


def test_check_detail_formats_memory_metrics() -> None:
    text = format_check_detail(
        CheckResult(
            name="memory",
            status=Status.OK,
            summary="11% used",
            metrics={
                "total_bytes": 8 * 1024 * 1024 * 1024,
                "used_bytes": 1024 * 1024 * 1024,
                "available_bytes": 7 * 1024 * 1024 * 1024,
                "usage_percent": 12.5,
                "swap_total_bytes": 2 * 1024 * 1024 * 1024,
                "swap_used_bytes": 0,
                "swap_usage_percent": 0,
            },
            duration_ms=7,
        )
    )

    assert "Memory detail" in text
    assert "Used: 1.0 GiB / 8.0 GiB (12.5%)" in text
    assert "Swap: 0.0 B / 2.0 GiB (0%)" in text


def test_check_detail_formats_disk_metrics_by_usage() -> None:
    text = format_check_detail(
        CheckResult(
            name="disk",
            status=Status.WARNING,
            summary="/var is 88% full",
            metrics={
                "filesystems": [
                    {
                        "mountpoint": "/",
                        "usage_percent": 20,
                        "available_bytes": 80 * 1024 * 1024 * 1024,
                        "fs_type": "ext4",
                    },
                    {
                        "mountpoint": "/var",
                        "usage_percent": 88,
                        "available_bytes": 12 * 1024 * 1024 * 1024,
                        "fs_type": "ext4",
                    },
                ]
            },
            reason="Disk usage exceeded warning threshold of 85%",
            duration_ms=12,
        )
    )

    assert "Disk detail" in text
    assert text.index("/var") < text.index("/:")
    assert "12.0 GiB free" in text


def test_services_formatter_summarizes_failed_units() -> None:
    text = format_services(
        "\n".join(
            [
                "ssh.service loaded active running OpenBSD Secure Shell server",
                "cron.service loaded active running Regular background daemon",
                "backup.service loaded failed failed Backup failed",
            ]
        )
    )

    assert "Running: 2" in text
    assert "Failed: 1" in text
    assert "backup.service" in text


def test_services_detail_includes_raw_service_output() -> None:
    text = format_services_detail("ssh.service loaded active running SSH")

    assert "Services detail" in text
    assert "ssh.service loaded active running SSH" in text


def test_journal_formatter_redacts_and_limits_lines() -> None:
    raw = "\n".join(
        [
            "line 1",
            "line 2 password=super-secret",
            "line 3",
        ]
    )

    text = format_journal(raw, max_lines=2)

    assert "Showing 2 of 3" in text
    assert "line 1" not in text
    assert "password=[REDACTED]" in text
    assert "super-secret" not in text


def test_ports_formatter_summarizes_socket_types() -> None:
    text = format_ports(
        "\n".join(
            [
                'tcp LISTEN 0 4096 0.0.0.0:22 0.0.0.0:* users:(("sshd",pid=1,fd=3))',
                'udp UNCONN 0 0 127.0.0.53:53 0.0.0.0:* users:(("systemd",pid=2,fd=4))',
            ]
        )
    )

    assert "TCP sockets: 1" in text
    assert "UDP sockets: 1" in text
    assert "0.0.0.0:22" in text


def test_ports_detail_includes_loopback_sockets() -> None:
    text = format_ports_detail(
        'tcp LISTEN 0 4096 127.0.0.1:5432 0.0.0.0:* users:(("postgres",pid=1,fd=3))'
    )

    assert "Ports detail" in text
    assert "127.0.0.1:5432" in text


def test_mail_formatter_groups_active_and_inactive_services() -> None:
    text = format_mail("postfix.service active\ndovecot.service inactive\nnginx.service active")

    assert "📮 Mail services" in text
    assert "🟢 Active: 2" in text
    assert "Needs attention: 1" in text
    assert "dovecot.service inactive" in text


def test_mail_queue_formatter_detects_empty_queue() -> None:
    text = format_mail_queue("Mail queue is empty")

    assert "✅ Mail queue is empty." in text


def test_mail_dns_formatter_redacts_raw_output() -> None:
    text = format_mail_dns("token=secret\nMX:\n10 mail.example.com.")

    assert "🧭 Mail DNS" in text
    assert "token=[REDACTED]" in text
    assert "secret" not in text


def test_mail_tls_formatter_marks_certificate_output() -> None:
    text = format_mail_tls("subject=CN = mail.example.com\nnotAfter=Sep 29 00:00:00 2026 GMT")

    assert "🔐 Mail TLS" in text
    assert "🟢 Certificate data collected." in text


def test_mail_logs_formatter_has_title() -> None:
    text = format_mail_logs(
        "\n".join(
            [
                "postfix/smtp[123]: ABC123: to=<user@example.com>, status=sent (250 ok)",
                (
                    "postfix/smtpd[124]: NOQUEUE: reject: RCPT from "
                    "bad.example[203.0.113.66]: 554 5.7.1 <user@example.com>: "
                    "Relay access denied; from=<bad@sender.test> "
                    "to=<user@example.com> proto=ESMTP helo=<bad.example>"
                ),
            ]
        )
    )

    assert "Mail flow" in text
    assert "Sent: 1" in text
    assert "Rejected: 1" in text
    assert "Delivered" in text
    assert "Relay access denied" in text


def test_mail_rejections_formatter_parses_reject_cards() -> None:
    text = format_mail_rejections(
        "Jul  1 10:04:01 box.example postfix/smtpd[125]: NOQUEUE: reject: "
        "RCPT from mta26.smrtsmg.com[212.2.200.25]: 450 4.2.0 "
        "<user@example.com>: Recipient address rejected: Greylisted; "
        "from=<sender@example.net> to=<user@example.com> proto=ESMTP "
        "helo=<mta26.smrtsmg.com>"
    )

    assert "Mail rejections" in text
    assert "Greylisted @ box.example" in text
    assert "To: user@example.com" in text
    assert "From: sender@example.net" in text
    assert "Client: mta26.smrtsmg.com[212.2.200.25]" in text
    assert "Recipient address rejected: Greylisted" in text


def test_mail_delivery_formatter_parses_delivery_cards() -> None:
    text = format_mail_delivery(
        "Jul  1 10:05:01 box.example postfix/smtp[126]: ABC123: "
        "to=<user@example.com>, relay=mx.example.com[203.0.113.25]:25, "
        "delay=1.2, status=deferred (connect timed out)"
    )

    assert "Mail delivery" in text
    assert "Deferred @ box.example" in text
    assert "To: user@example.com" in text
    assert "Relay: mx.example.com[203.0.113.25]:25" in text
    assert "Detail: connect timed out" in text


def test_mail_stats_formatter_summarizes_aggregate_sections() -> None:
    text = format_mail_stats(
        "\n".join(
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
                "",
                "== TOP TO DOMAINS ==",
                "24 example.com",
                "",
                "== TOP ROUTES ==",
                "10 example.org -> example.com -> 127.0.0.1",
                "",
                "== TOP REJECT REASONS ==",
                "5 Relay access denied",
            ]
        )
    )

    assert "Mail stats" in text
    assert "Sent: 42" in text
    assert "Rejected: 9" in text
    assert "Sender domains: 5" in text
    assert "Top sender domains" in text
    assert "18  example.org" in text
    assert "example.org -> example.com -> 127.0.0.1" in text
    assert "Relay access denied" in text


def test_mail_search_formatter_includes_query_context() -> None:
    text = format_mail_search(
        (
            "Jul  1 10:04:01 box.example postfix/smtpd[125]: NOQUEUE: reject: "
            "RCPT from bad.example[203.0.113.66]: 554 5.7.1 "
            "<user@example.com>: Relay access denied; from=<bad@sender.test> "
            "to=<user@example.com> proto=ESMTP helo=<bad.example>"
        ),
        mode="from",
        query="sender.test",
        since="24h",
    )

    assert "Mail search" in text
    assert "Mode: from" in text
    assert "Query: sender.test" in text
    assert "Since: 24h" in text
    assert "Rejected @ box.example" in text
    assert "From: bad@sender.test" in text


def test_mail_service_logs_formatter_has_title() -> None:
    text = format_mail_service_logs("systemd[1]: Started Postfix Mail Transport Agent.")

    assert "🧰 Mail service logs" in text


def test_greylist_formatter_summarizes_counts() -> None:
    text = format_greylist(
        "\n".join(
            [
                "== GREYLIST SUMMARY ==",
                "greylisted=4",
                "passed=2",
                "rejected=1",
                "whitelisted=0",
            ]
        )
    )

    assert "🩶 Greylist" in text
    assert "Greylisted: 4" in text
    assert "Passed: 2" in text


def test_audit_formatter_summarizes_findings() -> None:
    text = format_audit(
        "\n".join(
            [
                "[PASS] Postfix relay restrictions are present",
                "[WARN] SSH PasswordAuthentication=yes",
                "[CRITICAL] SSH root login and password authentication are both enabled",
                "PASS: 1",
                "WARN: 1",
                "CRITICAL: 1",
                "RESULT: CRITICAL",
            ]
        )
    )

    assert "🔴 Result: CRITICAL" in text
    assert "Critical: 1" in text
    assert "SSH root login" in text


def test_incident_formatter_summarizes_sections() -> None:
    text = format_incident(
        "\n".join(
            [
                "### INCIDENT SUMMARY",
                "host=demo (demo.example.com)",
                "overall=warning",
                "since=24h",
                "collected_at=2026-07-03T10:00:00Z",
                "",
                "### HEALTH CHECKS",
                "load|ok|0.2 / 0.1 / 0.1",
                "disk|warning|/ is 88% full",
                "",
                "### SERVICES",
                "backup.service loaded failed failed Demo backup failure",
                "",
                "### PORTS",
                'tcp LISTEN 0 4096 0.0.0.0:22 0.0.0.0:* users:(("sshd",pid=1,fd=3))',
                "",
                "### MAIL_STATS",
                "== MAIL STATS SUMMARY ==",
                "sent=4",
                "rejected=3",
                "greylisted=1",
                "bounced=0",
                "== TOP REJECT REASONS ==",
                "3 Relay access denied",
                "",
                "### QUEUE",
                "Mail queue is empty",
                "",
                "### SECURITY",
                "ufw.service active",
            ]
        )
    )

    assert "Incident report" in text
    assert "Overall: WARNING" in text
    assert "disk: / is 88% full" in text
    assert "backup.service" in text
    assert "0.0.0.0:22" in text
    assert "Rejected: 3" in text
    assert "Relay access denied" in text
    assert "Mail queue is empty" in text


def test_docker_formatter_limits_raw_output() -> None:
    text = format_docker("\n".join(f"line {index}" for index in range(40)))

    assert "... truncated 5 line(s)" in text


def test_updates_formatter_counts_listed_updates() -> None:
    text = format_updates("Listing...\nopenssl/jammy 1 amd64 [upgradable]\nnginx/jammy 2 amd64")

    assert "Listed updates: 2" in text
    assert "openssl" in text


def test_processes_formatter_limits_output() -> None:
    text = format_processes("\n".join(f"proc {index}" for index in range(50)))

    assert "... truncated 10 line(s)" in text

