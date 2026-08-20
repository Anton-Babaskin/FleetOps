from fleetops.interfaces.telegram.formatter import format_docker_deep
from fleetops.parsers.docker import parse_docker_report

DOCKER_REPORT = """== DOCKER SUMMARY ==
containers=2
running=1
unhealthy=1
restarting=0
exited=1

== CONTAINERS ==
api\tUp 2 hours (unhealthy)\tdemo/api:latest\t8000/tcp

== INSPECT ==
/api\t3\trunning\tunhealthy\tfalse\t0
/worker\t1\texited\tnone\ttrue\t137

== LIVE STATS ==
api\t1.2%\t128MiB / 1GiB\t12.5%\t1MB / 2MB\t5MB / 1MB

== COMPOSE PROJECTS ==
fleetops

== DOCKER DISK ==
Images 3 2 1.2GB 300MB (25%)
"""


def test_parse_docker_deep_report() -> None:
    report = parse_docker_report(DOCKER_REPORT)

    assert report.summary["unhealthy"] == 1
    assert report.containers[0].name == "api"
    assert report.containers[0].restart_count == 3
    assert report.containers[1].oom_killed is True


def test_format_docker_deep_prioritizes_problems() -> None:
    text = format_docker_deep(DOCKER_REPORT)

    assert "Unhealthy: 1" in text
    assert "api: unhealthy, restarts 3" in text
    assert "worker: OOM killed, exit 137, restarts 1" in text
    assert "Compose projects" in text
