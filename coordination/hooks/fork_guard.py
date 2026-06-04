#!/usr/bin/env python3
"""fork-guard (portable) — enforces the single-level sub-agent invariant.

This is the canonical hook used by .claude/settings.json because `python` is
guaranteed on this stack and the SAME command line works on Windows and Unix
(no shell-selection fragility). The sibling fork-guard.sh / fork-guard.ps1 are
documented shell equivalents.

Wiring: Claude Code PreToolUse hook. Claude Code sends a JSON event on stdin.
We block only when a CHILD agent (HARNESS_AGENT_DEPTH >= 1) tries to spawn
another sub-agent (the `Task` tool).

Why a single dispatch-point guard: hook trust is all-or-nothing — an untrusted
workspace runs ZERO hooks — so we never try to re-evaluate trust per call. And
"is this a forbidden recursive spawn?" is classified PER CALL from the live
payload + env, never statically tagged on the tool.

Exit 0 = allow. Exit 2 = block (stderr shown to the model).
"""
import json
import os
import sys

# The spawn/sub-agent surface in Claude Code. Extend if a project adds others.
SPAWN_TOOLS = {"Task"}


def main() -> int:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        event = json.loads(raw) if raw.strip() else {}
    except (ValueError, TypeError):
        event = {}

    tool_name = event.get("tool_name", "")

    try:
        depth = int(os.environ.get("HARNESS_AGENT_DEPTH", "0") or "0")
    except ValueError:
        depth = 0

    if tool_name in SPAWN_TOOLS and depth >= 1:
        sys.stderr.write(
            "fork-guard: BLOCKED. A child agent "
            f"(HARNESS_AGENT_DEPTH={depth}) may not spawn sub-agents.\n"
            "Single-level invariant: only the root coordinator (depth 0) may "
            "fork/dispatch. See docs/COORDINATION.md.\n"
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
