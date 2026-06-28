# HerdMaster

HerdMaster is a local-first orchestration control plane for coordinating multiple AI coding agents running in Herdr panes. It provides the packaging, configuration layout, SQLite persistence, Unix-socket message bus, dispatch helpers, watchdog/recovery core, and deployment files for the Python 3.12+ application.

The committed package is intentionally small at runtime: `typer` for the CLI surface declared by packaging, `rich` for terminal output, and `structlog` for structured logging. The core package does not depend on FastAPI, Postgres, Redis, Rust, or cloud services.

## Install

### From a checkout

Use editable install while developing or running from a local clone:

```bash
cd /path/to/HerdMaster
pip install -e .
```

Install development test dependencies with:

```bash
pip install -e ".[dev]"
```

### Isolated CLI install with pipx

Use `pipx` when you want the command-line package isolated from the current Python environment:

```bash
cd /path/to/HerdMaster
pipx install .
```

To refresh an existing local `pipx` install:

```bash
pipx install --force .
```

### User-space installer and systemd

The repository includes a user-space installer:

```bash
cd /path/to/HerdMaster
sh deploy/install.sh
```

`deploy/install.sh` performs these committed operations:

- Creates `~/.config/herdmaster/`.
- Copies `config/herdmaster.example.toml` to `~/.config/herdmaster/config.toml` only when the user config does not already exist.
- Installs the package with `pipx` when available.
- Falls back to `python -m pip install --user -e <repo>` when `pipx` is unavailable.
- Installs `deploy/herdmaster.service` to `~/.config/systemd/user/herdmaster.service` when `systemctl` is available.
- Runs `systemctl --user daemon-reload` when possible.

The committed service unit runs:

```text
ExecStart=/usr/bin/env herdmaster start
WorkingDirectory=%h/.config/herdmaster
```

Common user-service commands:

```bash
systemctl --user enable herdmaster
systemctl --user start herdmaster
systemctl --user status herdmaster
journalctl --user -u herdmaster -f
```

## Quickstart

Create the user configuration directory and seed it from the committed example:

```bash
mkdir -p ~/.config/herdmaster
cp config/herdmaster.example.toml ~/.config/herdmaster/config.toml
```

Start HerdMaster in the foreground:

```bash
herdmaster start
```

The packaging metadata declares the console script as `herdmaster = "herdmaster.cli:app"`, and the deployment files use `herdmaster start`. In the current source snapshot, `src/herdmaster/cli.py` is not committed yet; `python -m herdmaster` therefore prints `CLI not yet built` through the fallback in `src/herdmaster/__main__.py`. The implemented core modules and configuration reference below describe the committed runtime pieces that the CLI is expected to compose.

## Runtime Files and Config Directory

By default, HerdMaster uses the per-user config/runtime directory from PRD section 14.3:

```text
~/.config/herdmaster/
|-- config.toml
|-- herdmaster.db
|-- herdmaster.log
|-- herdmaster.sock
`-- prompts/
```

The sample configuration is in `config/herdmaster.example.toml`. `load_config(path=None)` reads `~/.config/herdmaster/config.toml`; if that file is absent, HerdMaster uses in-code defaults. Relative `db`, `socket`, and `log` entries under `[paths]` are resolved beneath `paths.config_dir`.

Expected file roles:

- `config.toml`: user-edited TOML configuration.
- `herdmaster.db`: SQLite database used by repositories for agents, tasks, messages, projects, project history, and health events.
- `herdmaster.log`: configured log file path for deployments that route structured logs to a file.
- `herdmaster.sock`: Unix-domain socket path for the message bus.
- `prompts/`: dispatch prompt-file fallback directory used for prompts above the configured inline threshold.

## Configuration Reference

This section documents every key in `config/herdmaster.example.toml` and the defaults implemented in `src/herdmaster/config.py`.

### `[paths]`

| Key | Default | Description |
| --- | --- | --- |
| `config_dir` | `"~/.config/herdmaster"` | Base directory for user config and local runtime files. `~` is expanded. |
| `db` | `"herdmaster.db"` | SQLite database path. Relative values resolve under `config_dir`; absolute values are expanded and used as-is. |
| `socket` | `"herdmaster.sock"` | General HerdMaster socket path. Relative values resolve under `config_dir`; absolute values are expanded and used as-is. |
| `log` | `"herdmaster.log"` | Log file path for deployments that write to a file. Relative values resolve under `config_dir`; absolute values are expanded and used as-is. |

### `[watchdog]`

| Key | Default | Description |
| --- | --- | --- |
| `soft_timeout_s` | `10.0` | Seconds without progress before a healthy agent transitions to degraded health. Must be less than `hard_timeout_s`. |
| `hard_timeout_s` | `30.0` | Seconds without progress before watchdog recovery is triggered. Must be greater than `soft_timeout_s`. |
| `poll_interval_s` | `15` | Seconds between watchdog polling passes. Must be greater than `0`. |
| `max_retries` | `3` | Maximum recovery attempts before escalation. Must be `0` or greater. |
| `tertiary_hash_interval_s` | `30` | Seconds between terminal-output hash checks used as a tertiary progress signal. Must be greater than `0`. |

### `[bus]`

| Key | Default | Description |
| --- | --- | --- |
| `socket_path` | `"~/.config/herdmaster/herdmaster.sock"` | Unix-domain socket used by `MessageBusServer`. The value is expanded with `~`; it is independent of `[paths].socket` in the current config model. |
| `message_ttl_s` | `300` | Time-to-live in seconds for bus messages. Must be greater than `0`. |

If the bus cannot bind the Unix socket, the implemented server activates file fallback and writes JSON lines to a fallback file next to `socket_path`.

### `[acl]`

| Key | Default | Description |
| --- | --- | --- |
| `default_policy` | `"deny"` | Fallback policy for ACL decisions. Must be `"allow"` or `"deny"`. |
| `roles` | `[]` | Array of `[[acl.roles]]` tables. Role names must be unique. |

Each `[[acl.roles]]` entry supports:

| Key | Default | Description |
| --- | --- | --- |
| `name` | Required | Unique role name, such as `"orchestrator"`, `"worker"`, `"peer_reviewer"`, or `"observer"`. |
| `agents` | `[]` | Agent IDs or patterns assigned to the role. The example uses explicit IDs such as `"A1"` and `"A2"`. |
| `can_send_to` | `[]` | Role names, agent selectors, or `"*"` targets this role may send messages to. |
| `can_receive_from` | `[]` | Role names, agent selectors, or `"*"` sources this role may receive messages from. |
| `can_dispatch_tasks` | `false` | Whether agents in this role may dispatch tasks. |
| `can_reassign_tasks` | `false` | Whether agents in this role may reassign tasks. |

The committed example defines:

- `orchestrator`: `agents = ["A1"]`, can send to and receive from `"*"`, can dispatch and reassign.
- `worker`: `agents = ["A2", "A3", "A4", "A5", "A6", "A7", "A8"]`, can communicate with `orchestrator`, cannot dispatch or reassign.
- `peer_reviewer`: `agents = ["A2", "A3"]`, can communicate with `orchestrator` and `peer_reviewer`, cannot dispatch or reassign.
- `observer`: no assigned agents by default, cannot send, can receive from `"*"`, cannot dispatch or reassign.

### `[api]`

| Key | Default | Description |
| --- | --- | --- |
| `bind` | `"127.0.0.1"` | Intended API bind address. The config model defaults to localhost. |
| `port` | `8080` | Intended API port. Must be in the range `1..65535`. |
| `token` | `""` | Optional bearer token value. Empty string means no token is configured. |

The config model is committed, but no API server module is present in this source snapshot.

### `[logging]`

| Key | Default | Description |
| --- | --- | --- |
| `level` | `"INFO"` | Logging threshold. Accepted values are `DEBUG`, `INFO`, `WARNING`, `ERROR`, and `CRITICAL`; values are normalized to uppercase. |
| `json` | `true` | When `true`, `setup_logging()` configures JSON output. When `false`, it uses `structlog` console rendering. |

## Validation and Reload Behavior

`validate_config()` rejects invalid runtime settings before long-running components should start:

- `watchdog.soft_timeout_s >= watchdog.hard_timeout_s`
- `watchdog.poll_interval_s <= 0`
- `watchdog.tertiary_hash_interval_s <= 0`
- `watchdog.max_retries < 0`
- `bus.message_ttl_s <= 0`
- duplicate ACL role names
- ACL role lists containing non-string entries
- `acl.default_policy` outside `"allow"` or `"deny"`
- `api.port` outside `1..65535`
- unsupported `logging.level`

`ConfigWatcher` polls the config file mtime and invokes a callback only after the new file loads and validates successfully. Bad reloads are logged and the previous config remains active.

## Implemented Runtime Components

The committed source includes:

- Configuration loading, validation, hot reload, and structured logging in `src/herdmaster/config.py`.
- SQLite schema and repository layer in `src/herdmaster/db/`.
- JSON-RPC message envelopes and async Unix-socket bus in `src/herdmaster/bus/`.
- Herdr CLI adapter and tolerant JSON parsers in `src/herdmaster/herdr/`.
- Durable task queue and prompt injector in `src/herdmaster/dispatch/`.
- Watchdog health monitoring and recovery in `src/herdmaster/watchdog/`.
- ACL engine in `src/herdmaster/acl/`.

## Observability (Prometheus & Grafana)

HerdMaster natively exports Prometheus-compatible metrics via the HTTP API (port `8080` by default, endpoint `/metrics`).
We provide a ready-to-use Docker Compose stack to spin up Prometheus and Grafana for local monitoring.

```bash
cd deploy/observability
docker compose up -d
```
- **Prometheus**: `http://localhost:9090`
- **Grafana**: `http://localhost:3000` (default credentials: admin / admin)

## Documentation

- [Technical design](docs/TECHNICAL_DESIGN.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Deployment notes](deploy/README.md)
- [Installer script](deploy/install.sh)
- [systemd user service](deploy/herdmaster.service)

`docs/TECHNICAL_DESIGN.md` and `docs/TROUBLESHOOTING.md` reference `docs/architecture_macro.html`, `docs/architecture_micro.html`, and `docs/architecture_deep.html`, but those HTML files are not committed in this snapshot. They are therefore not linked here to keep README links resolvable.
