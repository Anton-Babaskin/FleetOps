import pytest

from fleetops.services.diagnostics_service import normalize_since


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("30m", "30m"),
        ("1H", "1h"),
        ("7d", "7d"),
    ],
)
def test_normalize_since_accepts_supported_windows(value: str | None, expected: str | None) -> None:
    assert normalize_since(value) == expected


@pytest.mark.parametrize("value", ["soon", "24", "0h", "-1h", "1w"])
def test_normalize_since_rejects_unsafe_windows(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_since(value)
