#!/usr/bin/env pwsh
# fork-guard (Windows/PowerShell) — enforces the single-level sub-agent invariant.
#
# Wired as a Claude Code PreToolUse hook (see .claude/settings.json). Claude Code
# sends a JSON event on stdin; we only act when a CHILD agent
# (HARNESS_AGENT_DEPTH >= 1) tries to spawn another sub-agent.
#
# Trust gate is all-or-nothing and handled by Claude Code at dispatch: an
# untrusted workspace runs ZERO hooks, so this guard does not re-check trust.
#
# Exit 0 = allow. Exit 2 = block (stderr is shown to the model).
$ErrorActionPreference = 'Stop'

$depth = 0
if ($env:HARNESS_AGENT_DEPTH) { [int]::TryParse($env:HARNESS_AGENT_DEPTH, [ref]$depth) | Out-Null }

# Read the event payload (best-effort).
$payload = ''
try { $payload = [Console]::In.ReadToEnd() } catch { $payload = '' }

# Identify a sub-agent spawn. The Task tool is the spawn surface in Claude Code.
$isSpawn = $false
if ($payload -match '"tool_name"\s*:\s*"Task"') { $isSpawn = $true }

if ($isSpawn -and $depth -ge 1) {
  [Console]::Error.WriteLine("fork-guard: BLOCKED. A child agent (HARNESS_AGENT_DEPTH=$depth) may not spawn sub-agents.")
  [Console]::Error.WriteLine("Single-level invariant: only the root coordinator (depth 0) may fork/dispatch. See docs/COORDINATION.md.")
  exit 2
}

exit 0
