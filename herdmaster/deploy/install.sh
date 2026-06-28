#!/usr/bin/env sh
# deploy/install.sh - HerdMaster user-space installer
#
# Idempotent. Safe to run multiple times.

set -eu
# shellcheck disable=SC3040
if (set -o pipefail) 2>/dev/null; then
    # shellcheck disable=SC3040
    set -o pipefail
fi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

info() { printf '[INSTALL] %s\n' "$1"; }
warn() { printf '[WARNING] %s\n' "$1" >&2; }
ok()   { printf '[OK] %s\n' "$1"; }

DIRNAME="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$DIRNAME/.." && pwd)"

# ---------------------------------------------------------------------------
# 1. Ensure config directory exists
# ---------------------------------------------------------------------------
CONFIG_DIR="${HOME}/.config/herdmaster"
info "Ensuring config directory: ${CONFIG_DIR}"
mkdir -p "${CONFIG_DIR}"
ok "Config directory ready."

# ---------------------------------------------------------------------------
# 2. Seed config.toml from example (never overwrite an existing one)
# ---------------------------------------------------------------------------
CONFIG_FILE="${CONFIG_DIR}/config.toml"
EXAMPLE_TOML="${REPO_ROOT}/config/herdmaster.example.toml"

if [ -f "${CONFIG_FILE}" ]; then
    warn "config.toml already exists at ${CONFIG_FILE}; skipping copy to avoid overwriting user edits."
else
    if [ -f "${EXAMPLE_TOML}" ]; then
        cp "${EXAMPLE_TOML}" "${CONFIG_FILE}"
        ok "Copied example config to ${CONFIG_FILE}"
    else
        warn "Example config not found at ${EXAMPLE_TOML}; skipping config seed."
    fi
fi

# ---------------------------------------------------------------------------
# 3. Install HerdMaster package (pipx preferred, pip --user fallback)
# ---------------------------------------------------------------------------
if command -v pipx >/dev/null 2>&1; then
    info "pipx detected. Installing HerdMaster..."
    if pipx list 2>/dev/null | grep -q 'package herdmaster '; then
        warn "herdmaster already installed via pipx; refreshing from local source."
        pipx install --force "${REPO_ROOT}"
    else
        pipx install "${REPO_ROOT}"
    fi
    ok "Installed via pipx."
else
    warn "pipx not found. Falling back to 'pip install --user -e .'..."
    if command -v python3 >/dev/null 2>&1; then
        PYTHON=python3
    elif command -v python >/dev/null 2>&1; then
        PYTHON=python
    else
        echo "ERROR: python3 or python not found in PATH." >&2
        exit 1
    fi
    "${PYTHON}" -m pip install --user -e "${REPO_ROOT}"
    ok "Installed via pip (editable, --user)."
fi

# ---------------------------------------------------------------------------
# 4. Install systemd user unit (if systemd is available)
# ---------------------------------------------------------------------------
if command -v systemctl >/dev/null 2>&1; then
    SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
    mkdir -p "${SYSTEMD_USER_DIR}"
    cp "${REPO_ROOT}/deploy/herdmaster.service" "${SYSTEMD_USER_DIR}/herdmaster.service"
    chmod 0644 "${SYSTEMD_USER_DIR}/herdmaster.service"
    ok "Installed systemd user unit to ${SYSTEMD_USER_DIR}/herdmaster.service"

    info "Reloading systemd daemon..."
    if systemctl --user daemon-reload; then
        ok "systemd daemon reloaded."
    else
        warn "Could not reload the user daemon. Run 'systemctl --user daemon-reload' after logging into a systemd user session."
    fi
else
    warn "systemctl not found; skipping systemd unit installation."
    warn "You can still run 'herdmaster start' directly."
fi

# ---------------------------------------------------------------------------
# 5. Print next steps
# ---------------------------------------------------------------------------
cat <<'EOF'

========================================
  HerdMaster Installation Complete
========================================

Quick-start commands:

  herdmaster start          # Start in foreground (dev)
  herdmaster status         # Check health
  herdmaster stop           # Stop foreground process

systemd (--user) service:

  systemctl --user enable herdmaster   # Enable auto-start on login
  systemctl --user start  herdmaster   # Start now
  systemctl --user status herdmaster   # View status / logs
  journalctl --user -u herdmaster -f   # Follow logs

Configuration file:

  ~/.config/herdmaster/config.toml

Uninstall:

  systemctl --user stop    herdmaster
  systemctl --user disable herdmaster
  rm ~/.config/systemd/user/herdmaster.service
  systemctl --user daemon-reload
  # If installed via pipx:   pipx uninstall herdmaster
  # If installed via pip:    pip uninstall herdmaster

========================================
EOF

ok "Installation finished."
