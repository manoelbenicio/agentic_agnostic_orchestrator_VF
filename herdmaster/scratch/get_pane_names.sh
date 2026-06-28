#!/usr/bin/env bash
echo "=== HERDR PANES ==="
/home/dataops-lab/.local/bin/herdr pane list --json 2>/dev/null | python3 -c "
import sys, json
raw = sys.stdin.read()
data = json.loads(raw)

# handle different response shapes
panes = []
if isinstance(data, dict):
    result = data.get('result', data)
    if isinstance(result, dict):
        panes = result.get('panes', [])
    elif isinstance(result, list):
        panes = result
elif isinstance(data, list):
    panes = data

for p in panes:
    pane_id = p.get('id') or p.get('pane_id') or '?'
    title   = p.get('title') or p.get('name') or p.get('label') or '(sem nome)'
    print(f'  {pane_id:12} -> {title}')
" 2>/dev/null

echo ""
echo "=== AGENTS from DB ==="
python3 -c "
import sqlite3
conn = sqlite3.connect('/home/dataops-lab/.config/herdmaster/herdmaster.db')
cols = [r[1] for r in conn.execute('PRAGMA table_info(agents)').fetchall()]
print('  Columns:', cols)
for row in conn.execute('SELECT * FROM agents ORDER BY updated_at DESC LIMIT 20'):
    print(' ', dict(zip(cols, row)))
conn.close()
"
