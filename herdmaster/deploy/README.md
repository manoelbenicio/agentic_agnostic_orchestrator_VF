# HerdMaster Deployment Guide

> Deploy HerdMaster as a user-level systemd service or run it in the foreground for development.

## Prerequisites

- Python 3.12+
- `pip` or `pipx`
- `systemd` (optional, for background service)

## Install

```bash
git clone <repo> /path/to/herdmaster
cd /path/to/herdmaster
sh deploy/install.sh
```

The script is **idempotent** - safe to run multiple times. It will:

1. Create `~/.config/herdmaster/` if missing.
2. Copy `config/herdmaster.example.toml` to `~/.config/herdmaster/config.toml` (only if it does not already exist).
3. Install the HerdMaster package via **pipx** (preferred) or fall back to `pip install --user -e .`.
4. Install the systemd `--user` unit (`~/.config/systemd/user/herdmaster.service`) and reload the daemon.

## Enable & Start Service

```bash
systemctl --user enable herdmaster   # Auto-start on login
systemctl --user start  herdmaster   # Start now
systemctl --user status herdmaster   # View status & logs
```

Follow logs live:

```bash
journalctl --user -u herdmaster -f
```

## Verify

```bash
herdmaster status
```

Expected output shape:

```
HerdMaster v1.0.0 - running
PID:     <pid>
Socket:  ~/.config/herdmaster/herdmaster.sock
DB:      ~/.config/herdmaster/herdmaster.db
Log:     ~/.config/herdmaster/herdmaster.log
```

## Configuration

Edit `~/.config/herdmaster/config.toml` and reload the service:

```bash
systemctl --user restart herdmaster
```

Available sections:

- `paths` - DB, socket, and log file locations.
- `watchdog` - Timeouts and retry policy.
- `bus` - Unix socket path and message TTL.
- `acl` - Agent roles and permissions.
- `api` - Optional HTTP API bind address and token.
- `logging` - Log level and JSON formatting.

## Uninstall

```bash
systemctl --user stop    herdmaster
systemctl --user disable herdmaster
rm ~/.config/systemd/user/herdmaster.service
systemctl --user daemon-reload
# Remove package
pipx uninstall herdmaster      # if installed via pipx
# or
pip  uninstall herdmaster      # if installed via pip
# Remove data (optional)
rm -rf ~/.config/herdmaster
```

## Notes

- HerdMaster runs as **your user**, not root. Herdr panes and the Unix socket remain owned by you (NFR-009: if HerdMaster crashes, Herdr continues unaffected).
- The systemd unit uses `Restart=on-failure` with a 5-second delay so transient errors are recovered automatically without a tight crash loop.
