import re

SINCE_UNIT_SECONDS = {"m": 60, "h": 3600, "d": 86400}
MAX_SINCE_SECONDS = 365 * 86400
MAX_SEARCH_QUERY_LENGTH = 200
CONTAINER_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,254}")


def normalize_since(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    if len(normalized) < 2 or normalized[-1] not in SINCE_UNIT_SECONDS:
        raise ValueError("since must look like 30m, 1h, 24h, or 7d")
    amount_text = normalized[:-1]
    if not amount_text.isdigit() or int(amount_text) <= 0:
        raise ValueError("since must use a positive number")
    amount = int(amount_text)
    if amount * SINCE_UNIT_SECONDS[normalized[-1]] > MAX_SINCE_SECONDS:
        raise ValueError("since cannot exceed 365 days")
    return normalized


def normalize_search_query(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("mail search query is required")
    if len(normalized) > MAX_SEARCH_QUERY_LENGTH:
        raise ValueError(f"mail search query cannot exceed {MAX_SEARCH_QUERY_LENGTH} characters")
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise ValueError("mail search query cannot contain control characters")
    return normalized


def normalize_container_name(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if CONTAINER_NAME_PATTERN.fullmatch(normalized) is None:
        raise ValueError(
            "container name may contain only letters, digits, dot, underscore, and dash"
        )
    return normalized
