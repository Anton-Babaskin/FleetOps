from enum import StrEnum


class Status(StrEnum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


STATUS_PRIORITY: dict[Status, int] = {
    Status.OK: 0,
    Status.UNKNOWN: 1,
    Status.WARNING: 2,
    Status.CRITICAL: 3,
}


def worst_status(statuses: list[Status]) -> Status:
    if not statuses:
        return Status.UNKNOWN
    return max(statuses, key=lambda status: STATUS_PRIORITY[status])

