# AGENTS.md

Project harness for reliable agent-assisted development in a Python codebase.

> This is the canonical agent instruction file. `CLAUDE.md` points here — do not duplicate guidance into it.

## Startup Workflow

Before writing code:

1. **Confirm working directory** with `pwd`
2. **Read this file** completely
3. **Read project docs if present** (`docs/ARCHITECTURE.md`, `docs/PRODUCT.md`, README, or equivalent)
4. **Run verification** to confirm the environment is healthy — `./init.sh` on Unix/macOS/CI, or `./init.ps1` on Windows/PowerShell
5. **Read `feature_list.json`** to see current feature state
6. **Review recent commits** with `git log --oneline -5`

If baseline verification is failing, repair that first before adding new scope.

## Working Rules

- **One feature at a time**: Pick exactly one unfinished feature from `feature_list.json`
- **Verification required**: Don't claim done without running verification commands
- **Update artifacts**: Before ending session, update `progress.md` and `feature_list.json`
- **Stay in scope**: Don't modify files unrelated to the current feature
- **Leave clean state**: Next session must be able to run `./init.sh` immediately

## Required Artifacts

- `feature_list.json` — Feature state tracker (source of truth)
- `progress.md` — Session continuity log
- `init.sh` / `init.ps1` — Standard startup and verification path (bash / PowerShell)
- `session-handoff.md` — Optional, for larger sessions
- `.claude/settings.json` — Tool-permission gate (allow/ask/deny) and lifecycle/safety hooks
- `.claude/hooks/` — Cross-platform hooks: `dispatch.py` (trust gate + lifecycle), `guard_bash.py` (Bash safety classifier)
- `.claude/skills/` — Reusable workflow skills (auto-discovered), e.g. `run-feature/`
- `docs/` — Extension protocols: `CONTEXT.md`, `CONTEXT-MAP.md`, `TOOL_SAFETY.md`, `LIFECYCLE.md`, `COORDINATION.md`
- `memory/` — Auto-memory: `MEMORY.md` (bounded always-on index) + `topics/<slug>.md`
- `coordination/` — Multi-agent task ledger, results, and fork-guard hook
- `tools/` — Maintenance utilities, e.g. `memory_sweep.py` (`.sh` / `.ps1` wrappers)

## Definition of Done

A feature is done only when ALL of the following are true:

- [ ] Target behavior is implemented
- [ ] Required verification actually ran (tests / lint / type-check)
- [ ] Evidence recorded in `feature_list.json` or `progress.md`
- [ ] Repository remains restartable from standard startup path

## End of Session

Before ending a session:

1. Update `progress.md` with current state
2. Update `feature_list.json` with new feature status
3. Record any unresolved risks or blockers
4. Commit with descriptive message once work is in safe state
5. Leave repo clean enough for next session to run `./init.sh` immediately

## Verification Commands

```bash
# Full verification (recommended)
./init.sh        # Unix / macOS / CI (bash)
./init.ps1       # Windows (PowerShell)
```

Required checks (run by both scripts):

- `python -m pytest` — test suite
- `python -m compileall .` — every module imports/compiles

> Replace or extend these with the project's real checks (e.g. `ruff check .`, `mypy .`).
> Keep `init.sh` and `init.ps1` in sync so Unix/CI and Windows verify identically.

## Escalation

If you encounter:

- **Architecture decisions**: Consult project architecture docs if present, otherwise ask user
- **Unclear requirements**: Check product/requirements docs if present, otherwise ask user
- **Repeated test failures**: Update progress, flag for human review
- **Scope ambiguity**: Re-read `feature_list.json` for definition of done

---

## Extension Modules

The sections below document the harness extension modules. Each is a thin routing
pointer; the authoritative protocol lives in the linked `docs/*.md` file or skill.
Within each module section, sub-topics use `###` headings.

### Context Engineering

Context is a budget, not a dump. Operate it with four operations: **SELECT** (load just-in-time), **WRITE** (persist non-derivable facts), **COMPRESS** (compact long sessions), **ISOLATE** (keep delegated work out of the parent).

Routing:

- **Before loading heavy docs**, consult `docs/CONTEXT-MAP.md` (Tier 1 metadata) — it says what to load and when. Read Tier 3 resources only when their trigger fires.
- **For how to budget/compact/delegate**, read `docs/CONTEXT.md` when a session gets long, when delegating, or when deciding what to load or save.
- **To persist a durable fact**, add ONE terse line to `memory/MEMORY.md` and push detail into `memory/topics/<slug>.md`.

Hard invariants:

- Memory index entries are **one-line hooks only**. The index has silent ~200-line / ~25 KB caps; over them, newest entries vanish with no error. Detail goes in topic files.
- **Never store derivable content** (architecture, code patterns, file structure, versions) in memory — it lives in the repo and drifts. Memory = preferences / decisions / non-derivable facts only.
- **Single-level delegation**: sub-agents start fresh and must not spawn their own sub-agents.
- **Memoized context builders invalidate manually** — clear the matching cache at every mutation, or the model reads stale data all session.
- Run `tools/memory_sweep.py` (or `.sh` / `.ps1`) periodically to delete orphan topic files and warn before the index hits its silent caps.

### Memory Persistence

Auto-memory lives in `memory/` (separate from this instruction file). At session start, after reading this file, also read `memory/MEMORY.md` — it is the bounded, always-on index of non-derivable preferences/decisions/facts. Open a `memory/topics/<slug>.md` file only when its hook is relevant. The full protocol is in `memory/README.md` (do not duplicate it here).

Invariants:

- **Index = one-line hooks only.** Every `memory/MEMORY.md` entry is a single terse line: `- [TYPE] <hook> (YYYY-MM-DD) -> topics/<slug>.md`. The index is hard-capped (~200 lines / ~25KB) and truncates SILENTLY — multi-line entries can hit the byte cap and disappear. Push all detail into the topic file.
- **Store only non-derivable facts.** Types are PREFERENCE | DECISION | FACT. Never save anything derivable from the codebase (architecture, code patterns, file layout, versions, dependencies) — it drifts.
- **Two-step save, in order:** write `memory/topics/<slug>.md` first, then append the one-line index hook. Never write the index pointer before the topic file exists.
- **Local instructions win over memory.** Priority is org < user < project < local; a memory hook never overrides a project/`CLAUDE.local.md` rule. Verify new rules with the full instruction stack present.
- **Housekeeping:** run `python memory/sweep_orphans.py` (add `--apply` to delete) to clear topic files orphaned by an interrupted save. Runs on both Windows and Unix. (`tools/memory_sweep.py` is an equivalent sweeper that also checks the index caps.)

### Tool & Permission Safety

Tool use is fail-closed. Full rules in `docs/TOOL_SAFETY.md`; routing skill at `.claude/skills/tool-safety/`.

- **Default permission is `allow`** — sensitive/destructive tools are gated only by explicit `deny`/`ask` entries in `.claude/settings.json` plus the `PreToolUse` hook `.claude/hooks/guard_bash.py`. Never assume a tool is gated by default.
- **Classify per call, not per tool**: the same Bash tool is safe for `cat`/`Get-Content` and catastrophic for `rm -rf`/`Remove-Item -Recurse -Force`. Judge the actual arguments, and cover BOTH POSIX and PowerShell forms.
- **Untrusted workspace = no hooks run** (all-or-nothing). The static `settings.json` `deny`/`ask` rules must stand on their own.
- **Test new rules with the full instruction-file stack** (local > project > user > org); a `CLAUDE.local.md` can silently override them.
- Before adding/enabling a tool or loosening a permission, complete the Tool Safety Review checklist in `docs/TOOL_SAFETY.md`. New guard patterns require a matching case in `.claude/hooks/test_guard_bash.py` (run via `./init.sh` / `./init.ps1`).

### Lifecycle & Bootstrap

Initialization is staged and trust-gated. Full protocol: `docs/LIFECYCLE.md`. Hook entrypoint: `.claude/hooks/dispatch.py` (+ `.claude/hooks/README.md`).

- **Bootstrap order**: minimal context -> read-only tools + baseline verify (`./init.sh` / `./init.ps1`) -> **trust boundary** -> sensitive subsystems (hooks, write/shell, secrets) -> cleanup wiring. Never load secrets or run hooks before the trust boundary is crossed. If a stage fails, halt and stay read-only.
- **Trust is all-or-nothing, gated once**: if the workspace is untrusted, EVERY hook is skipped (including `guard_bash.py`). Trust via `HARNESS_TRUST=1` or a `.claude/.trust` marker. There is no per-hook trust — keep the gate singular in `dispatch.py:workspace_is_trusted()`.
- **One cross-platform entrypoint**: all lifecycle hooks run as `python .claude/hooks/dispatch.py <event>` (identical on Windows + Unix). Do not inline shell into `settings.json`.
- **Disjoint hook scopes** (do not duplicate): Lifecycle owns `SessionStart`/`Stop`; Tool-Safety owns `PreToolUse:Bash` (`docs/TOOL_SAFETY.md`); Coordination owns `PreToolUse:Task` fork-guard + two-phase result eviction (`docs/COORDINATION.md`). Lifecycle delegates command classification to `guard_bash.py` and the result sweep to Coordination — it never reimplements them.
- **Hooks fail open**: a throwing hook must never wedge the agent.

### Multi-Agent Coordination

When a task needs delegation, parallelism, or specialized roles, follow the coordination protocol before spawning anything.

- **Full protocol:** `docs/COORDINATION.md`. **Prompt scaffold:** `docs/coordination/worker-prompt.template.md`. **Shared ledger:** `coordination/tasks.md`. **Skill:** `dispatch-worker`.
- **Default to the Coordinator pattern** (workers start with ZERO inherited context). The coordinator must SYNTHESIZE prior results into a precise, self-contained spec — never delegate understanding ("based on your findings" is broken; the worker cannot see that history).
- **Single-level fork invariant:** a child agent MUST NOT spawn sub-agents. The `PreToolUse` fork-guard hook blocks the `Task` tool when `HARNESS_AGENT_DEPTH >= 1`. Set/increment that env var when launching a child so the guard can protect against grandchildren.
- **Flat swarm roster:** teammates coordinate through `coordination/tasks.md`, not by prompting each other; they cannot spawn other teammates.
- **Filter each worker's tools** to its role minimum (researcher: read/search, no write; implementer: +edit/tests; reviewer: read/search/tests).
- **Two-phase result handoff:** worker writes `coordination/results/<task-id>.md` and sets `status: done`; coordinator reads it, then sets `consumed: yes`. Never delete a `done`-but-not-`consumed` result.

### Reusable Workflows as Skills

Recurring, multi-session workflows for this repo live as project skills under `.claude/skills/<name>/SKILL.md` (Claude Code auto-discovers them). Prefer invoking the matching skill over re-deriving a procedure inline.

- **`run-feature`** — the canonical pick-one-feature -> implement -> verify -> handoff lifecycle (the skill form of the Working Rules / Definition of Done above). Use it to start or resume a feature from `feature_list.json`.
- Authoring guide and rules: `.claude/skills/README.md`.

Invariants when adding or editing a skill:

- `SKILL.md` `name` MUST equal its directory name; front-load trigger keywords at the very start of `description` (the listing caps each entry ~150 chars).
- Skills hold reusable workflows, decisions, templates — never architecture/code-structure facts (those drift), secrets, or unapproved destructive commands.
- Every relative link in a `SKILL.md` must resolve. Validate before committing: `bash .claude/skills/scripts/validate-skills.sh` (Unix/CI) or `pwsh -File .claude/skills/scripts/validate-skills.ps1` (Windows). Keep the two validators in sync, like `init.sh`/`init.ps1`.
