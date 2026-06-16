# FleetOps

FleetOps is open-source, self-hosted, agentless infrastructure diagnostics for Linux server fleets.

Current status: **v0.1.0**. This first release intentionally supports one configured Linux server. Multi-host fleet collection is planned for v0.2.

## Features

- Agentless SSH collection with `asyncssh`
- Deterministic checks for load, memory, disk usage, and failed systemd units
- Versioned Pydantic JSON health contract
- Telegram bot commands: `/start`, `/health`, `/snapshot`
- Numeric Telegram user ID allowlist
- Demo mode without SSH
- Docker Compose deployment
- Unit tests for models, rules, redaction, formatter, and demo collector

## Architecture

```mermaid
flowchart TD
    Collector --> Parsed[Parsed check facts]
    Parsed --> Rules[Rules engine]
    Rules --> HealthService
    HealthService --> Formatter
    Formatter --> Telegram
    Collector --> SnapshotService
    SnapshotService --> Redaction
    Redaction --> Telegram
```

Core business logic does not depend on Telegram.

## Security Model

- SSH host key verification is mandatory in production mode.
- Production mode requires a configured `known_hosts` file.
- Unknown SSH host keys are never accepted automatically.
- Telegram authorization uses numeric user IDs, not usernames.
- Telegram commands cannot pass arbitrary shell commands to servers.
- Snapshot collection uses a fixed read-only command list.
- Snapshot files are written with `0600` permissions.
- Snapshot output passes through a best-effort redaction layer.

Redaction hides common token, password, bearer token, AWS key, and JWT-like patterns. It is a safety layer, not a guarantee that every secret in arbitrary logs will be found.

## Supported Systems

- Python 3.12
- Debian 12
- Ubuntu 22.04 and 24.04
- OpenSSH
- systemd
- Docker Compose

## Quick Start

```bash
cp .env.example .env
cp config/hosts.example.yml config/hosts.yml
```

Edit `.env` and `config/hosts.yml`, then run:

```bash
docker compose --profile production up -d --build
```

No ports are published because Telegram uses long polling.

## Demo

Demo mode uses deterministic data and does not require SSH, a private key, or `known_hosts`.

```bash
cp .env.example .env
# Set FLEETOPS_TELEGRAM_BOT_TOKEN in .env
docker compose --profile demo up --build
```

The default demo scenario includes at least one warning.

## Production Configuration

Environment variables:

```bash
FLEETOPS_CONFIG_PATH=/app/config/hosts.yml
FLEETOPS_DEMO_MODE=false
FLEETOPS_TELEGRAM_BOT_TOKEN=replace-with-telegram-bot-token
FLEETOPS_SSH_PRIVATE_KEY_PATH=/run/secrets/fleetops_ssh_key
FLEETOPS_SSH_KNOWN_HOSTS_PATH=/run/secrets/fleetops_known_hosts
```

Example YAML:

```yaml
host:
  id: demo-server
  hostname: server.example.com
  port: 22
  username: fleetops

telegram:
  allowed_user_ids:
    - 123456789

thresholds:
  load:
    warning_per_cpu: 1.0
    critical_per_cpu: 2.0
  memory:
    warning_percent: 80
    critical_percent: 95
  disk:
    warning_percent: 85
    critical_percent: 95
  systemd:
    critical_on_failed: false

timeouts:
  connection_seconds: 10
  command_seconds: 10

snapshot:
  output_directory: /tmp/fleetops
  retention_hours: 24
```

## Telegram Commands

- `/start` checks access and confirms the bot is ready.
- `/health` collects current health and returns a readable summary.
- `/snapshot` creates a redacted incident snapshot and sends it as a text file.

Unauthorized users receive only `Access denied.`.

## JSON Contract

`overall_status` priority is deterministic:

```text
critical > warning > unknown > ok
```

Unsupported `schema_version` values are rejected by validation.

```json
{
  "schema_version": "1.0",
  "host": {
    "id": "demo-server",
    "hostname": "demo.example.com"
  },
  "collected_at": "2026-06-16T15:30:00Z",
  "duration_ms": 842,
  "overall_status": "warning",
  "checks": [
    {
      "name": "disk",
      "status": "warning",
      "summary": "/home is 87% full",
      "metrics": {
        "mountpoint": "/home",
        "usage_percent": 87,
        "free_bytes": 22978075034
      },
      "reason": "Disk usage exceeded warning threshold of 85%",
      "error": null,
      "timed_out": false,
      "duration_ms": 72,
      "raw_ref": null
    }
  ]
}
```

## Screenshots

Placeholder: Telegram `/health` and `/snapshot` screenshots will be added after the first public deployment.

## Limitations

- v0.1 supports one configured server.
- No scheduler or background polling.
- No web UI.
- No database.
- No remediation commands.
- Snapshot redaction is best-effort.

## Roadmap

- v0.2: multi-host fleet collection
- Configurable demo scenarios through environment
- Additional read-only Linux diagnostics
- Structured snapshot metadata

## Development

```bash
python -m pip install -e ".[dev]"
ruff check .
pytest
```

