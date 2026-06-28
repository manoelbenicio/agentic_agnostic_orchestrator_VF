#!/usr/bin/env bash
date -u
DB="/home/dataops-lab/.config/herdmaster/herdmaster.db"

echo "=== TASK COUNTS BY STATE ==="
sqlite3 "$DB" "SELECT state, COUNT(*) as total FROM tasks GROUP BY state ORDER BY total DESC;"

echo ""
echo "=== QUEUED TASKS ==="
sqlite3 "$DB" "SELECT substr(id,1,20), title, assigned_to, updated_at FROM tasks WHERE state='queued';"

echo ""
echo "=== IN_PROGRESS TASKS ==="
sqlite3 "$DB" "SELECT substr(id,1,20), title, assigned_to, updated_at FROM tasks WHERE state='in_progress';"

echo ""
echo "=== FAILED TASKS (last 5) ==="
sqlite3 "$DB" "SELECT substr(id,1,20), title, assigned_to, error_message, updated_at FROM tasks WHERE state='failed' ORDER BY updated_at DESC LIMIT 5;"

echo ""
echo "=== AGENTS HEALTH ==="
sqlite3 "$DB" "SELECT id, name, state, health, last_seen_at FROM agents ORDER BY last_seen_at DESC;"

echo ""
echo "=== w6:p8 RECOVERY EVENTS (last 10) ==="
sqlite3 "$DB" "SELECT event_type, payload, created_at FROM events WHERE payload LIKE '%w6:p8%' ORDER BY created_at DESC LIMIT 10;" 2>/dev/null || echo "no events table or no entries"
