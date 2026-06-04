# `.claude/hooks/` — hooks for this harness

Cross-platform hook system. Two modules share this directory:

- **Lifecycle & bootstrap** (this README's focus): `dispatch.py` — the single
  trust gate + `SessionStart`/`Stop` lifecycle moments. See `docs/LIFECYCLE.md`.
- **Tool-Safety**: `guard_bash.py` + `test_guard_bash.py` — the `PreToolUse`
  command classifier. See `docs/TOOL_SAFETY.md`. (Lifecycle delegates to it; it
  is the single source of truth for command safety — do not duplicate it.)

## Files

| File | Module | Role |
|------|--------|------|
| `dispatch.py` | Lifecycle | Single trust gate; `session-start` / `pre-tool-use` (proxy) / `stop`. |
| `guard_bash.py` | Tool-Safety | Per-call Bash command classifier (deny/ask). |
| `test_guard_bash.py` | Tool-Safety | pytest for the classifier. |
| `dispatch.log` | Lifecycle | Append-only audit trail (created on first run; safe to delete; git-ignore it). |

## Why one Python file instead of `.sh` + `.ps1`

`settings.json` hook `command` strings run through the OS shell; a bash one-liner
breaks under PowerShell and vice-versa. `python` is already required by this
harness, so `python .claude/hooks/dispatch.py <event>` is identical on Windows and
Unix. Keep hook logic in Python here — do NOT inline shell into `settings.json`.

## Trust gate (all-or-nothing)

`dispatch.py` checks `workspace_is_trusted()` ONCE, before running anything.
Untrusted workspace => every hook routed through it is skipped (exit 0, never
blocks). Trust this workspace via `HARNESS_TRUST=1` or a `.claude/.trust` marker.

## Wiring note (don't double-run PreToolUse)

`guard_bash.py` is already wired as the `PreToolUse` Bash guard. The shipped
`settings.json` keeps that and adds only `SessionStart` + `Stop` -> `dispatch.py`.
If you instead want one explicit gate, point `PreToolUse` at
`dispatch.py pre-tool-use` (it delegates to `guard_bash.classify()`) — but never
wire BOTH for the same matcher. See "Wiring options" in `docs/LIFECYCLE.md`.

## Test locally

```bash
# Lifecycle: untrusted skips all hooks (exit 0); trusted + destructive blocks (exit 2)
echo '{"tool_name":"Bash","tool_input":{"command":"rm -rf /tmp/x"}}' \
  | python .claude/hooks/dispatch.py pre-tool-use            # exit 0 (untrusted)
echo '{"tool_name":"Bash","tool_input":{"command":"rm -rf /tmp/x"}}' \
  | HARNESS_TRUST=1 python .claude/hooks/dispatch.py pre-tool-use   # exit 2

# Tool-Safety classifier (runs in the harness pytest suite)
python -m pytest .claude/hooks/test_guard_bash.py
```

```powershell
# PowerShell — trusted destructive PowerShell command is blocked
$env:HARNESS_TRUST = '1'
'{"tool_name":"PowerShell","tool_input":{"command":"Remove-Item -Recurse -Force C:/tmp"}}' `
  | python .claude/hooks/dispatch.py pre-tool-use            # exit 2
```

## Invariants (do not break)

- Trust is evaluated ONCE, at dispatch. No per-hook trust.
- A buggy/throwing hook must never wedge the agent — handlers fail open (allow).
- Command safety lives in `guard_bash.py` only; `dispatch.py` delegates, never
  re-classifies.
- Hook event scopes are disjoint: Lifecycle owns SessionStart/Stop; Tool-Safety
  owns PreToolUse:Bash; Coordination owns PreToolUse:Task (fork-guard).
