#!/usr/bin/env bash
set -e

echo "=== TIMESTAMP ==="
date -u

echo "=== HM PID ==="
HM_PID=$(cat /home/dataops-lab/.config/herdmaster/herdmaster.pid)
echo "PID: $HM_PID"

echo "=== PROCESS STATUS ==="
ps aux | grep "$HM_PID" | grep -v grep

echo "=== OPEN FILE DESCRIPTORS (logs) ==="
ls -la /proc/"$HM_PID"/fd 2>/dev/null | grep -v "socket\|pipe\|anon" | head -20

echo "=== LOG FILES VIA FD ==="
for fd in /proc/"$HM_PID"/fd/*; do
    target=$(readlink "$fd" 2>/dev/null || true)
    if [[ "$target" == *.log* ]] || [[ "$target" == *.jsonl* ]]; then
        echo "fd=$fd -> $target"
    fi
done

echo "=== STDERR/STDOUT via /proc ==="
for fd in 1 2; do
    target=$(readlink /proc/"$HM_PID"/fd/$fd 2>/dev/null || true)
    echo "fd[$fd] -> $target"
done

echo "=== DB WAL SIZE (activity indicator) ==="
ls -lh /home/dataops-lab/.config/herdmaster/herdmaster.db-wal 2>/dev/null

echo "=== DISPATCH LOG FROM DB (last 20 events) ==="
/home/dataops-lab/.local/bin/herdmaster tasks list --state in_progress 2>&1 | head -50

echo "=== QUEUED TASKS ==="
/home/dataops-lab/.local/bin/herdmaster tasks list --state queued 2>&1

echo "=== HERDR SOCKET STATUS ==="
ls -la /home/dataops-lab/.config/herdr/herdr.sock 2>/dev/null || echo "herdr.sock NOT FOUND"
