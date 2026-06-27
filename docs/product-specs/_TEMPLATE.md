<!-- Copy to docs/product-specs/<spec>.md per spec; delete this notice when filled -->
<!-- This is the SPEC shape the human Planner fills. The plan skill reads it. -->

# <PLACEHOLDER: Spec Name>

## Goal

<PLACEHOLDER: one sentence describing what this spec should deliver for the user.>

## Screens

- <PLACEHOLDER: screen / view the user sees>
- <PLACEHOLDER: screen / view the user sees>

## Features

- <PLACEHOLDER: discrete user-facing capability>
- <PLACEHOLDER: discrete user-facing capability>

## Logic / flow

> The main happy-path sequence, numbered. The 🔨 Generator builds to this order;
> the 🔍 Evaluator walks it. Keep it behavioural, not code-level.

- <PLACEHOLDER: step 1 user action -> step 2 system response -> step 3 ...>

## System statuses

> App-wide conditions that affect these screens. Delete rows that don't apply —
> each one kept must show the user something (never a blank/frozen screen).

- <PLACEHOLDER: offline / network lost>
- <PLACEHOLDER: session expired / not authenticated>
- <PLACEHOLDER: backend error / overloaded>

## Edge cases

> Abnormal inputs or situations and the expected behaviour.

- <PLACEHOLDER: empty / very long / unexpected-character input>
- <PLACEHOLDER: duplicate action (double-submit), race condition>

## Acceptance criteria

> State observable outcomes; for UI work write them as Playwright MCP browser
> assertions (snapshot/text/state via `../sops/browser-validation-loop.md`),
> confirmed on top of green `./init.sh` / `./init.ps1`.
> Every Logic/flow step, System status, Edge case, and Failure state above must
> map to at least one assertion here — otherwise the 🔍 Evaluator can't check it.

- <PLACEHOLDER: observable outcome>
- <PLACEHOLDER: observable outcome>
- <PLACEHOLDER: observable outcome>

## Out-of-scope

- <PLACEHOLDER: explicitly NOT built this spec>

## Failure states

- <PLACEHOLDER: recoverable error and the user feedback shown>
- <PLACEHOLDER: blocked state and fallback>
