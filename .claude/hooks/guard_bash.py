#!/usr/bin/env python3
"""PreToolUse guard for the Bash tool.

WHY A PYTHON HOOK (not a .sh/.ps1 pair):
  Claude Code runs hook `command` strings through the OS shell, so a raw shell
  one-liner would have to be written twice (bash + PowerShell) and would drift.
  Python is already required by this harness (see init.sh / init.ps1), so a
  single `python` invocation is byte-identical on Windows and Unix. settings.json
  invokes this as:  python "$CLAUDE_PROJECT_DIR/.claude/hooks/guard_bash.py"

WHAT IT DOES:
  Classifies the SPECIFIC command for THIS call (gotcha: classify per-call, not
  per-tool — `cat` is safe, `rm -rf` is not, on the SAME Bash tool) and covers
  BOTH POSIX and PowerShell destructive forms (gotcha: Unix prefix matching
  misses `Remove-Item -Recurse -Force`, etc.).

CONTRACT (Claude Code PreToolUse hook):
  - stdin  : JSON with tool_name and tool_input.command
  - exit 0 : allow (no decision) — DEFAULT permission is 'allow', so this hook is
             the explicit gate for destructive shell calls (gotcha: sensitive
             ops are NOT gated unless you override the default).
  - exit 2 : block; stderr text is shown to the model and the call is denied.
  - JSON on stdout with {"hookSpecificOutput":{"permissionDecision":"ask"}} asks
    the user. We use exit 2 (deny) for clearly-destructive forms and "ask" for
    merely-risky ones.

This is a SCAFFOLD: tune the pattern lists for your project's real risk surface.
Patterns are matched on the raw command string; this is a heuristic backstop, NOT
a sandbox. Keep settings.json `deny`/`ask` rules as the primary gate.
"""
import json
import re
import sys

# --- DENY: clearly destructive on either shell. Block outright (exit 2). -------
# Each entry covers the POSIX form AND its Windows/PowerShell equivalent.
DENY_PATTERNS = [
    # recursive force delete
    r"\brm\s+(-[a-z]*r[a-z]*f|-[a-z]*f[a-z]*r|-rf|-fr)\b",          # rm -rf
    r"\bRemove-Item\b.*-Recurse\b.*-Force\b",                        # PS recurse+force
    r"\bRemove-Item\b.*-Force\b.*-Recurse\b",
    r"\b(rd|rmdir)\s+/s\b",                                          # cmd rmdir /s
    r"\bdel\s+/[sq]\b",                                              # cmd del /s /q
    # disk / filesystem wipe
    r"\bmkfs(\.\w+)?\b",
    r"\bdd\s+.*\bof=/dev/",
    r"\bFormat-Volume\b", r"\bformat\s+[A-Za-z]:",
    r"\bClear-Disk\b",
    # fork bomb / reboot / shutdown
    r":\(\)\s*\{.*\}\s*;:",
    r"\b(shutdown|reboot|halt)\b", r"\bStop-Computer\b", r"\bRestart-Computer\b",
    # piping remote scripts straight into a shell
    r"\bcurl\b.*\|\s*(sudo\s+)?(ba)?sh\b",
    r"\bwget\b.*\|\s*(sudo\s+)?(ba)?sh\b",
    r"\bInvoke-(WebRequest|RestMethod)\b.*\|\s*(iex|Invoke-Expression)\b",
    r"\biwr\b.*\|\s*iex\b",
    # destructive SQL
    r"\bDROP\s+(TABLE|DATABASE|SCHEMA)\b",
    r"\bTRUNCATE\s+TABLE\b",
    r"\bDELETE\s+FROM\b(?!.*\bWHERE\b)",                             # unqualified DELETE
    # protected dirs (history-rewriting / VCS internals / system trees)
    r"\bgit\b.*\bpush\b.*--force\b(?!-with-lease)",                  # plain --force push
    r"\brm\b.*\B\.git\b", r"\bRemove-Item\b.*\.git\b",
    r"(^|\s)(/etc|/usr|/bin|/sbin)(/|\s|$)",
    r"\bchmod\s+-R\s+777\b",
]

# --- ASK: risky but legitimate. Surface to the user (permissionDecision ask). --
ASK_PATTERNS = [
    r"\b(sudo|doas)\b", r"\bStart-Process\b.*-Verb\s+RunAs\b",
    r"\bpip\s+install\b", r"\bnpm\s+(install|i|ci)\b", r"\bpoetry\s+(add|install)\b",
    r"\bgit\s+reset\s+--hard\b", r"\bgit\s+clean\s+-[a-z]*f", r"\bgit\s+checkout\s+--\s",
    r"\bRemove-Item\b", r"\brm\b",                                   # any other delete
    r"\bcurl\b", r"\bwget\b", r"\bInvoke-WebRequest\b", r"\bInvoke-RestMethod\b",
    r"\b(mv|move|Move-Item)\b", r"\bsed\s+-i\b",                     # in-place mutation
    # <PLACEHOLDER>: add project-specific risky commands (deploy, db migrate, etc.)
]


def classify(command: str):
    """Return ('deny'|'ask'|'allow', matched_pattern_or_None) for ONE command."""
    for pat in DENY_PATTERNS:
        if re.search(pat, command, re.IGNORECASE):
            return "deny", pat
    for pat in ASK_PATTERNS:
        if re.search(pat, command, re.IGNORECASE):
            return "ask", pat
    return "allow", None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        # Fail closed on unparseable input rather than silently allowing.
        print("guard_bash: could not parse hook input; blocking.", file=sys.stderr)
        return 2

    if payload.get("tool_name") != "Bash":
        return 0  # not our tool; defer to the permission system

    command = (payload.get("tool_input") or {}).get("command", "") or ""
    decision, pattern = classify(command)

    if decision == "deny":
        print(
            "BLOCKED by tool-safety guard: this command matches a destructive "
            f"pattern ({pattern}). If this is intentional, run it manually or ask "
            "the user to approve it explicitly.",
            file=sys.stderr,
        )
        return 2

    if decision == "ask":
        # Defer to the user without hard-blocking.
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": (
                    f"tool-safety guard: risky command pattern ({pattern}); "
                    "confirm before running."
                ),
            }
        }))
        return 0

    return 0  # allow


if __name__ == "__main__":
    sys.exit(main())
