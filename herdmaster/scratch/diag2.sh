#!/usr/bin/env bash
date -u
echo "--- Herdr sock file ---"
ls -la /home/dataops-lab/.config/herdr/herdr.sock 2>/dev/null || echo "NOT FOUND"

echo "--- Herdr process running? ---"
ps aux | grep -i "[h]erdr" | grep -v grep || echo "NO HERDR PROCESS FOUND"

echo "--- Test socket alive via python ---"
python3 << 'EOF'
import socket
s = socket.socket(socket.AF_UNIX)
r = s.connect_ex('/home/dataops-lab/.config/herdr/herdr.sock')
if r == 0:
    print("HERDR SOCKET: ALIVE")
else:
    print(f"HERDR SOCKET: DEAD (errno={r})")
s.close()
EOF

echo "--- HerdMaster dispatch_loop — last lines from DB WAL ---"
strings /home/dataops-lab/.config/herdmaster/herdmaster.db-wal 2>/dev/null | grep -i "dispatch\|inject\|failed\|error\|herdr\|pane\|idle\|wait" | tail -20

echo "--- HerdMaster stdout pipe consumer ---"
cat /proc/$(cat /home/dataops-lab/.config/herdmaster/herdmaster.pid)/fd/1 2>/dev/null | head -5 || echo "pipe has no reader or empty"

echo "--- Check via herdr CLI if socket responds ---"
herdr workspace list 2>&1 | head -5 || echo "herdr CLI not in PATH"
/home/dataops-lab/.local/bin/herdr workspace list 2>&1 | head -5 || echo "herdr not at .local/bin"
find /home/dataops-lab/.local/bin/ -name 'herdr*' 2>/dev/null
