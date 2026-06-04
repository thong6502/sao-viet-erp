#!/usr/bin/env python3
"""Lifecycle dispatcher: the single trust gate + bootstrap/session hooks.

SCOPE (Lifecycle & bootstrap module ONLY):
    This file owns the ONE trust gate, the bootstrap/session lifecycle moments
    (SessionStart, Stop), and an optional trust-gating PROXY for PreToolUse.
    It does NOT classify commands and does NOT decide tool safety — that is the
    Tool-Safety module's job (`.claude/hooks/guard_bash.py`, see docs/TOOL_SAFETY.md)
    and the Coordination module's fork-guard (see docs/COORDINATION.md). We
    delegate to those; we never duplicate them.

WHY ONE PYTHON ENTRYPOINT (not .sh/.ps1 pairs):
    settings.json hook `command` strings run through the OS shell, so a raw bash
    one-liner breaks under PowerShell and vice-versa. `python` is already a hard
    dependency of this harness (init.sh / init.ps1), so
    `python .claude/hooks/dispatch.py <event>` is byte-identical on Windows and
    Unix. Keep hook logic in Python here, not inline shell in settings.json.

CLAUDE CODE HOOK CONTRACT:
    - Hook input arrives as JSON on STDIN.
    - exit 0  => allow / proceed.
    - exit 2  => BLOCK; stderr is shown to the agent as the reason.
    - other nonzero => non-blocking error (logged; action proceeds).

THE TRUST GATE IS ALL-OR-NOTHING, EVALUATED ONCE:
    If the workspace is untrusted, EVERY hook routed through here is skipped —
    not just risky ones. Trust is checked exactly once per invocation, at the
    top of main(). There is no per-hook trust. Untrusted workspace => zero
    hooks run, by design.

    NOTE: Claude Code itself also gates hooks on its own workspace-trust state
    (when the workspace is untrusted, it skips ALL configured hooks before they
    ever start). This dispatcher's gate is the harness-level equivalent so the
    same all-or-nothing guarantee holds for hooks invoked through it, and so
    bootstrap staging (below) can key off one trust signal.
"""
from __future__ import annotations

import datetime as _dt
import importlib.util
import json
import os
import sys
from pathlib import Path

# --- Resolve paths from this file (absolute, never cwd-relative). ------------
HOOKS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = HOOKS_DIR.parent.parent
LOG_PATH = HOOKS_DIR / "dispatch.log"

EXIT_ALLOW = 0
EXIT_BLOCK = 2

# Optional PreToolUse guards to run behind the trust gate, in order. Each is a
# (module_filename, callable_name) where the callable has the same signature as
# this script's main: it reads the SAME event dict and returns an exit code.
# We reuse the sibling modules' `classify()` so there is ONE source of truth for
# command safety. <PLACEHOLDER: add more guards as other modules ship them.>
_PRETOOL_GUARDS = [
    ("guard_bash.py", "classify"),  # Tool-Safety module
]


def _log(line: str) -> None:
    """Append one audit line. Never raise from logging."""
    try:
        stamp = _dt.datetime.now().isoformat(timespec="seconds")
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(f"{stamp}\t{line}\n")
    except Exception:
        pass


def _read_event() -> dict:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _load_sibling(filename: str):
    """Import a sibling hook module by filename, regardless of cwd."""
    path = HOOKS_DIR / filename
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def workspace_is_trusted() -> bool:
    """THE single trust signal for the whole harness hook system.

    Trusted when EITHER:
      - env var HARNESS_TRUST=1 (CI / explicit opt-in), OR
      - a `.claude/.trust` marker file exists in the project root.

    <PLACEHOLDER: replace with your real trust signal — workspace path
    allow-list, signed config, recorded user consent, etc.> An untrusted
    workspace MUST yield zero hooks. Do not add per-hook trust checks anywhere;
    keep the gate here, singular.
    """
    if os.environ.get("HARNESS_TRUST") == "1":
        return True
    if (PROJECT_ROOT / ".claude" / ".trust").exists():
        return True
    return False


# ---------------------------------------------------------------------------
# Lifecycle handlers. Return (exit_code, message). Keep fast; fail OPEN — a
# buggy hook must never wedge the agent.
# ---------------------------------------------------------------------------

def on_session_start(event: dict) -> tuple[int, str]:
    """Bootstrap marker (Stage 4 in docs/LIFECYCLE.md).

    We are past the trust boundary by the time this runs, so this is where
    trust-sensitive startup context may be surfaced. <PLACEHOLDER: emit
    project-specific startup context — current feature from feature_list.json,
    open risks from session-handoff.md, etc.>
    """
    _log("session-start")
    return EXIT_ALLOW, ""


def on_pre_tool_use(event: dict) -> tuple[int, str]:
    """Trust-gated PROXY to the real safety guards (no classification here).

    By the time we reach this function the trust gate has already passed, so
    delegating to guard_bash.classify() here gives every PreToolUse guard the
    same all-or-nothing trust behavior, behind ONE gate. Optional: wire
    PreToolUse to guard_bash.py directly instead and let Claude Code's own
    workspace trust gate it — see docs/LIFECYCLE.md "Wiring options".
    """
    tool = event.get("tool_name", "")
    command = ""
    if tool in ("Bash", "PowerShell"):
        command = str((event.get("tool_input") or {}).get("command", ""))

    if not command:
        return EXIT_ALLOW, ""

    for filename, fn_name in _PRETOOL_GUARDS:
        mod = _load_sibling(filename)
        if mod is None or not hasattr(mod, fn_name):
            continue
        try:
            decision, pattern = getattr(mod, fn_name)(command)
        except Exception as exc:
            _log(f"pre-tool guard {filename} errored: {exc!r}")
            continue
        if decision == "deny":
            _log(f"pre-tool BLOCK via {filename} tool={tool} pat={pattern}")
            return EXIT_BLOCK, (
                f"Blocked by {filename} (matched {pattern}). "
                "If intended, run it manually or relax the guard."
            )
    _log(f"pre-tool allow tool={tool}")
    return EXIT_ALLOW, ""


def on_stop(event: dict) -> tuple[int, str]:
    """Stop / session-end lifecycle moment.

    Good place to trigger the Coordination module's two-phase result sweep
    (docs/COORDINATION.md) so finished work isn't lost or leaked. Lifecycle owns
    the trigger point; Coordination owns the eviction protocol.
    <PLACEHOLDER: invoke your sweep here.>
    """
    _log("stop")
    return EXIT_ALLOW, ""


HANDLERS = {
    "session-start": on_session_start,
    "pre-tool-use": on_pre_tool_use,
    "stop": on_stop,
}


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in HANDLERS:
        sys.stderr.write("usage: dispatch.py <" + "|".join(HANDLERS) + ">\n")
        return EXIT_ALLOW  # unknown event must never block the agent

    event_name = argv[1]

    # --- THE SINGLE TRUST GATE (all-or-nothing). ----------------------------
    if not workspace_is_trusted():
        _log(f"SKIP (untrusted) event={event_name}")
        return EXIT_ALLOW  # untrusted => skip ALL hooks, never block

    event = _read_event()
    try:
        code, message = HANDLERS[event_name](event)
    except Exception as exc:  # a buggy hook must not wedge the agent
        _log(f"ERROR event={event_name} exc={exc!r}")
        return EXIT_ALLOW

    if message:
        sys.stderr.write(message + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
