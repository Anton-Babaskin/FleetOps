import pytest

from fleetops.services.validation import (
    normalize_container_name,
    normalize_search_query,
    normalize_since,
)


def test_since_rejects_unbounded_window() -> None:
    with pytest.raises(ValueError, match="365 days"):
        normalize_since("366d")


def test_mail_search_query_is_bounded_and_single_line() -> None:
    assert normalize_search_query(" sender@example.com ") == "sender@example.com"
    with pytest.raises(ValueError, match="control characters"):
        normalize_search_query("sender@example.com\nsecond-command")
    with pytest.raises(ValueError, match="200"):
        normalize_search_query("x" * 201)


@pytest.mark.parametrize("name", ["api", "mail-worker_1", "project.web-2"])
def test_container_name_accepts_docker_names(name: str) -> None:
    assert normalize_container_name(name) == name


@pytest.mark.parametrize("name", ["../api", "api name", "api;id", "-api"])
def test_container_name_rejects_shell_syntax(name: str) -> None:
    with pytest.raises(ValueError):
        normalize_container_name(name)
