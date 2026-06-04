# Tool & Permission Safety

How this harness keeps tool use fail-closed. Read this before adding a new tool,
loosening a permission, or editing a hook.

## The layered gate (priority order)

Claude Code evaluates permission from highest to lowest priority. Counterintuitively,
**local beats project beats user beats org** — a `CLAUDE.local.md` or local settings
file in the repo root silently wins over project rules. Always test a new rule with
the FULL stack present (user `~/.claude/CLAUDE.md` + project `AGENTS.md`/`CLAUDE.md`
+ any `CLAUDE.local.md`) to confirm it isn't being overridden.

```
org policy  >  user settings  >  project rules  >  local overrides  >  session grants
```

1. **`.claude/settings.json` `permissions`** — the primary, declarative gate.
   `deny` / `ask` / `allow` lists. This is checked into the repo (project level).
2. **`.claude/hooks/guard_bash.py`** (`PreToolUse` on `Bash`) — a runtime backstop
   that classifies the *specific command* and can `deny` (exit 2) or `ask`.
3. **The model's own judgment** — last and weakest. Never the only gate.

## Non-negotiable invariants

1. **Default permission is `allow`.** A tool with no rule is auto-approved. Any
   sensitive or destructive tool MUST be explicitly listed in `ask` or `deny` in
   `settings.json`. Never assume a tool is gated by default.
2. **Classify per call, not per tool.** The Bash tool is safe for `cat` and
   catastrophic for `rm -rf`. Safety is a property of the arguments, not the tool.
   Never statically tag a tool as "read-only" or "safe".
3. **Cover BOTH shells.** This harness runs on Windows (PowerShell) and Unix/CI
   (bash). Every destructive heuristic must match the POSIX form AND the Windows
   equivalent: `rm -rf` ⇿ `Remove-Item -Recurse -Force`; `cat` ⇿ `Get-Content`;
   `/dev/null` ⇿ `$null`; `$VAR` ⇿ `$env:VAR`. Use absolute paths in hooks.
4. **Re-evaluate permission fresh every call.** Permission evaluation has side
   effects (it tracks denials and can transform modes). Never cache or reuse a
   prior decision.
5. **Hook trust is all-or-nothing.** In an untrusted workspace, Claude Code skips
   ALL hooks — `guard_bash.py` will not run. In that mode, `settings.json`
   `deny`/`ask` rules are your only protection, so keep them complete on their own.
   Do not rely on the hook to cover gaps the static rules leave open.

## Adding or enabling a tool — required checklist

```
## Tool Safety Review — <tool name>

### Classification
- [ ] Read-only?         true / false / depends on args
- [ ] Concurrent-safe?   true / false / depends on args
- [ ] Documented the unsafe argument patterns (both shells)

### Permission
- [ ] Default overridden to `ask` or `deny` in settings.json if sensitive
- [ ] Destructive forms added to guard_bash.py DENY/ASK (POSIX + Windows)
- [ ] Protected paths covered (.git/**, system dirs, secrets)

### Testing (with the FULL instruction-file stack present)
- [ ] Safe inputs auto-approve
- [ ] Unsafe inputs ask/deny
- [ ] New patterns added to .claude/hooks/test_guard_bash.py and pytest passes
```

## What this is NOT

The guard is a heuristic backstop, not a sandbox. It reduces footguns; it does not
contain a hostile process. Keep the declarative `settings.json` rules authoritative
and treat the hook as defense-in-depth.

<PLACEHOLDER>: list this project's genuinely destructive operations here (deploys,
DB migrations, infra commands) and make sure each appears in settings.json and/or
guard_bash.py.
