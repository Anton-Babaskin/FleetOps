def split_message(text: str, limit: int = 3800) -> list[str]:
    if limit <= 0:
        raise ValueError("message limit must be positive")
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for line in text.splitlines():
        separator_length = 1 if current else 0
        if len(line) > limit:
            if current:
                chunks.append("\n".join(current))
                current = []
                current_length = 0
            chunks.extend(line[index : index + limit] for index in range(0, len(line), limit))
            continue
        if current and current_length + separator_length + len(line) > limit:
            chunks.append("\n".join(current))
            current = [line]
            current_length = len(line)
        else:
            current.append(line)
            current_length += separator_length + len(line)
    if current:
        chunks.append("\n".join(current))
    return chunks or [""]
