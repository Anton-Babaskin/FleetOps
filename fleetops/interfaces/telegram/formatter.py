import html
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fleetops.domain.models import CheckResult, HealthResult
from fleetops.domain.statuses import Status
from fleetops.security.redaction import redact

ICONS = {
    Status.OK: "🟢 OK",
    Status.WARNING: "🟡 WARNING",
    Status.CRITICAL: "🔴 CRITICAL",
    Status.UNKNOWN: "⚪ UNKNOWN",
}


def _line_for_check(check: CheckResult) -> str:
    name = check.name.capitalize() if check.name != "systemd" else "systemd"
    return f"{ICONS[check.status]} {name}: {html.escape(check.summary)}"


def format_health(result: HealthResult) -> str:
    lines = [
        f"🩺 Health · {html.escape(result.host.hostname)}",
        "",
        f"{ICONS[result.overall_status]} overall",
        f"⏱ Collection: {result.duration_ms} ms",
        "",
    ]
    lines.extend(_line_for_check(check) for check in result.checks)
    return "\n".join(lines)


def _format_bytes(value: Any) -> str:
    if not isinstance(value, int | float):
        return "n/a"
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    size = float(value)
    for unit in units:
        if abs(size) < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"


def _format_percent(value: Any) -> str:
    if not isinstance(value, int | float):
        return "n/a"
    return f"{value:g}%"


def _format_load_detail(check: CheckResult) -> list[str]:
    metrics = check.metrics
    return [
        f"1m / 5m / 15m: {metrics.get('load_1m', 'n/a')} / "
        f"{metrics.get('load_5m', 'n/a')} / {metrics.get('load_15m', 'n/a')}",
        f"CPU count: {metrics.get('cpu_count', 'n/a')}",
    ]


def _format_memory_detail(check: CheckResult) -> list[str]:
    metrics = check.metrics
    usage = _format_percent(metrics.get("usage_percent"))
    return [
        f"Used: {_format_bytes(metrics.get('used_bytes'))} / "
        f"{_format_bytes(metrics.get('total_bytes'))} ({usage})",
        f"Available: {_format_bytes(metrics.get('available_bytes'))}",
        f"Swap: {_format_bytes(metrics.get('swap_used_bytes'))} / "
        f"{_format_bytes(metrics.get('swap_total_bytes'))} "
        f"({_format_percent(metrics.get('swap_usage_percent'))})",
    ]


def _format_disk_detail(check: CheckResult) -> list[str]:
    filesystems = check.metrics.get("filesystems")
    if not isinstance(filesystems, list):
        return ["Filesystem metrics are unavailable."]
    sorted_filesystems = sorted(
        [fs for fs in filesystems if isinstance(fs, dict)],
        key=lambda fs: fs.get("usage_percent", 0),
        reverse=True,
    )
    lines = ["Filesystems by usage:"]
    for fs in sorted_filesystems[:8]:
        lines.append(
            "- "
            f"{fs.get('mountpoint', 'n/a')}: {_format_percent(fs.get('usage_percent'))} used, "
            f"{_format_bytes(fs.get('available_bytes'))} free "
            f"({fs.get('fs_type', 'n/a')})"
        )
    return lines


def _format_systemd_detail(check: CheckResult) -> list[str]:
    failed_units = check.metrics.get("failed_units")
    failed_count = check.metrics.get("failed_count", 0)
    if not failed_units:
        return [f"Failed units: {failed_count}"]
    return [f"Failed units: {failed_count}", *[f"- {unit}" for unit in failed_units]]


def format_check_detail(check: CheckResult) -> str:
    detail_formatters = {
        "load": _format_load_detail,
        "memory": _format_memory_detail,
        "disk": _format_disk_detail,
        "systemd": _format_systemd_detail,
    }
    name = check.name.capitalize() if check.name != "systemd" else "systemd"
    lines = [
        f"🔎 {name} detail",
        "",
        f"{ICONS[check.status]}",
        f"Summary: {check.summary}",
        f"⏱ Duration: {check.duration_ms} ms",
    ]
    if check.reason:
        lines.append(f"Reason: {check.reason}")
    if check.error:
        lines.append(f"Error: {check.error}")
    formatter = detail_formatters.get(check.name)
    if formatter is not None and check.metrics:
        lines.extend(["", *formatter(check)])
    return "\n".join(lines)


def format_status(
    *,
    hostname: str,
    host_id: str,
    demo_mode: bool,
    allowed_user_count: int,
    started_at: datetime,
) -> str:
    uptime_seconds = max(0, int((datetime.now(UTC) - started_at).total_seconds()))
    return "\n".join(
        [
            "🛟 FleetOps status",
            "",
            f"Mode: {'🧪 demo' if demo_mode else '🔐 ssh'}",
            f"Host: {html.escape(host_id)} ({html.escape(hostname)})",
            f"Allowed users: {allowed_user_count}",
            f"Uptime: {uptime_seconds}s",
        ]
    )


def format_services(raw: str) -> str:
    redacted = redact(raw).strip()
    if not redacted:
        return "🧩 Services\n\nNo service output returned."
    if redacted.startswith("ERROR:"):
        return f"🧩 Services\n\n{redacted}"

    failed: list[str] = []
    running_count = 0
    other_count = 0
    for line in redacted.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(None, 4)
        if len(parts) >= 4 and parts[2] == "active" and parts[3] == "running":
            running_count += 1
        elif len(parts) >= 4 and parts[2] == "failed":
            failed.append(stripped)
        else:
            other_count += 1

    lines = [
        "🧩 Services",
        "",
        f"🟢 Running: {running_count}",
        f"{'🔴' if failed else '🟢'} Failed: {len(failed)}",
    ]
    if other_count:
        lines.append(f"⚪ Other listed: {other_count}")
    if failed:
        lines.extend(["", "⚠️ Failed units:"])
        lines.extend(f"• {line}" for line in failed[:10])
    else:
        lines.extend(["", "✅ No failed services listed."])
    return "\n".join(lines)


def format_services_detail(raw: str) -> str:
    return format_raw_report("🧩 Services detail", raw, max_lines=80)


def format_journal(raw: str, max_lines: int = 20) -> str:
    redacted = redact(raw).strip()
    if not redacted:
        return "📜 Journal\n\nNo recent warning/error lines returned."
    lines = redacted.splitlines()
    visible = lines[-max_lines:]
    header = [
        "📜 Journal",
        "",
        f"Showing {len(visible)} of {len(lines)} recent warning/error line(s).",
        "",
    ]
    return "\n".join([*header, *visible])


def format_raw_report(title: str, raw: str, max_lines: int = 40) -> str:
    redacted = redact(raw).strip()
    if not redacted:
        return f"{title}\n\nNo output returned."
    lines = redacted.splitlines()
    visible = lines[:max_lines]
    output = list(visible)
    if len(lines) > max_lines:
        output.append(f"... truncated {len(lines) - max_lines} line(s)")
    return "\n".join([title, "", *output])


def format_ports(raw: str) -> str:
    redacted = redact(raw).strip()
    if not redacted:
        return "🌐 Ports\n\nNo listening sockets returned."
    lines = [line.strip() for line in redacted.splitlines() if line.strip()]
    tcp_count = sum(1 for line in lines if line.startswith("tcp"))
    udp_count = sum(1 for line in lines if line.startswith("udp"))
    public_listeners = [
        line
        for line in lines
        if "127.0.0.1:" not in line and "[::1]:" not in line and "LISTEN" in line
    ]
    visible = public_listeners[:12]
    if len(public_listeners) > 12:
        visible.append(f"... {len(public_listeners) - 12} more public listener(s)")
    if not visible:
        visible = ["No public listening TCP sockets found in the first page."]
    return "\n".join(
        [
            "Ports",
            "",
            f"🔵 TCP sockets: {tcp_count}",
            f"🟣 UDP sockets: {udp_count}",
            "",
            "🌍 Public listeners:",
            *visible,
        ]
    )


def format_ports_detail(raw: str) -> str:
    return format_raw_report("🌐 Ports detail", raw, max_lines=90)


def format_docker(raw: str) -> str:
    return format_raw_report("🐳 Docker", raw, max_lines=35)


def format_mail(raw: str) -> str:
    redacted = redact(raw).strip()
    if not redacted:
        return "📮 Mail services\n\nNo common mail services found."
    if "No unit files found" in redacted:
        return "📮 Mail services\n\nNo common mail services found."
    active = []
    inactive = []
    other = []
    for line in redacted.splitlines():
        parts = line.split(None, 1)
        if len(parts) != 2:
            other.append(line)
        elif parts[1] == "active":
            active.append(parts[0])
        else:
            inactive.append(line)
    lines = [
        "📮 Mail services",
        "",
        f"🟢 Active: {len(active)}",
        f"{'🟡' if inactive else '🟢'} Needs attention: {len(inactive)}",
    ]
    if active:
        lines.extend(["", "✅ Active services:", *[f"• {item}" for item in active]])
    if inactive:
        lines.extend(["", "⚠️ Needs attention:", *[f"• {item}" for item in inactive]])
    if other:
        lines.extend(["", "Other output:", *other[:10]])
    return "\n".join(lines)


def format_mail_queue(raw: str) -> str:
    redacted = redact(raw).strip()
    if not redacted:
        return "📬 Mail queue\n\nNo queue output returned."
    if "Mail queue is empty" in redacted:
        return "📬 Mail queue\n\n✅ Mail queue is empty."
    queue_lines = [line for line in redacted.splitlines() if line.strip()]
    visible = queue_lines[:40]
    if len(queue_lines) > 40:
        visible.append(f"... truncated {len(queue_lines) - 40} line(s)")
    return "\n".join(["📬 Mail queue", "", *visible])


def format_mail_dns(raw: str) -> str:
    return format_raw_report("🧭 Mail DNS", raw, max_lines=70)


def format_mail_tls(raw: str) -> str:
    redacted = redact(raw).strip()
    if not redacted:
        return "🔐 Mail TLS\n\nNo certificate output returned."
    expired_hint = "notAfter=" in redacted and "certificate check failed" not in redacted
    status = "🟢 Certificate data collected." if expired_hint else "🟡 Review TLS output."
    return "\n".join(["🔐 Mail TLS", "", status, "", *redacted.splitlines()[:70]])


@dataclass(frozen=True)
class MailEvent:
    kind: str
    time: str
    host: str
    to_addr: str
    from_addr: str
    client: str
    reason: str
    relay: str
    status: str
    proto: str
    helo: str
    raw: str


def _match_first(pattern: str, value: str) -> str:
    match = re.search(pattern, value)
    return match.group(1).strip() if match else ""


def _mail_time_and_host(line: str) -> tuple[str, str]:
    iso_match = re.match(r"^(\d{4}-\d\d-\d\dT\S+)\s+(\S+)\s+", line)
    if iso_match:
        return iso_match.group(1), iso_match.group(2)
    syslog_match = re.match(r"^([A-Z][a-z]{2}\s+\d+\s+\d\d:\d\d:\d\d)\s+(\S+)\s+", line)
    if syslog_match:
        return syslog_match.group(1), syslog_match.group(2)
    return "", ""


def _split_reject_client_reason(line: str) -> tuple[str, str]:
    marker = "reject: RCPT from "
    if marker not in line:
        return "", ""
    tail = line.split(marker, 1)[1]
    bracket_separator = tail.find("]: ")
    if bracket_separator >= 0:
        return tail[: bracket_separator + 1], tail[bracket_separator + 3 :]
    if ": " in tail:
        client, reason = tail.split(": ", 1)
        return client, reason
    return tail, ""


def _clean_reason(reason: str) -> str:
    cleaned = reason.split("; from=<", 1)[0].strip()
    return cleaned.rstrip(",")


def _truncate_field(value: str, limit: int = 180) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: limit - 3]}..."


def _parse_mail_event(line: str) -> MailEvent | None:
    stripped = line.strip()
    if not stripped:
        return None
    time, host = _mail_time_and_host(stripped)
    from_addr = _match_first(r"from=<([^>]*)>", stripped)
    to_addr = _match_first(r"to=<([^>]*)>", stripped)
    proto = _match_first(r"\bproto=([^ ]+)", stripped)
    helo = _match_first(r"\bhelo=<([^>]*)>", stripped)

    if "reject: RCPT from " in stripped:
        client, reason = _split_reject_client_reason(stripped)
        kind = "greylisted" if "greylisted" in reason.lower() else "rejected"
        return MailEvent(
            kind=kind,
            time=time,
            host=host,
            to_addr=to_addr or _match_first(r"\s<([^>]+)>:", reason),
            from_addr=from_addr,
            client=client,
            reason=_clean_reason(reason),
            relay="",
            status="",
            proto=proto,
            helo=helo,
            raw=stripped,
        )

    status = _match_first(r"\bstatus=(sent|bounced|deferred)\b", stripped)
    if status:
        return MailEvent(
            kind=status,
            time=time,
            host=host,
            to_addr=to_addr,
            from_addr=from_addr,
            client="",
            reason=_match_first(r"\bstatus=(?:sent|bounced|deferred)\s+\((.*)\)", stripped),
            relay=_match_first(r"\brelay=([^,]+)", stripped),
            status=status,
            proto=proto,
            helo=helo,
            raw=stripped,
        )
    return None


def _mail_event_title(event: MailEvent) -> str:
    labels = {
        "sent": "✅ Delivered",
        "deferred": "🟡 Deferred",
        "bounced": "🔴 Bounced",
        "greylisted": "🩶 Greylisted",
        "rejected": "⛔ Rejected",
    }
    title = labels.get(event.kind, "📨 Mail event")
    return f"{title} @ {event.host}" if event.host else title


def _format_mail_event(event: MailEvent) -> list[str]:
    lines = [_mail_event_title(event)]
    if event.time:
        lines.append(f"Time: {event.time}")
    if event.to_addr:
        lines.append(f"To: {event.to_addr}")
    if event.from_addr:
        lines.append(f"From: {event.from_addr}")
    if event.client:
        lines.append(f"Client: {_truncate_field(event.client)}")
    if event.relay:
        lines.append(f"Relay: {_truncate_field(event.relay)}")
    if event.status:
        lines.append(f"Status: {event.status}")
    if event.reason:
        label = "Reason" if event.kind in {"rejected", "greylisted"} else "Detail"
        lines.append(f"{label}: {_truncate_field(event.reason)}")
    if event.proto:
        lines.append(f"Proto: {event.proto}")
    if event.helo:
        lines.append(f"Helo: {_truncate_field(event.helo, 80)}")
    if len(lines) == 1:
        lines.append(_truncate_field(event.raw, 260))
    return lines


def _format_mail_events(
    *,
    title: str,
    raw: str,
    kinds: set[str] | None = None,
    empty_message: str,
    max_events: int = 8,
) -> str:
    redacted = redact(raw).strip()
    if not redacted:
        return f"{title}\n\n{empty_message}"
    if redacted.startswith("ERROR:"):
        return f"{title}\n\n{redacted}"

    parsed = [_parse_mail_event(line) for line in redacted.splitlines()]
    events = [event for event in parsed if event is not None]
    if kinds is not None:
        events = [event for event in events if event.kind in kinds]

    sent = sum(event.kind == "sent" for event in events)
    rejected = sum(event.kind in {"rejected", "greylisted"} for event in events)
    greylisted = sum(event.kind == "greylisted" for event in events)
    deferred = sum(event.kind == "deferred" for event in events)
    bounced = sum(event.kind == "bounced" for event in events)

    header = [
        title,
        "",
        f"🟢 Sent: {sent}",
        f"⛔ Rejected: {rejected}",
        f"🩶 Greylisted: {greylisted}",
        f"🟡 Deferred: {deferred}",
        f"🔴 Bounced: {bounced}",
    ]
    if not events:
        return "\n".join([*header, "", empty_message])

    visible = events[-max_events:]
    cards: list[str] = []
    for index, event in enumerate(visible):
        if index:
            cards.append("")
        cards.extend(_format_mail_event(event))
    if len(events) > len(visible):
        cards.append("")
        cards.append(f"... {len(events) - len(visible)} older parsed event(s)")
    return "\n".join([*header, "", *cards])


def format_mail_logs(raw: str) -> str:
    return _format_mail_events(
        title="📨 Mail flow",
        raw=raw,
        empty_message="No send/reject/defer/bounce mail flow events found.",
    )


def format_mail_rejections(raw: str) -> str:
    return _format_mail_events(
        title="⛔ Mail rejections",
        raw=raw,
        kinds={"rejected", "greylisted"},
        empty_message="No rejected mail events found.",
        max_events=10,
    )


def format_mail_delivery(raw: str) -> str:
    return _format_mail_events(
        title="✅ Mail delivery",
        raw=raw,
        kinds={"sent", "deferred", "bounced"},
        empty_message="No delivery/defer/bounce mail events found.",
        max_events=10,
    )


def format_mail_search(raw: str, *, mode: str, query: str, since: str | None = None) -> str:
    title = "🔎 Mail search"
    result = _format_mail_events(
        title=title,
        raw=raw,
        empty_message="No matching mail events found.",
        max_events=12,
    )
    context = [
        f"Mode: {mode}",
        f"Query: {query}",
    ]
    if since:
        context.append(f"Since: {since}")
    lines = result.splitlines()
    return "\n".join([lines[0], "", *context, *lines[1:]])


def _parse_mail_stats(raw: str) -> tuple[dict[str, str], dict[str, list[str]]]:
    values: dict[str, str] = {}
    sections: dict[str, list[str]] = {}
    current = ""
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("== ") and stripped.endswith(" =="):
            current = stripped.strip("= ")
            sections[current] = []
            continue
        if current == "MAIL STATS SUMMARY" and "=" in stripped:
            key, value = stripped.split("=", 1)
            values[key] = value
        elif current:
            sections.setdefault(current, []).append(stripped)
    return values, sections


def _format_stats_section(title: str, rows: list[str], limit: int = 8) -> list[str]:
    if not rows:
        return []
    lines = ["", title]
    for row in rows[:limit]:
        parts = row.split(None, 1)
        volume_parts = row.split(None, 3)
        if len(volume_parts) == 4 and volume_parts[1] == "MB":
            lines.append(f"• {volume_parts[0]} MB  {volume_parts[2]} msg  {volume_parts[3]}")
        elif len(parts) == 2 and parts[0].replace(".", "", 1).isdigit():
            lines.append(f"• {parts[0]}  {parts[1]}")
        else:
            lines.append(f"• {row}")
    if len(rows) > limit:
        lines.append(f"... {len(rows) - limit} more")
    return lines


def format_mail_stats(raw: str) -> str:
    redacted = redact(raw).strip()
    if not redacted:
        return "📊 Mail stats\n\nNo mail statistics output returned."
    values, sections = _parse_mail_stats(redacted)
    lines = [
        "📊 Mail stats",
        "",
        f"🟢 Sent: {values.get('sent', '0')}",
        f"⛔ Rejected: {values.get('rejected', '0')}",
        f"🩶 Greylisted: {values.get('greylisted', '0')}",
        f"🟡 Deferred: {values.get('deferred', '0')}",
        f"🔴 Bounced: {values.get('bounced', '0')}",
        f"🌐 Sender domains: {values.get('from_domains', '0')}",
        f"🎯 Recipient domains: {values.get('to_domains', '0')}",
    ]
    lines.extend(_format_stats_section("Top sender domains", sections.get("TOP FROM DOMAINS", [])))
    lines.extend(_format_stats_section("Top recipient domains", sections.get("TOP TO DOMAINS", [])))
    lines.extend(_format_stats_section("Top routes", sections.get("TOP ROUTES", []), limit=6))
    lines.extend(_format_stats_section("Top relays", sections.get("TOP RELAYS", []), limit=6))
    lines.extend(
        _format_stats_section("Top reject reasons", sections.get("TOP REJECT REASONS", []), limit=6)
    )
    lines.extend(
        _format_stats_section(
            "Top sender volume",
            sections.get("TOP VOLUME FROM DOMAINS", []),
            limit=6,
        )
    )
    return "\n".join(lines)


def format_mail_service_logs(raw: str) -> str:
    return format_raw_report("🧰 Mail service logs", raw, max_lines=70)


def format_greylist(raw: str) -> str:
    redacted = redact(raw).strip()
    if not redacted:
        return "🩶 Greylist\n\nNo postgrey output returned."
    values: dict[str, str] = {}
    for line in redacted.splitlines():
        if "=" in line and line.split("=", 1)[0] in {
            "greylisted",
            "passed",
            "rejected",
            "whitelisted",
        }:
            key, value = line.split("=", 1)
            values[key] = value
    lines = [
        "🩶 Greylist",
        "",
        f"🟡 Greylisted: {values.get('greylisted', '0')}",
        f"🟢 Passed: {values.get('passed', '0')}",
        f"🔴 Rejected: {values.get('rejected', '0')}",
        f"⚪ Whitelisted: {values.get('whitelisted', '0')}",
    ]
    current_section = ""
    interesting: list[str] = []
    for line in redacted.splitlines():
        if line.startswith("== "):
            current_section = line
            if "TOP" in line or "RECENT" in line:
                interesting.append(line)
            continue
        stripped = line.strip()
        if not stripped:
            continue
        if current_section.startswith("== TOP") and stripped[:1].isdigit():
            interesting.append(stripped)
        elif current_section == "== RECENT EVENTS ==" and len(interesting) < 35:
            interesting.append(line)
    if interesting:
        lines.extend(["", *interesting[:35]])
    return "\n".join(lines)


def format_greylist_detail(raw: str) -> str:
    return format_raw_report("🩶 Greylist detail", raw, max_lines=120)


def format_top(raw: str) -> str:
    return format_raw_report("📈 Top", raw, max_lines=30)


def format_processes(raw: str) -> str:
    return format_raw_report("⚙️ Processes", raw, max_lines=40)


def format_reboots(raw: str) -> str:
    return format_raw_report("🔁 Reboots", raw, max_lines=30)


def format_updates(raw: str) -> str:
    redacted = redact(raw).strip()
    if not redacted:
        return "📦 Updates\n\nNo update output returned."
    lines = [line for line in redacted.splitlines() if line and line != "Listing..."]
    if not lines:
        return "📦 Updates\n\n✅ No package updates listed."
    visible = lines[:40]
    if len(lines) > 40:
        visible.append(f"... truncated {len(lines) - 40} update line(s)")
    return "\n".join(["📦 Updates", "", f"🟡 Listed updates: {len(lines)}", "", *visible])


def format_security(raw: str) -> str:
    return format_raw_report("🛡️ Security", raw, max_lines=50)


def format_docker_logs(raw: str) -> str:
    return format_raw_report("🐳 Docker logs", raw, max_lines=70)


def _audit_count(raw: str, label: str) -> int:
    for line in raw.splitlines():
        if line.startswith(f"{label}:"):
            value = line.split(":", 1)[1].strip()
            if value.isdigit():
                return int(value)
    return 0


def format_audit(raw: str) -> str:
    redacted = redact(raw).strip()
    if not redacted:
        return "🧪 Security audit\n\nNo audit output returned."
    critical = _audit_count(redacted, "CRITICAL")
    warnings = _audit_count(redacted, "WARN")
    passed = _audit_count(redacted, "PASS")
    result_icon = "🔴" if critical else "🟡" if warnings else "🟢"
    result = "CRITICAL" if critical else "WARNINGS" if warnings else "OK"
    issues = [
        line
        for line in redacted.splitlines()
        if line.startswith("[CRITICAL]") or line.startswith("[WARN]")
    ]
    visible = issues[:8]
    if len(issues) > len(visible):
        visible.append(f"... {len(issues) - len(visible)} more issue(s)")
    lines = [
        "🧪 Security audit",
        "",
        f"{result_icon} Result: {result}",
        f"🔴 Critical: {critical}",
        f"🟡 Warnings: {warnings}",
        f"🟢 Pass: {passed}",
    ]
    if visible:
        lines.extend(["", "Top findings:", *[f"• {item}" for item in visible]])
    else:
        lines.extend(["", "✅ No warning or critical findings."])
    return "\n".join(lines)


def format_audit_detail(raw: str) -> str:
    return format_raw_report("🧪 Security audit detail", raw, max_lines=140)

