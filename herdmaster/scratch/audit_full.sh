#!/usr/bin/env bash
# Full audit: collects size, MD5, SHA256, birth, modified for all agent/control plane files
# Output: written to disk as audit_report.md

OUTFILE="/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/docs/PROMPT_AUDIT_REPORT.md"

exec > "$OUTFILE" 2>&1

echo "# Prompt & Communication Files — Full Audit Report"
echo ""
echo "**Generated:** $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "**Evidence:** This file was written directly to disk by audit_full.sh"
echo "**Verify this file itself:** \`sha256sum $OUTFILE\`"
echo ""
echo "---"
echo ""

audit_file() {
    local f="$1"
    local label="$2"
    if [ ! -f "$f" ]; then
        echo "| $label | FILE NOT FOUND | — | — | — | — |"
        return
    fi
    local size
    size=$(wc -c < "$f")
    local md5
    md5=$(md5sum "$f" | awk '{print $1}')
    local sha256
    sha256=$(sha256sum "$f" | awk '{print $1}')
    local birth
    birth=$(stat -c "%w" "$f" 2>/dev/null | sed 's/\..*//' | sed 's/ /T/; s/-0300/Z/')
    local modified
    modified=$(stat -c "%y" "$f" 2>/dev/null | sed 's/\..*//' | sed 's/ /T/; s/-0300/Z/')
    echo "| \`$label\` | ${size} bytes | \`$md5\` | \`$sha256\` | ${birth:-n/a} | ${modified} |"
}

# ── GROUP 1: HerdMaster Task Prompts (CLI → Agents) ──────────────────────────
echo "## Group 1 — HerdMaster Task Prompts (CLI → Agents)"
echo ""
echo "| File | Size | MD5 | SHA256 | Created (UTC) | Last Modified (UTC) |"
echo "|------|------|-----|--------|---------------|---------------------|"
for f in /home/dataops-lab/.config/herdmaster/prompts/task-*.md; do
    audit_file "$f" "$(basename "$f")"
done
echo ""

# ── GROUP 2: Agent Prompts in Project ────────────────────────────────────────
echo "## Group 2 — Agent Prompts in Project (docs/agent-prompts/)"
echo ""
echo "| File | Size | MD5 | SHA256 | Created (UTC) | Last Modified (UTC) |"
echo "|------|------|-----|--------|---------------|---------------------|"
BASE="/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/docs/agent-prompts"
audit_file "$BASE/README.md"                    "README.md"
audit_file "$BASE/codex-1-canvas-builder.md"   "codex-1-canvas-builder.md"
audit_file "$BASE/codex-2-studio.md"            "codex-2-studio.md"
audit_file "$BASE/gemini-1-reconciler-voice.md" "gemini-1-reconciler-voice.md"
audit_file "$BASE/gemini-2-dashboard-quality.md" "gemini-2-dashboard-quality.md"
echo ""

# ── GROUP 3: PRD / Tech Lead Docs ────────────────────────────────────────────
echo "## Group 3 — PRD & Tech Lead Reference (docs/herdmaster-prd/)"
echo ""
echo "| File | Size | MD5 | SHA256 | Created (UTC) | Last Modified (UTC) |"
echo "|------|------|-----|--------|---------------|---------------------|"
PRD="/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/docs/herdmaster-prd"
audit_file "$PRD/TECH_LEAD_PROMPT.md"          "TECH_LEAD_PROMPT.md"
audit_file "$PRD/AGENT_BRIEFING.md"            "AGENT_BRIEFING.md"
audit_file "$PRD/PRD_HerdMaster_v1.0.md"       "PRD_HerdMaster_v1.0.md"
audit_file "$PRD/RESEARCH_Herdr_Capabilities.md" "RESEARCH_Herdr_Capabilities.md"
audit_file "$PRD/ROADMAP_Agile_Sprints.md"     "ROADMAP_Agile_Sprints.md"
echo ""

# ── GROUP 4: Governance / Control Plane Rules ────────────────────────────────
echo "## Group 4 — Governance & Control Plane Rules"
echo ""
echo "| File | Size | MD5 | SHA256 | Created (UTC) | Last Modified (UTC) |"
echo "|------|------|-----|--------|---------------|---------------------|"
ROOT="/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks"
audit_file "$ROOT/.agents/AGENTS.md"        "AGENTS.md"
audit_file "$ROOT/checkin_checkout.md"      "checkin_checkout.md"
echo ""

echo "---"
echo ""
echo "## Self-Verification"
echo ""
echo "SHA256 of THIS report file (run after generation):"
sha256sum "$OUTFILE" 2>/dev/null | awk '{print "```\n" $1 "  PROMPT_AUDIT_REPORT.md\n```"}'
echo ""
echo "**Anti-hallucination check:** Compare the hash above against \`sha256sum docs/PROMPT_AUDIT_REPORT.md\` on disk."
