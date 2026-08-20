from fleetops.interfaces.telegram.messages import split_message


def test_split_message_preserves_line_boundaries() -> None:
    chunks = split_message("first line\nsecond line\nthird line", limit=22)

    assert chunks == ["first line\nsecond line", "third line"]


def test_split_message_breaks_a_single_oversized_line() -> None:
    assert split_message("abcdefghij", limit=4) == ["abcd", "efgh", "ij"]
