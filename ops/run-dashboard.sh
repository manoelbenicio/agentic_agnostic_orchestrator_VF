#!/usr/bin/env bash
# AOP — Launcher do Status 360 Dashboard
# COMO USAR (em um terminal WSL/bash novo, para não poluir o terminal do agente):
#   bash <repo>/AOP/ops/run-dashboard.sh
# ou, se já estiver na pasta AOP/ops:   bash run-dashboard.sh
# Ctrl+C para sair.

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$DIR/status360.py"

# UTF-8 para os emojis do semáforo
export LANG="${LANG:-C.UTF-8}"
export PYTHONIOENCODING=utf-8

command -v python3 >/dev/null 2>&1 || { echo "ERRO: python3 não encontrado no PATH."; exit 1; }
[ -f "$SCRIPT" ] || { echo "ERRO: não achei $SCRIPT"; exit 1; }

echo "Iniciando o AOP Status 360 (refresh 60s). Ctrl+C para sair..."
sleep 1
exec python3 "$SCRIPT" --watch
