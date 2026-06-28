#!/usr/bin/env bash
date -u
echo "=== HERDMASTER TASK PROMPTS ==="
for f in /home/dataops-lab/.config/herdmaster/prompts/task-*.md; do
    echo "FILE: $f"
    stat -c "BIRTH: %w | MODIFIED: %y" "$f" 2>/dev/null || stat -c "MODIFIED: %y" "$f"
done

echo ""
echo "=== AGENT PROMPTS ==="
for f in \
    /mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/docs/agent-prompts/README.md \
    /mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/docs/agent-prompts/codex-1-canvas-builder.md \
    /mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/docs/agent-prompts/codex-2-studio.md \
    /mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/docs/agent-prompts/gemini-1-reconciler-voice.md \
    /mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/docs/agent-prompts/gemini-2-dashboard-quality.md; do
    echo "FILE: $f"
    stat -c "BIRTH: %w | MODIFIED: %y" "$f" 2>/dev/null || stat -c "MODIFIED: %y" "$f"
done

echo ""
echo "=== PRD DOCS ==="
for f in \
    /mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/docs/herdmaster-prd/AGENT_BRIEFING.md \
    /mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/docs/herdmaster-prd/PRD_HerdMaster_v1.0.md \
    /mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/docs/herdmaster-prd/RESEARCH_Herdr_Capabilities.md \
    /mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/docs/herdmaster-prd/ROADMAP_Agile_Sprints.md \
    /mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/docs/herdmaster-prd/TECH_LEAD_PROMPT.md; do
    echo "FILE: $f"
    stat -c "BIRTH: %w | MODIFIED: %y" "$f" 2>/dev/null || stat -c "MODIFIED: %y" "$f"
done

echo ""
echo "=== GOVERNANCE ==="
for f in \
    /mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/.agents/AGENTS.md \
    /mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/checkin_checkout.md; do
    echo "FILE: $f"
    stat -c "BIRTH: %w | MODIFIED: %y" "$f" 2>/dev/null || stat -c "MODIFIED: %y" "$f"
done
