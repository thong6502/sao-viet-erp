---
name: tool-safety
description: Tool permission gating and destructive-command safety. Use before adding a tool, editing .claude/settings.json permissions, changing the Bash guard hook, or when a command looks destructive (rm -rf, Remove-Item -Recurse, DROP TABLE, force push).
---

# Tool & Permission Safety

Authoritative detail lives in `docs/TOOL_SAFETY.md`. Read it before acting. This
skill is the routing entry point.

## When this applies
- Adding or enabling a new tool for the agent.
- Editing `.claude/settings.json` `permissions` (allow / ask / deny).
- Editing `.claude/hooks/guard_bash.py` or its tests.
- About to run a command that could be destructive.

## The 60-second rules
1. **Default is `allow`.** Sensitive tools are unguarded unless explicitly listed
   in `settings.json` `ask`/`deny`. Add the rule; don't assume a gate exists.
2. **Classify per call, not per tool.** `cat` is safe, `rm -rf` is not — same tool.
   Judge the actual arguments.
3. **Both shells.** Match POSIX and Windows equivalents:
   `rm -rf` ⇿ `Remove-Item -Recurse -Force`, `cat` ⇿ `Get-Content`.
4. **Untrusted workspace = zero hooks.** If hooks are off, `settings.json` rules
   are the only gate. Keep them complete on their own.
5. **Test with the full instruction stack.** Local > project > user > org — a
   `CLAUDE.local.md` can silently override a rule you just added.

## How to change the gate
- **New permission:** add to `.claude/settings.json` (`allow`/`ask`/`deny`). Prefer
  the narrowest rule that works. Treat `deny` as the safe default for destructive ops.
- **New destructive pattern:** add the regex (POSIX + Windows form) to
  `DENY_PATTERNS` or `ASK_PATTERNS` in `.claude/hooks/guard_bash.py`, add a case to
  `.claude/hooks/test_guard_bash.py`, then run `python -m pytest` (via `./init.sh`
  or `./init.ps1`) to confirm.

## Do NOT
- Cache a permission decision and reuse it — re-evaluate every call.
- Statically tag a tool "read-only" or "concurrent-safe".
- Rely on the hook alone when the workspace may be untrusted.
