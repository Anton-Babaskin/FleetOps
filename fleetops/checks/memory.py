from pydantic import BaseModel, Field


class MemoryFacts(BaseModel):
    total_bytes: int = Field(ge=0)
    used_bytes: int = Field(ge=0)
    available_bytes: int = Field(ge=0)
    usage_percent: float = Field(ge=0, le=100)
    swap_total_bytes: int = Field(ge=0)
    swap_used_bytes: int = Field(ge=0)
    swap_usage_percent: float = Field(ge=0, le=100)


def parse_meminfo(text: str) -> MemoryFacts:
    values: dict[str, int] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        raw_value = rest.strip().split()[0]
        values[key] = int(raw_value) * 1024

    required = ["MemTotal", "MemAvailable", "SwapTotal", "SwapFree"]
    missing = [key for key in required if key not in values]
    if missing:
        raise ValueError(f"missing meminfo keys: {', '.join(missing)}")

    total = values["MemTotal"]
    available = values["MemAvailable"]
    used = max(total - available, 0)
    swap_total = values["SwapTotal"]
    swap_used = max(swap_total - values["SwapFree"], 0)
    usage = (used / total * 100) if total else 0
    swap_usage = (swap_used / swap_total * 100) if swap_total else 0
    return MemoryFacts(
        total_bytes=total,
        used_bytes=used,
        available_bytes=available,
        usage_percent=round(usage, 2),
        swap_total_bytes=swap_total,
        swap_used_bytes=swap_used,
        swap_usage_percent=round(swap_usage, 2),
    )

