from fleetops.domain.docker import DockerContainer, DockerReport


def _marker_sections(raw: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = ""
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("== ") and stripped.endswith(" =="):
            current = stripped.removeprefix("== ").removesuffix(" ==")
            sections[current] = []
        elif current and stripped:
            sections[current].append(stripped)
    return sections


def _parse_int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except ValueError:
        return default


def parse_docker_report(raw: str) -> DockerReport:
    sections = _marker_sections(raw)
    summary: dict[str, int] = {}
    for line in sections.get("DOCKER SUMMARY", []):
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        summary[key] = _parse_int(value)

    containers: list[DockerContainer] = []
    for line in sections.get("INSPECT", []):
        parts = line.split("\t")
        if len(parts) != 6:
            continue
        name, restarts, state, health, oom_killed, exit_code = parts
        containers.append(
            DockerContainer(
                name=name.removeprefix("/"),
                restart_count=_parse_int(restarts),
                state=state,
                health=health,
                oom_killed=oom_killed.lower() == "true",
                exit_code=_parse_int(exit_code),
            )
        )

    return DockerReport(
        summary=summary,
        containers=containers,
        container_rows=sections.get("CONTAINERS", []),
        live_stats=sections.get("LIVE STATS", []),
        compose_projects=sections.get("COMPOSE PROJECTS", []),
        disk=sections.get("DOCKER DISK", []),
    )
