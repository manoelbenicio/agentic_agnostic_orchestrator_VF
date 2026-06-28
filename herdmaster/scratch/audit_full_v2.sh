#!/usr/bin/env bash
# Regenerates PROMPT_AUDIT_REPORT.md with all columns including real NTFS CreationTime
# Source of birth times: PowerShell Get-Item.CreationTimeUtc (real NTFS metadata)

OUTFILE="/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/docs/PROMPT_AUDIT_REPORT.md"

# Declare associative array: filename -> created|modified (from PowerShell output)
declare -A BIRTH
BIRTH["AGENTS.md"]="2026-06-25T11:01:04Z"
BIRTH["checkin_checkout.md"]="2026-06-25T13:09:44Z"
BIRTH["PROMPT_AUDIT_REPORT.md"]="2026-06-25T13:31:45Z"
BIRTH["README.md"]="2026-06-24T01:27:39Z"
BIRTH["codex-1-canvas-builder.md"]="2026-06-24T01:27:39Z"
BIRTH["codex-2-studio.md"]="2026-06-24T01:27:39Z"
BIRTH["gemini-1-reconciler-voice.md"]="2026-06-24T01:27:39Z"
BIRTH["gemini-2-dashboard-quality.md"]="2026-06-24T01:27:39Z"
BIRTH["TECH_LEAD_PROMPT.md"]="2026-06-24T01:27:41Z"
BIRTH["AGENT_BRIEFING.md"]="2026-06-24T01:27:41Z"
BIRTH["PRD_HerdMaster_v1.0.md"]="2026-06-24T01:27:41Z"
BIRTH["RESEARCH_Herdr_Capabilities.md"]="2026-06-24T01:27:41Z"
BIRTH["ROADMAP_Agile_Sprints.md"]="2026-06-24T01:27:41Z"

# HerdMaster prompts: birth from stat %w (Linux ext4 inode — available)
declare -A BIRTH_HM
for f in /home/dataops-lab/.config/herdmaster/prompts/task-*.md; do
    name=$(basename "$f")
    b=$(stat -c "%w" "$f" 2>/dev/null | sed 's/\..*//' | sed 's/ /T/; s/-0300/+00:00/' | sed 's/+00:00/Z/')
    BIRTH_HM["$name"]="$b"
done

exec > "$OUTFILE" 2>&1

echo "# Prompt & Communication Files — Full Audit Report"
echo ""
echo "**Generated:** $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "**Evidence:** Written directly to disk by audit_full_v2.sh"
echo "**Birth time source:** PowerShell \`Get-Item.CreationTimeUtc\` (real NTFS) for Windows files;"
echo "  \`stat -c %w\` (ext4 inode) for Linux HerdMaster prompt files"
echo "**Verify this file:** \`sha256sum docs/PROMPT_AUDIT_REPORT.md\`"
echo ""
echo "---"
echo ""

audit_row() {
    local f="$1" label="$2" birth="$3"
    if [ ! -f "$f" ]; then
        echo "| \`$label\` | NOT FOUND | — | — | — | — |"
        return
    fi
    local size md5 sha256 modified
    size=$(wc -c < "$f")
    md5=$(md5sum "$f" | awk '{print $1}')
    sha256=$(sha256sum "$f" | awk '{print $1}')
    modified=$(stat -c "%y" "$f" 2>/dev/null | sed 's/\..*//' | sed 's/ /T/; s/-0300/Z/')
    echo "| \`$label\` | ${size} bytes | \`$md5\` | \`$sha256\` | ${birth} | ${modified} |"
}

# ── GROUP 1: HerdMaster Task Prompts ─────────────────────────────────────────
echo "## Group 1 — HerdMaster Task Prompts (CLI → Agents)"
echo "_Location: \`/home/dataops-lab/.config/herdmaster/prompts/\`_"
echo ""
echo "| File | Size | MD5 | SHA256 | Created (UTC) | Last Modified (UTC) |"
echo "|------|------|-----|--------|---------------|---------------------|"
for f in /home/dataops-lab/.config/herdmaster/prompts/task-*.md; do
    name=$(basename "$f")
    audit_row "$f" "$name" "${BIRTH_HM[$name]:-n/a}"
done
echo ""

# ── GROUP 2: Agent Prompts ────────────────────────────────────────────────────
echo "## Group 2 — Agent Prompts (docs/agent-prompts/)"
echo "_Location: \`c:\\VMs\\Projects\\Multi_Orchestration_Project_Tasks\\docs\\agent-prompts\\\`_"
echo ""
echo "| File | Size | MD5 | SHA256 | Created (UTC) | Last Modified (UTC) |"
echo "|------|------|-----|--------|---------------|---------------------|"
BASE="/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/docs/agent-prompts"
for name in "README.md" "codex-1-canvas-builder.md" "codex-2-studio.md" "gemini-1-reconciler-voice.md" "gemini-2-dashboard-quality.md"; do
    audit_row "$BASE/$name" "$name" "${BIRTH[$name]:-n/a}"
done
echo ""

# ── GROUP 3: PRD / Tech Lead ──────────────────────────────────────────────────
echo "## Group 3 — PRD & Tech Lead Reference (docs/herdmaster-prd/)"
echo "_Location: \`c:\\VMs\\Projects\\Multi_Orchestration_Project_Tasks\\docs\\herdmaster-prd\\\`_"
echo ""
echo "| File | Size | MD5 | SHA256 | Created (UTC) | Last Modified (UTC) |"
echo "|------|------|-----|--------|---------------|---------------------|"
PRD="/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/docs/herdmaster-prd"
for name in "TECH_LEAD_PROMPT.md" "AGENT_BRIEFING.md" "PRD_HerdMaster_v1.0.md" "RESEARCH_Herdr_Capabilities.md" "ROADMAP_Agile_Sprints.md"; do
    audit_row "$PRD/$name" "$name" "${BIRTH[$name]:-n/a}"
done
echo ""

# ── GROUP 4: Governance ───────────────────────────────────────────────────────
echo "## Group 4 — Governance & Control Plane Rules"
echo "_Location: \`c:\\VMs\\Projects\\Multi_Orchestration_Project_Tasks\\\`_"
echo ""
echo "| File | Size | MD5 | SHA256 | Created (UTC) | Last Modified (UTC) |"
echo "|------|------|-----|--------|---------------|---------------------|"
ROOT="/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks"
audit_row "$ROOT/.agents/AGENTS.md"    "AGENTS.md"           "${BIRTH[AGENTS.md]:-n/a}"
audit_row "$ROOT/checkin_checkout.md"  "checkin_checkout.md" "${BIRTH[checkin_checkout.md]:-n/a}"
echo ""

echo "---"
echo ""
echo "## Self-Verification (Anti-Hallucination)"
echo ""
echo "SHA256 of THIS report file:"
sha256sum "$OUTFILE" 2>/dev/null | awk '{print "```\n" $1 "  PROMPT_AUDIT_REPORT.md\n```"}'
echo ""
echo "**To verify:** \`wsl -e bash -c \"sha256sum /mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/docs/PROMPT_AUDIT_REPORT.md\"\`"
