from dataclasses import dataclass, field


@dataclass(frozen=True)
class DockerContainer:
    name: str
    restart_count: int
    state: str
    health: str
    oom_killed: bool
    exit_code: int


@dataclass(frozen=True)
class DockerReport:
    summary: dict[str, int] = field(default_factory=dict)
    containers: list[DockerContainer] = field(default_factory=list)
    container_rows: list[str] = field(default_factory=list)
    live_stats: list[str] = field(default_factory=list)
    compose_projects: list[str] = field(default_factory=list)
    disk: list[str] = field(default_factory=list)
