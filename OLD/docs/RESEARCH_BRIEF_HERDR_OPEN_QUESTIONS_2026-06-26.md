# Herdr — Research Brief & Open Questions (for deep-research teams)

**Date:** 2026-06-26
**Author context:** HerdMaster multi-agent orchestration project
**Purpose:** Hand-off document for a separate research team to investigate open questions
about controlling/verifying coding agents inside Herdr. Each question is self-contained with
full context so no prior conversation knowledge is required.

> Canonical Herdr docs to verify any answer against:
> - Docs root: https://herdr.dev/docs/
> - Socket API: https://herdr.dev/docs/socket-api/
> - Agents / detection: https://herdr.dev/docs/agents/
> - Integrations: https://herdr.dev/docs/integrations/
> - Configuration: https://herdr.dev/docs/configuration/
> - CLI reference: https://herdr.dev/docs/cli-reference/
> - SKILL.md (agent-operates-Herdr): https://raw.githubusercontent.com/ogulcancelik/herdr/master/SKILL.md
> - Agent guide (agent-teaches-human): https://herdr.dev/agent-guide.md
> - Repo: https://github.com/ogulcancelik/herdr

---

## 0. Environment & fleet (ground truth — already verified live)

- **Host:** Linux (WSL2 under Windows), shell `/bin/bash`. Herdr server **running**.
- **Herdr version family:** 0.7.0 (per bundled doc copies).
- **`herdr` binary:** `/home/dataops-lab/.local/bin/herdr`
- **Pane ID format in THIS session:** `w8:pQ`, `w8:pR`, `w8:p14` (i.e. `w<N>:p<X>`).
  NOTE: official SKILL.md examples use a different format (`1-1`, `1:1`, `1`). This discrepancy
  is unexplained — see Q7.
- **Fleet = three harnesses only** (model behind them is irrelevant to Herdr; it detects the CLI):

  | Herdr `agent` label | Harness (what it really is)                | Live panes            | Integration available? | State source today |
  |---------------------|--------------------------------------------|-----------------------|------------------------|--------------------|
  | `codex`             | OpenAI Codex CLI                           | w8:pQ, w8:pR, w8:pS   | session-only, **outdated (v5 < v6)** | screen manifest, rule `osc_title_idle` matches |
  | `agy`               | **Antigravity = Google = Gemini** (one thing) | w8:pJ, w8:pY       | **NONE**               | screen manifest, `default_known_agent_idle_fallback` |
  | `kiro`              | Kiro (AWS)                                 | w8:p12, w8:p14, w8:pG | **NONE**               | screen manifest, `default_known_agent_idle_fallback` |

- **Distinct agent labels in live roster (verified):** `['agy', 'codex', 'kiro']`.
  No `gemini`, `antigravity`, or `claude` labels exist. There are **no Claude Code panes**.
- **`herdr integration status` (verified output):**
  - `codex: outdated (v5 < v6)` — session integration installed but stale.
  - `claude: not installed` — irrelevant (no Claude panes).
  - `opencode: outdated (v5 < v7)` — not in active fleet.
  - `agy`, `kiro` — **absent from the integration list entirely** (no integration exists).

### What we already know for certain (do NOT re-research, use as constraints)
1. `herdr pane run <pane> "<cmd>"` sends **text + a real Enter** (submits). Confirmed in docs + live.
2. `herdr pane send-text <pane> "<txt>"` / socket `pane.send_text` = literal text, **no Enter**.
3. `herdr pane send-keys <pane> <key>` = key events. Tokens are **lowercase**: `enter`, `esc`,
   `ctrl+u`, `ctrl+h`, `alt+x`, `shift+tab`, `f1`, `minus`, `plus`. (SKILL.md shows `Enter`
   capitalized in examples; both appear to be accepted — see Q7.)
4. `herdr agent explain <pane> --json` returns (real keys, verified live): `state` (str),
   `matched_rule` (object `{id, state, priority, region}` or null), `fallback_reason`
   (str or null), `evaluated_rules` (array), `manifest_source`, `manifest_version`,
   `local_override_shadowing_remote` (bool), `visible_idle/visible_working/visible_blocker`.
5. Codex/Claude/Cursor/Copilot/Droid/Qoder = **session-identity integrations only**; state always
   comes from screen manifest. Lifecycle-authority integrations (hooks author idle/working/blocked)
   exist ONLY for: Pi, OMP, Kimi, OpenCode, Kilo, Hermes. **None of our 3 harnesses can become a
   lifecycle authority.**
6. Blocked detection is strict: Herdr marks `blocked` only when the bottom-buffer matches a known
   approval/question/permission UI rule. Otherwise it falls back to `idle` labeled
   `default_known_agent_idle_fallback`.
7. Local manifest overrides live at `~/.config/herdr/agent-detection/<agent>.toml` and always win.
   Apply with `herdr server reload-agent-manifests` (or restart). Debug with
   `herdr agent explain --file screen.txt --agent <name> --json`.
8. Remote manifests only PATCH detection for agents Herdr already knows. Adding a brand-new agent
   requires a Herdr binary update. (Relevant: is `agy`/`kiro` detection patchable remotely, or only
   locally? — see Q3.)

---

## OPEN QUESTIONS

### Q1 — Manifest override schema for AGY (Antigravity/Gemini) and Kiro idle/blocked rules  ★HIGHEST VALUE
**Why it matters:** 5 of our 8 panes (`agy` + `kiro`) have NO integration path and currently
detect only as `default_known_agent_idle_fallback` — meaning Herdr is *guessing* idle and cannot
distinguish "ready" from "stuck/blocked". A local manifest override is the ONLY durable fix.

**What we need:**
- The exact TOML schema for `~/.config/herdr/agent-detection/<agent>.toml`. From observed
  `agent explain` output, rules appear to have: `id`, `priority`, `region`
  (`osc_title` | `after_last_prompt_marker` | `whole_recent` | …), `state`
  (`idle` | `working` | `blocked` | `unknown`), and an `evidence` block with keys:
  `contains` (list), `regex` (list), `line_regex` (list), `all_count`, `any_count`, `not_count`,
  `region_bytes`. **Confirm the authoritative, complete field list and semantics of each.**
- What are the valid values for `region`? Full enumeration.
- How is `priority` ordered (higher wins? what are the bundled priority bands — we saw 1100, 1050,
  1000, 900, 600, 100)?
- Matching semantics: how do `contains` / `regex` / `line_regex` combine with `all_count` /
  `any_count` / `not_count`? Is it "match if any_count of `contains` hit"? Exact boolean logic.
- Can a local override file ADD rules to a known agent while inheriting bundled rules, or does it
  fully REPLACE the agent's ruleset? (Doc says "local overrides always win" — does "win" mean
  replace-all or merge?)
- Is there a published example/template `<agent>.toml` we can copy?

### Q2 — Capturing the real screen shapes for AGY and Kiro idle/working/blocked
**Why it matters:** Writing Q1's rules requires knowing the actual bottom-buffer text each harness
shows in each state.

**What we need:**
- Best practice for capturing the detection snapshot: is `herdr pane read <pane> --source detection`
  the exact text the matcher sees? The docs mention `--source detection` returns "the bottom-buffer
  snapshot used by agent screen detection" — confirm this is the canonical capture for authoring rules.
- Does `agent explain --json`'s `evaluated_rules[].evidence.region_preview` give us enough of the
  real screen, or do we need a fuller dump? How to get the full untruncated region text.
- For `agy` (Antigravity) and `kiro` (Kiro/AWS) specifically: are there community/bundled manifests
  anywhere we can start from, or are we authoring from scratch? (They're absent from the integration
  list — but bundled *detection* manifests may still exist independent of integrations.)

### Q3 — Are `agy` and `kiro` "known" agents to Herdr's detector, or unknown?
**Why it matters:** Doc says remote manifests only patch agents Herdr "already knows how to
identify"; brand-new agents need a binary update. Herdr clearly already *labels* our panes `agy`
and `kiro`, so process detection exists — but we need to know the boundary.

**What we need:**
- Confirm `agy` and `kiro` are first-class known agents (so local manifest overrides for them are
  supported and will be honored), vs. generically detected.
- Output interpretation help for `herdr server agent-manifests` (lists active manifest sources per
  agent) — does it list `agy` and `kiro`? What does presence/absence imply for override support?
- Accepted `--agent` names for `agent explain --file ... --agent <name>`: the config doc's
  `cjk_ime_agents` list includes `agy`, `kiro`, `gemini`, etc. Is the `--agent` flag's accepted set
  the same? Full list.

### Q4 — Codex command-palette stall: detect as `blocked` via override?
**Why it matters:** When a Codex pane has its `/` command palette open, the parked command's Enter
is consumed by the palette and the pane stalls. Herdr currently still reports `idle` (rule
`osc_title_idle` matches on the title region regardless of palette state). We want Herdr to detect
this stall as `blocked`.

**What we need:**
- Can a higher-priority local override rule for `codex` match the palette's bottom-buffer signature
  and classify it `blocked`, WITHOUT breaking the existing session-identity integration? (Doc says
  overrides affect detection only; integrations provide session identity. Confirm they don't conflict.)
- What does the Codex palette actually render in the detection region? (Capture needed — ties to Q2.)
- Does Codex use `/new` (confirmed working) vs `/chat new`? This is OBSERVED per-CLI behavior, not
  documented. Is there an authoritative list of Codex CLI slash-commands and how the palette
  interacts with programmatic Enter injection?

### Q5 — `wait agent-status` semantics for screen-manifest agents
**Why it matters:** We replaced a blind `sleep` with `herdr wait agent-status <pane> --status idle
--timeout <ms>`. But for `agy`/`kiro`, "idle" is the unreliable fallback-idle.

**What we need:**
- Does `wait agent-status --status idle` resolve on `default_known_agent_idle_fallback`, or only on
  a rule-matched idle? (We believe the former — confirm.)
- Is there a way to wait specifically for a *rule-matched* state vs a fallback?
- `wait output <pane> --match <regex> --regex --timeout` — is matching against
  `--source recent` (unwrapped)? Confirm it's robust to soft-wrapping and is the recommended
  primitive for "agent finished and shows ready prompt".
- Exit codes: confirm `wait` returns exit 1 on timeout (SKILL.md says so) and 0 on match. Any other
  exit codes?

### Q6 — Native session restore: Codex v5→v6 upgrade + restart behavior
**Why it matters:** Our `codex` integration is `outdated (v5 < v6)`. We want `codex resume <id>`
to work after a HerdMaster/Herdr restart.

**What we need:**
- Does re-running `herdr integration install codex` upgrade v5→v6 in place, and is it safe/idempotent?
  What files does it touch (`~/.codex/herdr-agent-state.sh`, `hooks.json`, `config.toml [features]
  hooks=true`)? Confirm uninstall leaves `config.toml` unchanged.
- With `[session] resume_agents_on_restore = true` (default), exactly which restart events trigger
  resume — only `herdr server` restart? What about our own HerdMaster process restart (which does
  NOT restart the Herdr server)? Clarify the boundary: does Herdr-server-survives-our-restart mean
  panes are never actually torn down?
- For `agy` and `kiro`: no session restore exists. On a real Herdr server restart they come back as
  plain shells in the saved cwd. Confirm, and identify any workaround.

### Q7 — Pane/tab/workspace ID format discrepancy
**Why it matters:** Our live session uses `w8:pQ` style; SKILL.md documents `1-1` / `1:1` / `1`.
Code that hardcodes either format will break.

**What we need:**
- Why the difference? Is `w<N>:p<X>` the current 0.7.0 format and `1-1` an older/doc-lagging format,
  or are both valid simultaneously (e.g. legacy aliases)?
- Confirm the durable practice: always re-read IDs from `pane list` / `workspace list` / split
  responses; never persist or guess IDs. (SKILL.md says IDs compact on close — confirm `w8:pQ`-style
  IDs also compact/recycle.)
- Are `w8:pQ`-style IDs stable across a Herdr server restart, or do they change?

### Q8 — `send-keys` token casing & the recovery sequence
**Why it matters:** Our stuck-pane recovery sends `ctrl+u` → `esc` → `ctrl+u` → re-`pane run`.
Socket API doc says lowercase tokens; SKILL.md examples show capitalized `Enter`.

**What we need:**
- Authoritative token grammar for `pane send-keys` / `pane.send_input.keys`. Is it case-insensitive?
  Confirm `ctrl+u`, `esc` are correct (we verified the server accepts them, but want the canonical spec).
- Is there a documented "clear the input line / dismiss palette" idiom per agent, or is
  `ctrl+u` + `esc` a reasonable generic approach?
- Any risk that `send-keys ctrl+u`/`esc` to a *healthy* agent pane causes harm (e.g. interrupting
  a running task)? We want recovery to be safe to fire only on SUSPECT panes — confirm no side effects
  on idle panes.

### Q9 — Notifications & sidebar config for an orchestration rig (Linux/WSL)
**Why it matters:** Default `[ui.toast] delivery = "off"` means blocked agents stall silently.

**What we need:**
- On WSL specifically: `delivery = "system"` needs `notify-send` + `DISPLAY`/`WAYLAND_DISPLAY`
  (often absent in WSL). `delivery = "terminal"` sends escape sequences to the outer terminal
  (Ghostty/iTerm2/Kitty/WezTerm). **Which delivery actually works in a WSL terminal**, and does it
  depend on the Windows terminal emulator hosting the WSL session? Any known-good config for
  Windows Terminal / WezTerm-on-Windows?
- `agent_panel_sort = "priority"` orders by blocked→done→working→idle→unknown. For screen-manifest
  agents whose `blocked` is under-detected (Q1/Q4), does priority sort still surface them, or do they
  hide in `idle` because of fallback? (Reinforces Q1's importance.)
- `delay_seconds` behavior: it notifies only if the pane is still in the same state after the delay.
  For flappy screen detection, what `delay_seconds` avoids false notifications?

### Q10 — SKILL.md install per-harness (codex / agy / kiro)
**Why it matters:** We may install SKILL.md so agents can do read-side coordination
(`pane read`, `wait agent-status` on siblings). Each harness consumes instructions differently.

**What we need:**
- Authoritative install location PER harness:
  - **Codex**: agent guide says include from `~/.codex/AGENTS.md` (global instructions, NOT a
    skills dir). Confirm.
  - **AGY (Antigravity/Gemini)**: where does Antigravity load reusable skills/custom instructions?
    (Repo has `.gemini/skills/` scaffolding — is that real, or do we use a different mechanism?)
  - **Kiro (AWS)**: where does Kiro load skills? (Repo has `.kiro/` — confirm the path and format,
    e.g. `.kiro/steering/` vs a skills dir.)
- The `HERDR_ENV=1` guardrail in SKILL.md is prompt-level only (not enforced). Is there any HARD
  gate Herdr provides to prevent an agent outside Herdr from driving the socket? (We treat HerdMaster
  as the real authority — confirm there's no stronger built-in enforcement we're missing.)

### Q11 — Marketplace plugins worth vetting for multi-agent orchestration
**Why it matters:** We want robust state visibility + remote/notify reach. Plugins are community,
NOT reviewed by Herdr ("install at your own discretion").

**Candidates to evaluate (read source first — security blast radius near agent sockets):**
- `0x5c0f/herdr-insight` (Rust) — "Agent State Timeline Panel". Most relevant to our verification
  problem: does it show rule-matched vs fallback states over time? Does it work for `agy`/`kiro`?
- `Davidcreador/herdr-token-dashboard` / `astkaasa/herdr-tokscale-dashboard` /
  `CodyBontecou/herdr-telemetry-bridge` — per-agent token/cost/telemetry. Which exposes data we
  could feed into HerdMaster's DB?
- `zom-2018/herdr-ntfy-notify` / `dcolinmorgan/herdr-remote` + `herdr-push` /
  `tiny-send/tinysend-herdr` — notify/approve when an agent blocks/finishes (mobile/Telegram/email).
  Which works on Linux/WSL without macOS deps? Reliability of the "blocked" trigger given Q1.
- `andrewchng/herdr-sessionizer` / `razajamil/herdr-plugin-workspace-manager` /
  `shizlie/herdr-setup-bootstrap` / `alon-z/herdr-devup` — declarative TOML layout bootstrap. Could
  any REPLACE parts of our hand-rolled `HerdMaster/ops/bootstrap.sh`? Trade-offs vs keeping bash.
- **For each shortlisted plugin:** What `herdr-plugin.toml` permissions/entrypoints does it declare?
  What sockets/data does it touch? `min_herdr_version`? Linux platform support? Maintenance status?

### Q12 — VM/sandbox wrapper detection (`HERDR_AGENT` hint)
**Why it matters:** On Linux, wrappers (VMs, Bubblewrap, `fence`) hide the real agent process from
host `/proc`, so Herdr may show `agent: unknown`. Fix: `HERDR_AGENT=<agent>` scoped to the
foreground command (e.g. `HERDR_AGENT=kiro fence -- kiro`), NOT exported globally.

**What we need:**
- Do any of our harnesses (codex/agy/kiro) run under a wrapper in our setup such that we need this?
  (Our roster currently shows correct labels, so probably not — but if we sandbox later, confirm the
  exact `HERDR_AGENT` values accepted and that it correctly selects the screen manifest.)
- Does `HERDR_AGENT` affect ONLY detection label, or also which manifest rules apply (relevant to Q1)?

---

## Appendix A — Commands we've already run (read-only, safe to reproduce)

```bash
herdr pane list                              # live roster (pane_id | agent | label)
herdr agent explain <pane> --json            # state + matched_rule + fallback_reason + evaluated_rules
herdr integration status                     # install state per agent
herdr pane read <pane> --source detection    # (to capture detection snapshot — for Q2)
herdr server agent-manifests                 # (active manifest sources per agent — for Q3)
```

## Appendix B — What our code currently does (for reviewers' context)

`HerdMaster/ops/bootstrap.sh` → `agents-flush` action:
1. Loads live roster (`pane list`) → maps each pane to its `agent` type (no hardcoding).
2. Per-type reset command: `codex → /new`, others (`agy`/`kiro`) → `/chat new` (OBSERVED, not docs).
3. Dispatch via `herdr pane run` (text+Enter).
4. Settle via `wait agent-status --status idle --timeout 8000` (fallback `sleep 1`).
5. Verify via `agent explain --json`: CLEAN if rule-matched idle/done; for `agy`/`kiro` ALSO accept
   `default_known_agent_idle_fallback` (no rule exists — best signal). SUSPECT otherwise. + text
   read-back as secondary check.
6. Recovery on SUSPECT: `send-keys ctrl+u` → `esc` → `ctrl+u` → re-`pane run`, then re-verify.

**The single highest-leverage research target is Q1** (manifest override schema for agy/kiro),
because it converts 5 of 8 panes from "guessed idle" to "truly detected state", which in turn makes
notifications (Q9), waits (Q5), and the sidebar all trustworthy.



---
---

# RESOLUTION ADDENDUM — 2026-06-26 (AGY research report + live verification)

Two inputs merged here: (a) the AGY team's vendor-sourced report (verified against herdr.dev
docs + GitHub releases), and (b) our own live commands run on this machine. Where they differ,
**live machine output wins** and is marked `[LIVE]`.

## Corrections to earlier assumptions
- **Version:** `[LIVE] herdr --version → 0.7.1` (NOT 0.7.0). The "0.7.0" in the original brief came
  from bundled *doc copies* in the repo, not the binary. Binary is current on stable. (Preview
  2026-06-25 with extra AGY detection is still ahead, not installed.)
- **`server reload-agent-manifests` / `agent-manifests` / `update-agent-manifests`:** the report
  flagged these as "not in CLI Reference" — true for docs, but `[LIVE] herdr server --help` shows
  **all three exist** in the binary. Confirmed real:
  - `herdr server agent-manifests [--json]` — show manifest status
  - `herdr server update-agent-manifests [--json]` — fetch + reload remote manifests
  - `herdr server reload-agent-manifests` — reload in-memory rule cache after editing a local override
- **Remote-manifest "patch only / new agent needs binary update" (Claim 8):** report marks
  UNVERIFIED from docs. Leave as unverified; not load-bearing for us (agy/kiro are already known).

## Per-question final status (after merge)

| Q | Final status | Resolution |
|---|--------------|-----------|
| Q1 | **RESOLVED via on-disk capture** | Schema NOT in docs, but the real manifests are readable on disk → they ARE the schema (see below). Overrides REPLACE (not merge) — confirmed by docs. |
| Q2 | RESOLVED | `herdr pane read <pane> --source detection` = canonical capture (vendor-confirmed). |
| Q3 | RESOLVED | `agy` and `kiro` are first-class known agents. `[LIVE]` both have remote manifests cached. |
| Q4 | ARCHITECTURALLY SAFE | Override adds detection rule only; does not touch Codex session integration. Needs palette capture. |
| Q5 | RESOLVED | `wait agent-status --status idle` DOES resolve on fallback-idle (status is single value; fallback is explain-only metadata). → our type-aware explain check stays necessary. |
| Q6 | PARTIAL | `integration install codex` upgrade behavior still needs a live test (held for go-ahead). |
| Q7 | RESOLVED | v0.7.0 #569 changed IDs to `w1:p1` style intentionally; now stable handles. SKILL.md `1-1` is outdated. |
| Q8 | RESOLVED | Lowercase tokens canonical (CLI Ref + v0.7.0 #613). Legacy `C-c` aliases exist. |
| Q9 | RESOLVED (WSL caveat) | `[ui.toast] delivery` + `agent_panel_sort=priority` confirmed. WSL delivery still needs a live test (`terminal` vs `system`+notify-send). |
| Q10 | RESOLVED | Codex→`~/.codex/AGENTS.md`; AGY→`.gemini/skills/`; Kiro→`.kiro/`. Verify each per-harness at install. |
| Q11 | FRAMEWORK ONLY | Plugin CLI confirmed; each plugin repo still needs source review. |
| Q12 | RESOLVED | `HERDR_AGENT=<agent>` (added v0.7.1 #679) selects screen manifest; scoped to foreground. Not needed today. |

## Q1 SCHEMA — captured from real on-disk manifest `[LIVE]`

Manifest dir (remote cache): `~/.local/state/herdr/agent-detection/remote/*.toml`
Local override dir (ours to create): `~/.config/herdr/agent-detection/<agent>.toml`
**Overrides REPLACE the whole agent ruleset** → a local file MUST contain the full existing rules
PLUS additions, or detection regresses.

`[LIVE]` Manifest versions (all `result: current`, nothing to update):
- `agy = 2026.06.24.1` (NEWEST of all agents — upstream AGY improvement already cached)
- `kiro = 2026.06.10.1` (older; less actively maintained upstream)
- `gemini = 2026.06.10.1` (SEPARATE from agy — Herdr treats Gemini CLI ≠ Antigravity)
- `codex = 2026.06.10.3`

`[LIVE]` Real `agy.toml` (the schema template, verbatim structure):
```toml
id = "agy"
version = "2026.06.24.1"
min_engine_version = 1
updated_at = "2026-06-24T00:00:00Z"
aliases = ["antigravity", "antigravity-cli"]

[[rules]]
id = "permission_prompt"
state = "blocked"
priority = 300
region = "whole_recent"
visible_blocker = true
contains = ["requesting permission for:"]
any = [
  { contains = ["do you want to proceed?"] },
  { contains = ["tab amend", "edit command"] },
]

[[rules]]
id = "spinner_working"
state = "working"
priority = 100
region = "whole_recent"
visible_working = true
line_regex = ['^\s*[\u2800-\u28FF]+\s+\p{Alphabetic}+\w*ing\b']

[[rules]]
id = "background_tasks_working"
state = "working"
priority = 90
region = "bottom_non_empty_lines(5)"
visible_working = true
line_regex = ['(?i)·\s*[1-9][0-9]*\s+task']
```

### Schema facts derived from the real file
- **Top-level keys:** `id`, `version`, `min_engine_version`, `updated_at`, `aliases` (list).
- **Each rule = `[[rules]]`** with: `id`, `state` (`idle|working|blocked|done|unknown`),
  `priority` (int; higher wins — bands seen: 1100/1050/1000/900/600/300/100/90),
  `region`, optional `visible_blocker`/`visible_working` (bool, sets the explain visible_* flag),
  and matchers.
- **Matchers:** `contains` (list of substrings), `line_regex` (list of regex, matched per-line),
  `regex` (whole-region regex, seen in codex), and `any = [ {sub-matcher}, ... ]` (OR group).
- **`region` values observed:** `whole_recent`, `bottom_non_empty_lines(N)`, `osc_title`,
  `after_last_prompt_marker`.

### ROOT CAUSE of AGY fallback-idle (now proven)
`agy.toml` defines rules ONLY for `blocked` + `working`. There is **NO `idle` rule**. So when an
AGY pane sits at a ready prompt (not spinning, no permission prompt), nothing matches →
`default_known_agent_idle_fallback`. This is by design upstream, not a bug.
**Fix (#3):** local `~/.config/herdr/agent-detection/agy.toml` = copy of the 3 rules above + a new
low-priority `idle` rule matching AGY's ready-prompt shape (capture via `--source detection`).
Same approach for `kiro.toml` (read its real file first).

## Updated execution order (post-research)
1. (DONE) #2 robust verification in `agents-flush` (type-aware explain + wait + recovery).
2. (DONE) Version check → already 0.7.1; remote manifests current → no upgrade/refresh needed.
3. **#3 manifest overrides** — now the clear top priority, and de-risked:
   a. Capture ready-prompt detection shape per agent: `pane read <pane> --source detection`.
   b. Write local `agy.toml` = full existing ruleset + new `idle` rule (REPLACE semantics).
   c. Write local `kiro.toml` likewise (read real `kiro.toml` first).
   d. `herdr server reload-agent-manifests` → re-verify with `agent explain --json`
      (expect `matched_rule` instead of `fallback_reason`).
   e. Optionally a higher-priority codex palette→blocked rule (Q4), full codex ruleset + addition.
4. #1 config — notifications + `agent_panel_sort=priority` (WSL delivery needs live test).
5. (with go-ahead) `integration install codex` upgrade test (Q6).
6. SKILL.md per-harness install (Q10), per-location confirmation.

## Still genuinely open (need live test, not docs)
- Q6: does `integration install codex` upgrade in place / what files? (held for go-ahead)
- Q9: which toast `delivery` actually fires under WSL2 + this terminal.
- Q5: exact `wait` exit codes (SKILL.md says 1=timeout, 0=match; verify live).
- Q4: the actual Codex palette detection-region signature (capture when a pane is in that state).



---
---

# IMPLEMENTATION ADDENDUM — 2026-06-26 (#3 manifest overrides DONE + verified)

This section records the actual implementation of the manifest overrides (research item #3),
which answers Q1/Q2/Q4 with working, live-verified artifacts rather than docs alone.

## Outcome (headline)
**All 8 fleet panes now report `idle` via a MATCHED RULE — zero `default_known_agent_idle_fallback`
anywhere.** Before: 5/8 (agy+kiro) were fallback-idle; codex idle was fragile (OSC-title only).

| Pane | Agent | Before | After |
|------|-------|--------|-------|
| w8:pJ, w8:pY | agy | idle\|default_known_agent_idle_fallback | idle\|**ready_prompt_idle** |
| w8:p12, w8:p14, w8:pG | kiro | idle\|default_known_agent_idle_fallback | idle\|**ready_prompt_idle** |
| w8:pQ, w8:pR, w8:pS | codex | idle\|osc_title_idle (fragile) | idle\|**live_idle** |

## Q1 — FULL SCHEMA (now fully confirmed from real files + live install)
TOML manifest at `~/.config/herdr/agent-detection/<agent>.toml`. **Local override REPLACES the
entire agent ruleset** (verified live: `local_override_shadowing_remote: true`, `source_kind:
"local override"`). A local file MUST contain the full existing ruleset + additions.

Top-level keys: `id` (str), `version` (str, **MUST be dotted-numeric** — see schema gotcha below),
`min_engine_version` (int; codex=2, agy/kiro=1), `updated_at` (RFC3339 str), `aliases` (list).

Each `[[rules]]`:
- `id` (str), `state` (`idle|working|blocked|unknown`), `priority` (int, **higher wins**),
  `region` (str), `visible_idle`/`visible_working`/`visible_blocker` (bool), `skip_state_update` (bool).
- Matchers: `contains` (list substr), `regex` (whole-region), `line_regex` (per-line),
  `any = [ {sub} ]` (OR), `all = [ {sub} ]` (AND), `not = [ {sub} ]` (negation). Sub-matchers nest.
- `region` values seen: `osc_title`, `whole_recent`, `after_last_prompt_marker`,
  `bottom_non_empty_lines(N)`.
- Priority bands observed: codex uses 1100/1050/1000/900/600/100; agy/kiro use 300/290/100/90;
  our idle additions use 50 (deliberately lowest).

### ⚠️ SCHEMA GOTCHA (not catchable by python tomllib — Herdr-specific)
`version` must be **dotted numeric** (e.g. `2026.06.24.99`). A suffix like `2026.06.24.1-local.1`
is REJECTED at load with: `version "..." must be dotted numeric`, the override is IGNORED (with a
`warning` in the reload output), and the remote/bundled manifest stays active (fail-safe). We use a
high last-segment (`.99`) to mark a local fork while staying numeric. **Always validate by checking
the reload output for `source_kind: "local override"` and no `warning`, not just tomllib.**

## Q2 — Idle signatures captured live (`pane read --source detection`)
- **agy** (no `osc_title`; regions = whole_recent + bottom_non_empty_lines(5)): ready prompt always
  shows footer `? for shortcuts`. Rule: `contains ["? for shortcuts"]`.
- **kiro** (regions = whole_recent only): empty-input placeholder `ask a question or describe a task`.
  Rule: `contains ["ask a question or describe a task"]`.
- **codex**: persistent footer `gpt-<ver> <effort> · /<cwd>`. Rule: `line_regex ['gpt-[0-9.]+\s+\w+\s+·\s+/']`.

## Q4 — Codex idle fragility (scope correction) + /chat-new proof
- The original Q4 ask was "palette→blocked". We could NOT capture a live palette-stuck state (all
  panes idle), so that specific rule is DEFERRED.
- The HIGHER-value codex fix found live: `osc_title_idle` keys ONLY on the OSC title, which we
  observed EMPTY both at startup (w8:pQ) AND in-session (w8:pR) → fallback-idle. Added `live_idle`
  (whole_recent footer, priority 50, with blocker `not`-guards) → fixed.
- **Hard proof for the reset-command choice:** w8:pR's detection buffer showed
  `Unrecognized command '/chat'. Type "/" for a list of supported commands.` ×3 — confirming codex
  rejects `/chat new` and requires `/new`. Validates `bootstrap.sh reset_cmd_for_type`.

## Artifacts
- **Staging masters (version-controlled in repo):**
  `HerdMaster/ops/herdr-overrides/staging/{agy,kiro,codex}.toml`
- **Installed (live, user config):** `~/.config/herdr/agent-detection/{agy,kiro,codex}.toml`
- **Rollback:** `rm ~/.config/herdr/agent-detection/<agent>.toml && herdr server reload-agent-manifests`
  (remote/bundled manifest resumes immediately).
- **Re-apply after a fresh machine / config reset:** copy staging files to the install dir + reload.

## Residual / future
- Codex palette→blocked rule: capture a live stuck-palette `--source detection` snapshot, then add a
  high-priority blocked rule keyed on its signature (full codex ruleset + addition).
- Idle-marker robustness: rules were verified against live IDLE buffers only. We could not observe a
  WORKING/BLOCKED screen this session, so the `not`-guards + low priority are a safety net by design,
  not yet empirically exercised against a live working screen. Re-verify when an agent is mid-task.
- Upstream churn: `agy` remote manifest is actively updated (2026.06.24.1; a 2026-06-25 preview adds
  more AGY detection). Our local override SHADOWS remote — periodically diff our staged base against
  the latest remote and re-merge so we don't miss upstream improvements.



---
---

# LIVE TEST REPORT — 2026-06-27 (end-to-end, real data)

Five live tests against the running fleet (codex w8:pQ/pR/pS, agy w8:pJ/pY, kiro w8:p12/p14/pG).
Real prompts and real reset commands were sent; `agent explain` is read-only.

## T1 — Real WORKING-state transition (validates the override priority design)  ✅ PASS
- Sent a real prompt to kiro w8:pG ("17 times 23?"). Captured `idle → working (kiro_working_marker)
  → idle (ready_prompt_idle)`. Answer `391` appeared in the buffer (genuine execution).
- **Proves empirically** (was only theoretical at design time): the existing working rule (prio 100)
  outranks our new `ready_prompt_idle` (prio 50); the idle rule does NOT false-fire during work.
- Caveat: kiro answers fast, so working windows are short (~1–5s) but reliably detected.

## T2 — `wait agent-status` semantics + exit codes  ✅ codes / ⚠️ reliability finding
- **Exit codes confirmed (resolves the SKILL.md-only claim): 0 = match, 1 = timeout.**
  - wait idle on freshly-idle pane → exit 0 ~0.1s.
  - wait blocked on idle pane (3s timeout) → exit 1 at ~3.1s.
  - wait working concurrent with a real dispatch → exit 0 ~0.4s (catches working reliably).
- **CRITICAL: `wait agent-status --status idle` is UNRELIABLE for our screen-manifest agents.**
  Repeated waits on a settled idle pane timed out; a wait spanning a *proven* working→idle
  transition (confirmed by concurrent `agent explain` polling) ALSO timed out (28s). It appears to
  fire only when the status is already idle at the instant of the call / a fresh edge — not on the
  settling transition. Internal cause not over-theorized; operational takeaway is what matters.
- `agent explain` polling, by contrast, tracks idle/working accurately and instantly.

## T3 — `bootstrap.sh agents-flush` live (found + fixed TWO real bugs)  ✅ PASS after fixes
- **Bug 1 (from T2):** `wait_pane_settle()` used `wait agent-status --status idle` → would burn the
  full 8s timeout per pane on fast resets. **Fixed** → poll-`agent explain` loop (returns 0 in 0.03s
  on an idle pane).
- **Bug 2 (only visible in a live run):** the verify loop gated on `explain rc=0 AND
  pane_reset_landed` (text read-back). After a reset the command echo + agent ack (e.g. AGY "new
  chat") legitimately remain in the buffer, so the text check returned false → a CLEAN pane was
  falsely flagged "suspeito" and sent to recovery. **Fixed** → `agent explain` is the sole authority;
  text read-back demoted to informational logging; added explicit `rc=2 → BLOCKED` branch.
- **Live result:** real reset commands to all 8 panes; every pane `limpo` via explain, zero
  false-suspect, zero unnecessary recovery. codex used `/new`, agy/kiro `/chat new`. Post-flush all
  8 idle + rule-matched. (codex matched `osc_title_idle` again post-`/new` because the title
  repopulated → prio-100 osc rule wins over our prio-50 `live_idle`; the layered design works.)

## T4 — codex integration v5→v6 upgrade  ✅ PASS
- BEFORE `codex: outdated (v5 < v6)` → ran `herdr integration install codex` (idempotent in-place
  upgrade; touched `~/.codex/{herdr-agent-state.sh, hooks.json, config.toml}`) → AFTER
  `codex: current (v6)`. Resolves Q6.
- Gives codex **session-identity restore** (`codex resume <id>` after a Herdr *server* restart), NOT
  state authority — codex state still comes from screen detection. Rollback: `herdr integration
  uninstall codex`.

## T5 — WSL notification config  ✅ VERIFIED (already configured; nothing to clobber)
- WSL probe: `notify-send` NOT installed; `DISPLAY=:0`, `WAYLAND_DISPLAY=wayland-0` (WSLg).
  → `delivery="system"` would fail (no binary); **`delivery="terminal"` is the correct WSL choice.**
- `~/.config/herdr/config.toml` already had `[ui] agent_panel_sort="priority"`, `agent_panel_scope=
  "all"`, `[ui.toast] delivery="terminal"`. `herdr server reload-config` → `status: applied`, zero
  diagnostics; live server confirmed.
- **Awareness (not changed):** `[experimental] pane_history=true` persists pane contents (possible
  secrets) to `~/.config/herdr/session-history.json` (~900KB exists). It lives in user home,
  OUTSIDE the project repo → no git exposure. Operator's deliberate setting; left as-is.

## Net code changes (this test session)
- `HerdMaster/ops/bootstrap.sh`: `wait_pane_settle()` rewritten (poll-explain), `agents-flush`
  verification loop rewritten (explain = sole authority, read-back informational, BLOCKED branch).
  `bash -n` clean; exercised live against all 8 panes.

## Answers folded back into the open-questions
- Q5: `wait` exit codes = 0/1 confirmed; idle-wait is unreliable for screen-manifest agents (use
  explain-polling to detect settle). Q6: codex upgrade is idempotent in-place. Q9: `terminal`
  delivery is the verified WSL path; `system`/notify-send unavailable here.



---
---

# SKILL.md INSTALL — 2026-06-27 (per-harness, Q10 resolved)

## Source of truth
Fetched live from `https://raw.githubusercontent.com/ogulcancelik/herdr/master/SKILL.md` (8988 bytes;
matches the copy reviewed earlier). Canonical repo copy saved at
`HerdMaster/ops/herdr-overrides/SKILL.md` (9605 bytes — adds two local-fleet annotation notes:
the `w8:pX` id format, and the `wait agent-status idle` unreliability finding from the live tests).

## Per-harness mechanism — DETERMINED BY INSPECTION (not assumed)
All three harnesses use the SAME convention, confirmed by the existing `openspec-*` skills already
installed on disk: **`~/.<harness>/skills/<skill-name>/SKILL.md`** (one folder per skill).
- This is cleaner than the herdr agent-guide's generic hint (which suggested codex consumes
  instructions from `~/.codex/AGENTS.md`). The ACTUAL on-disk convention here is a skills dir for
  all three, matching the SKILL.md frontmatter (`name: herdr`). We followed the real convention.

## Installed (verified)
| Harness | Path | Bytes | Alongside |
|---------|------|-------|-----------|
| codex | `~/.codex/skills/herdr/SKILL.md` | 9605 | openspec-* skills |
| agy (antigravity) | `~/.gemini/skills/herdr/SKILL.md` | 9605 | openspec-* skills |
| kiro | `~/.kiro/skills/herdr/SKILL.md` | 9605 | openspec-* skills |
- No existing `herdr` skill dir in any harness → zero clobber.
- Frontmatter intact (`name: herdr`); `HERDR_ENV=1` guardrail present in all three.

## Guardrail note (Q10)
The skill self-gates on `HERDR_ENV=1` ("if not set, say you are not inside a herdr pane and stop").
This is a PROMPT-LEVEL guardrail, NOT a hard enforcement — confirmed: `HERDR_ENV` is just an env
var Herdr injects into managed panes. HerdMaster remains the real authority for dispatch/reset; the
skill only enables read-side coordination (`pane read`, `wait agent-status` on siblings, `pane list`).

## Re-apply / rollback
- Re-apply (fresh machine): `cp HerdMaster/ops/herdr-overrides/SKILL.md ~/.<h>/skills/herdr/SKILL.md`
  for h in codex/gemini/kiro.
- Rollback: `rm -rf ~/.<h>/skills/herdr`.
