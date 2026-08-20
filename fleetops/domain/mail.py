from dataclasses import dataclass, field


@dataclass(frozen=True)
class MailEvent:
    kind: str
    time: str = ""
    host: str = ""
    to_addr: str = ""
    from_addr: str = ""
    client: str = ""
    reason: str = ""
    relay: str = ""
    status: str = ""
    proto: str = ""
    helo: str = ""
    raw: str = ""


@dataclass(frozen=True)
class MailStats:
    values: dict[str, str] = field(default_factory=dict)
    sections: dict[str, list[str]] = field(default_factory=dict)
