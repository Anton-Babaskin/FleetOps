from pydantic import BaseModel, Field


class LoadFacts(BaseModel):
    load_1m: float = Field(ge=0)
    load_5m: float = Field(ge=0)
    load_15m: float = Field(ge=0)
    cpu_count: int = Field(ge=1)


def parse_loadavg(loadavg: str, nproc: str) -> LoadFacts:
    parts = loadavg.strip().split()
    if len(parts) < 3:
        raise ValueError("unexpected /proc/loadavg format")
    return LoadFacts(
        load_1m=float(parts[0]),
        load_5m=float(parts[1]),
        load_15m=float(parts[2]),
        cpu_count=int(nproc.strip()),
    )

