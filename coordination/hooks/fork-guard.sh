#!/usr/bin/env bash
# fork-guard (Unix/CI) — enforces the single-level sub-agent invariant.
#
# Wired as a Claude Code PreToolUse hook (see .claude/settings.json). Claude Code
# sends a JSON event on stdin; we only need to act when a CHILD agent
# (HARNESS_AGENT_DEPTH >= 1) tries to spawn another sub-agent.
#
# Trust gate is all-or-nothing and handled by Claude Code at dispatch: if the
# workspace is untrusted NO hooks run at all, so this guard does not try to
# re-evaluate trust per call.
#
# Exit 0 = allow. Exit 2 = block (stderr is shown to the model).
set -euo pipefail

depth="${HARNESS_AGENT_DEPTH:-0}"

# Read the event payload (best-effort; we do not require jq).
payload="$(cat 2>/dev/null || true)"

# Identify a sub-agent spawn. The Task tool is the spawn surface in Claude Code.
# Match on tool_name in the JSON payload without depending on jq.
is_spawn=0
case "$payload" in
  *'"tool_name"'*'"Task"'*) is_spawn=1 ;;
esac

if [ "$is_spawn" -eq 1 ] && [ "${depth}" -ge 1 ]; then
  echo "fork-guard: BLOCKED. A child agent (HARNESS_AGENT_DEPTH=${depth}) may not spawn sub-agents." >&2
  echo "Single-level invariant: only the root coordinator (depth 0) may fork/dispatch. See docs/COORDINATION.md." >&2
  exit 2
fi

exit 0
