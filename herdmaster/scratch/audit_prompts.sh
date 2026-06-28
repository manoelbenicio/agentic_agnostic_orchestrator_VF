#!/usr/bin/env bash
date -u
echo "=== HERDMASTER TASK PROMPTS (injected to agents) ==="
find /home/dataops-lab/.config/herdmaster/prompts/ -type f | sort | while read -r f; do
    echo "---"
    echo "FILE: $f"
    echo "SIZE_BYTES: $(wc -c < "$f")"
    echo "MD5:    $(md5sum "$f" | awk '{print $1}')"
    echo "SHA256: $(sha256sum "$f" | awk '{print $1}')"
done

echo ""
echo "=== TECH LEAD / AGENT PROMPTS IN PROJECT ==="
find /mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/docs/agent-prompts/ -type f | sort | while read -r f; do
    echo "---"
    echo "FILE: $f"
    echo "SIZE_BYTES: $(wc -c < "$f")"
    echo "MD5:    $(md5sum "$f" | awk '{print $1}')"
    echo "SHA256: $(sha256sum "$f" | awk '{print $1}')"
done

echo ""
echo "=== PRD / TECH LEAD PROMPTS ==="
find /mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/docs/herdmaster-prd/ -type f -name "*.md" | sort | while read -r f; do
    echo "---"
    echo "FILE: $f"
    echo "SIZE_BYTES: $(wc -c < "$f")"
    echo "MD5:    $(md5sum "$f" | awk '{print $1}')"
    echo "SHA256: $(sha256sum "$f" | awk '{print $1}')"
done

echo ""
echo "=== AGENTS.md ==="
f="/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/.agents/AGENTS.md"
echo "FILE: $f"
echo "SIZE_BYTES: $(wc -c < "$f")"
echo "MD5:    $(md5sum "$f" | awk '{print $1}')"
echo "SHA256: $(sha256sum "$f" | awk '{print $1}')"
