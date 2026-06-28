#!/usr/bin/env bash
# Verifica birthtime via múltiplos métodos
date -u

echo "=== METHOD 1: stat %W (epoch seconds of birth) ==="
for f in \
    "/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/.agents/AGENTS.md" \
    "/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/checkin_checkout.md" \
    "/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/docs/PROMPT_AUDIT_REPORT.md" \
    "/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/docs/agent-prompts/README.md" \
    "/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/docs/herdmaster-prd/TECH_LEAD_PROMPT.md"; do
    birth_epoch=$(stat -c "%W" "$f" 2>/dev/null)
    birth_human=$(stat -c "%w" "$f" 2>/dev/null)
    echo "FILE: $(basename $f)"
    echo "  BIRTH_EPOCH: $birth_epoch"
    echo "  BIRTH_HUMAN: $birth_human"
done

echo ""
echo "=== METHOD 2: Python statx (direct syscall) ==="
python3 << 'EOF'
import os
import time

files = [
    "/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/.agents/AGENTS.md",
    "/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/checkin_checkout.md",
    "/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/docs/PROMPT_AUDIT_REPORT.md",
    "/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/docs/agent-prompts/README.md",
    "/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/docs/herdmaster-prd/TECH_LEAD_PROMPT.md",
]
for f in files:
    try:
        r = os.stat(f)
        print(f"FILE: {os.path.basename(f)}")
        # st_birthtime available on some platforms
        if hasattr(r, 'st_birthtime'):
            print(f"  st_birthtime: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(r.st_birthtime))}")
        else:
            print(f"  st_birthtime: NOT AVAILABLE via os.stat")
        print(f"  st_mtime:     {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(r.st_mtime))}")
        print(f"  st_ctime:     {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(r.st_ctime))}")
    except Exception as e:
        print(f"FILE: {f} ERROR: {e}")
EOF

echo ""
echo "=== METHOD 3: /proc/self/mountinfo — check DrvFs mount options ==="
grep -i "drvfs\|ntfs\|9p" /proc/self/mountinfo | grep -i "VMs\|Projects\|mnt/c" | head -5
