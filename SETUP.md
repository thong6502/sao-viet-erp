# Harness Setup Checklist

This harness ships with all five core subsystems **plus** six extension modules
(memory, tool-safety, lifecycle, multi-agent, context-engineering, reusable-skills).
Everything is scaffolded and **verifies green out of the box** (`./init.sh` / `./init.ps1`
pass: 3 guard tests + compile check). Before relying on the extensions in a real project,
work through the items below.

See `AGENTS.md` for how each module behaves; the per-module protocol lives in the linked
`docs/*.md` files and the `.claude/skills/` skills.

---

## Already done (no action needed)

- [x] `pytest.ini` added so `python -m pytest` discovers the harness's own hook test under
      `.claude/` (without it, pytest exited 5 and `init.sh` failed under `set -e`).
- [x] `.gitignore` added (`__pycache__/`, `.pytest_cache/`, venvs, `.claude/hooks/dispatch.log`).
- [x] Removed a redundant memory example (`memory/topics/tooling.md`) that the orphan sweep
      flagged out-of-the-box; `memory/topics/EXAMPLE-topic.md` is the single auto-skipped template.
- [x] `PreToolUse:Task` hook normalized to the `$CLAUDE_PROJECT_DIR/...` cwd-independent form.

## 1. Trust wiring (REQUIRED before hooks/guards are effective)

Hook trust is **all-or-nothing**: in an untrusted workspace Claude Code runs **zero** hooks,
disabling `guard_bash.py`, `fork_guard.py`, and `dispatch.py` together.

- [ ] Replace the placeholder in `.claude/hooks/dispatch.py:workspace_is_trusted()` with a real
      trust signal (path allow-list / signed config / recorded consent). It currently honors
      `HARNESS_TRUST=1` or a `.claude/.trust` marker file.
- [ ] In CI, set `HARNESS_TRUST=1` so `SessionStart`/`Stop` hooks actually run.
- [ ] The fork-recursion guard depends on `HARNESS_AGENT_DEPTH` being incremented for each child
      agent launch. Confirm your agent launch wrapper propagates/increments it, or the guard
      can't detect depth.
- [ ] Because untrusted = no hooks, confirm the **static** `permissions.deny`/`ask` lists in
      `.claude/settings.json` are sufficient on their own as a fallback.

## 2. `python` vs `python3`

All hooks and `init.sh`/`init.ps1` invoke `python`. If your environments only expose `python3`:

- [ ] Change the hook commands in `.claude/settings.json` and the `init.*` scripts to `python3`
      (keep them consistent).

## 3. Tool-safety tuning

- [ ] Edit `permissions.deny` secret globs in `.claude/settings.json` to match where THIS project
      keeps secrets/keys (defaults: `.env`, `secrets/**`, `*.pem`, `id_rsa`).
- [ ] Fill `ASK_PATTERNS` in `.claude/hooks/guard_bash.py` with project-specific risky commands
      (deploy, db-migrate, etc.). Add a matching case in `.claude/hooks/test_guard_bash.py` for
      each new pattern.
- [ ] List the project's genuinely destructive operations in `docs/TOOL_SAFETY.md`.

## 4. Fill the `<PLACEHOLDER>` markers

All intentional; replace before real use:

- [ ] `memory/MEMORY.md` — delete the placeholder hook lines (or replace with real entries).
- [ ] `docs/CONTEXT.md`, `docs/CONTEXT-MAP.md` — real context-budget numbers + Tier-3 doc list.
- [ ] `coordination/tasks.md` — clear the example ledger rows.
- [ ] `.claude/skills/run-feature/templates/feature-entry.json` — fill when copying into `feature_list.json`.
- [ ] Base state files (`feature_list.json`, `progress.md`, `session-handoff.md`) — replace the
      `feat-002…005` placeholders and `YYYY-MM-DD` stamps with your real first feature.

## 5. Optional wiring

- [ ] Add `python tools/memory_sweep.py` (report-only; non-destructive) as a step in `init.sh`
      and `init.ps1` so each verification run surfaces orphan topic files and index cap warnings.
      Do **not** add `--apply` to init scripts — that deletes files and is intentionally gated to
      `ask` in `.claude/settings.json`.
- [ ] On Unix/CI, make the shell wrappers executable: `chmod +x tools/memory_sweep.sh
      .claude/skills/scripts/validate-skills.sh`.
- [ ] Wire `.claude/skills/scripts/validate-skills.{sh,ps1}` into CI so a malformed `SKILL.md`
      fails the build.
- [ ] If you want module adoption tracked as work, append features `feat-006+` to
      `feature_list.json` (keep the required fields `id/name/description/dependencies/status/evidence`
      intact; don't add an `owner` field unless every feature gets one — the validator wants a
      uniform shape).

## Known minor redundancies (your call — not bugs)

- Two orphan-sweep implementations exist: `memory/sweep_orphans.py` (memory module) and
  `tools/memory_sweep.py` (context module, also checks index caps). Consolidate to one if you
  prefer a single tool.
- `coordination/hooks/fork-guard.sh` / `.ps1` are reference twins of the wired `fork_guard.py`;
  they are documented-but-unwired. Keep as reference or delete to reduce surface.
