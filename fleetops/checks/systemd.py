from pydantic import BaseModel, Field


class SystemdFacts(BaseModel):
    failed_count: int = Field(ge=0)
    failed_units: list[str]


def parse_systemctl_failed(text: str) -> SystemdFacts:
    units: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("UNIT ") or stripped.startswith("LOAD "):
            continue
        if "0 loaded units listed" in stripped:
            return SystemdFacts(failed_count=0, failed_units=[])
        parts = stripped.split()
        if len(parts) >= 4 and parts[2] == "failed":
            units.append(parts[0])
    return SystemdFacts(failed_count=len(units), failed_units=units)

