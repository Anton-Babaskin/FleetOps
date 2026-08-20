from fleetops.parsers.mail import parse_mail_event, parse_mail_stats


def test_parse_iso_postfix_rejection() -> None:
    event = parse_mail_event(
        "2026-07-02T11:55:00+0200 box.example postfix/smtpd[10]: NOQUEUE: "
        "reject: RCPT from bad.example[203.0.113.4]: 554 5.7.1 "
        "<user@example.com>: Relay access denied; from=<bad@sender.test> "
        "to=<user@example.com> proto=ESMTP helo=<bad.example>"
    )

    assert event is not None
    assert event.kind == "rejected"
    assert event.host == "box.example"
    assert event.from_addr == "bad@sender.test"
    assert event.to_addr == "user@example.com"


def test_parse_mail_stats_returns_domain_model() -> None:
    stats = parse_mail_stats(
        "== MAIL STATS SUMMARY ==\nsent=4\nrejected=2\n\n"
        "== TOP REJECT REASONS ==\n2 Relay access denied"
    )

    assert stats.values == {"sent": "4", "rejected": "2"}
    assert stats.sections["TOP REJECT REASONS"] == ["2 Relay access denied"]
