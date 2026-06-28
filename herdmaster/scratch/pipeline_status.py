#!/usr/bin/env python3
import sqlite3
import sys
from datetime import datetime

DB = "/home/dataops-lab/.config/herdmaster/herdmaster.db"
print(f"TIMESTAMP: {datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}")
print(f"DB: {DB}\n")

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# Task counts by state
print("=== TASK COUNTS BY STATE ===")
for row in conn.execute("SELECT state, COUNT(*) as total FROM tasks GROUP BY state ORDER BY total DESC"):
    print(f"  {row['state']:15} {row['total']}")

# Queued
print("\n=== QUEUED TASKS ===")
rows = conn.execute("SELECT id, title, assigned_to, updated_at FROM tasks WHERE state='queued'").fetchall()
if rows:
    for r in rows:
        print(f"  [{r['id'][:24]}] {r['title'][:50]} | agent={r['assigned_to']} | updated={r['updated_at']}")
else:
    print("  (none)")

# In progress
print("\n=== IN_PROGRESS TASKS ===")
rows = conn.execute("SELECT id, title, assigned_to, updated_at FROM tasks WHERE state='in_progress'").fetchall()
if rows:
    for r in rows:
        print(f"  [{r['id'][:24]}] {r['title'][:50]} | agent={r['assigned_to']} | updated={r['updated_at']}")
else:
    print("  (none)")

# Failed recent
print("\n=== FAILED TASKS (last 5) ===")
rows = conn.execute("SELECT id, title, assigned_to, error_message, updated_at FROM tasks WHERE state='failed' ORDER BY updated_at DESC LIMIT 5").fetchall()
if rows:
    for r in rows:
        err = (r['error_message'] or '')[:80]
        print(f"  [{r['id'][:24]}] {r['title'][:40]} | agent={r['assigned_to']} | err={err} | {r['updated_at']}")
else:
    print("  (none)")

# Agents
print("\n=== AGENTS STATE ===")
for r in conn.execute("SELECT id, name, state, health, last_seen_at FROM agents ORDER BY last_seen_at DESC"):
    print(f"  {r['id']:10} | {r['name']:30} | state={r['state']:12} | health={r['health']:10} | seen={r['last_seen_at']}")

# w6:p8 recent events
print("\n=== w6:p8 RECENT EVENTS (last 8) ===")
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
if 'events' in tables:
    rows = conn.execute("SELECT event_type, payload, created_at FROM events WHERE payload LIKE '%w6:p8%' ORDER BY created_at DESC LIMIT 8").fetchall()
    for r in rows:
        print(f"  {r['created_at']} | {r['event_type']} | {str(r['payload'])[:100]}")
else:
    print(f"  Tables available: {tables}")

conn.close()
