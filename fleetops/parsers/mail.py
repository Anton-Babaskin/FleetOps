import re

from fleetops.domain.mail import MailEvent, MailStats


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
        return tuple(tail.split(": ", 1))
    return tail, ""


def _clean_reason(reason: str) -> str:
    cleaned = reason.split("; from=<", 1)[0].strip()
    return cleaned.rstrip(",")


def parse_mail_event(line: str) -> MailEvent | None:
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
            proto=proto,
            helo=helo,
            raw=stripped,
        )

    status = _match_first(r"\bstatus=(sent|bounced|deferred)\b", stripped)
    if not status:
        return None
    return MailEvent(
        kind=status,
        time=time,
        host=host,
        to_addr=to_addr,
        from_addr=from_addr,
        reason=_match_first(r"\bstatus=(?:sent|bounced|deferred)\s+\((.*)\)", stripped),
        relay=_match_first(r"\brelay=([^,]+)", stripped),
        status=status,
        proto=proto,
        helo=helo,
        raw=stripped,
    )


def parse_mail_events(raw: str) -> list[MailEvent]:
    return [event for line in raw.splitlines() if (event := parse_mail_event(line)) is not None]


def parse_mail_stats(raw: str) -> MailStats:
    values: dict[str, str] = {}
    sections: dict[str, list[str]] = {}
    current = ""
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("== ") and stripped.endswith(" =="):
            current = stripped.removeprefix("== ").removesuffix(" ==")
            sections[current] = []
            continue
        if current == "MAIL STATS SUMMARY" and "=" in stripped:
            key, value = stripped.split("=", 1)
            values[key] = value
        elif current:
            sections[current].append(stripped)
    return MailStats(values=values, sections=sections)
