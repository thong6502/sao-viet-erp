# Lifecycle & Bootstrap

How this harness initializes, where lifecycle hooks fire, and the single trust
gate that controls them. Authoritative doc for the Lifecycle & bootstrap module.
Artifacts: `.claude/hooks/dispatch.py` (+ `README.md`), wired in
`.claude/settings.json`.

## Scope (stays in its lane)

This module owns: the **trust gate**, **bootstrap staging**, and the
**SessionStart / Stop** lifecycle moments. It does NOT own:

- Command safety classification -> **Tool-Safety module** (`docs/TOOL_SAFETY.md`,
  `.claude/hooks/guard_bash.py`). Lifecycle *delegates* to it; it never
  re-implements classification.
- Sub-agent results / two-phase eviction / fork-guard -> **Coordination module**
  (`docs/COORDINATION.md`). Lifecycle only provides the `Stop` *trigger point*;
  Coordination owns the eviction protocol and ledger (`coordination/`).

## Bootstrap is staged and trust-gated

Initialization is dependency-ordered. **Security-sensitive work must not run
before trust is established.** The single trust gate lives in
`.claude/hooks/dispatch.py:workspace_is_trusted()`.

| Stage | What happens | Trust required |
|-------|--------------|----------------|
| 1. Minimal context | Confirm cwd, read `AGENTS.md`, determine entry mode | No |
| 2. Read-only tools | Read / Glob / Grep; baseline verify (`./init.sh` or `./init.ps1`) | No |
| 3. Trust boundary | `workspace_is_trusted()` evaluated **once** | — |
| 4. Sensitive subsystems | Hooks dispatch, write/shell tools, secrets/telemetry | **Yes** |
| 5. Cleanup wiring | `Stop` hook armed -> triggers Coordination's result sweep | Yes |

If any stage fails, bootstrap halts and the session stays read-only. Do not load
secrets, enable write tools, or run hooks until Stage 3 passes.

## Hook trust is ALL-OR-NOTHING (gated once)

> If the workspace is untrusted, **every** hook is skipped — not just risky ones.
> Trust is evaluated exactly once, at the dispatch point. There is no per-hook
> trust. Untrusted workspace = zero hooks run.

Two layers enforce this:
1. **Claude Code itself** skips ALL configured hooks in an untrusted workspace
   (before they ever start).
2. **`dispatch.py`** re-checks `workspace_is_trusted()` once at the top of every
   invocation, so hooks routed through it inherit the same guarantee and
   bootstrap staging can key off one signal.

Trust this workspace via `HARNESS_TRUST=1` or a `.claude/.trust` marker file.
`<PLACEHOLDER: swap in your real trust signal — path allow-list, signed config, recorded consent.>`

> Consequence: in an untrusted workspace, `guard_bash.py` does NOT run either, so
> the declarative `settings.json` `deny`/`ask` rules are your only protection.
> Keep them complete on their own (see `docs/TOOL_SAFETY.md`).

## Lifecycle event map (Claude Code event -> dispatcher)

All lifecycle hooks route through ONE cross-platform entrypoint so the command
string is identical on Windows and Unix: `python .claude/hooks/dispatch.py <event>`.

| Claude Code event | Dispatcher event | Purpose | Owner |
|-------------------|------------------|---------|-------|
| `SessionStart`    | `session-start`  | Bootstrap marker / surface startup context | Lifecycle |
| `PreToolUse`      | `pre-tool-use`   | Trust-gated **proxy** -> `guard_bash.classify()` | Tool-Safety (logic), Lifecycle (gate) |
| `Stop`            | `stop`           | Trigger Coordination result sweep | Coordination (sweep), Lifecycle (trigger) |

Exit codes: `0` allow, `2` block (stderr shown to agent), other nonzero =
non-blocking error.

## Wiring options for PreToolUse (avoid double-running)

`guard_bash.py` is already a PreToolUse hook owned by Tool-Safety. Pick ONE so a
Bash call isn't classified twice:

- **Option A (recommended, simplest):** wire PreToolUse on `Bash` directly to
  `guard_bash.py` and let Claude Code's own workspace-trust gate handle the
  all-or-nothing rule. `dispatch.py` then handles only `SessionStart` + `Stop`.
- **Option B (single explicit gate):** wire PreToolUse to
  `dispatch.py pre-tool-use`, which re-checks trust once and delegates to
  `guard_bash.classify()`. Use this if you want the harness-level trust gate to
  visibly own every hook. Do NOT wire both for the same matcher.

The shipped `settings.json` fragment uses **Option A** for Bash safety
(unchanged Tool-Safety wiring) and adds only `SessionStart` + `Stop`.

## Background work units (long-running, non-sub-agent)

For long-running work spawned in a session (extraction, benchmark, indexing) the
pattern is: typed prefixed IDs (`extraction-001`), a strict state machine
(`running -> completed | failed | killed`), and disk-backed output. The
**eviction protocol is two-phase and is defined once in `docs/COORDINATION.md`**
(eager disk cleanup at terminal state; lazy in-memory cleanup only after the
parent is notified). Reuse it — do not define a second ledger here.

## Bootstrap verification checklist

- [ ] Stage 1: cwd confirmed, `AGENTS.md` read, entry mode known
- [ ] Stage 2: `./init.sh` (or `./init.ps1`) passes; read-only tools only
- [ ] Stage 3: trust signal present (`HARNESS_TRUST=1` or `.claude/.trust`)
- [ ] Stage 4: dispatcher skips ALL hooks when untrusted (exit 0)
- [ ] Stage 4: dispatcher blocks a known-destructive sample when trusted (exit 2)
- [ ] Stage 5: `Stop` hook wired; Coordination sweep reachable
