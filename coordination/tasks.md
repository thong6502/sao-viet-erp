# Coordination Task Ledger

The shared task list for swarm/coordinator workstreams. Agents coordinate
INDIRECTLY through this file, not by prompting each other. One task per row.

Lifecycle: `open` -> claimed (`owner` set) -> `done` (result file written) ->
`consumed: yes` (coordinator read it; only now may the result file be deleted).
See the two-phase handoff in `docs/COORDINATION.md`.

| task-id | description | role | owner | status | result file | consumed |
|---|---|---|---|---|---|---|
| <PLACEHOLDER: feat-002-a> | <PLACEHOLDER: research auth flows> | researcher | <unassigned> | open | coordination/results/<task-id>.md | no |

## Rules

- Claim a task by setting `owner` to your role/id BEFORE starting work.
- A worker may only run tasks whose `role` matches it.
- On finish: write `coordination/results/<task-id>.md`, set `status: done`.
- Coordinator sets `consumed: yes` after reading the result. Do not delete a
  `done` result that is not yet `consumed`.
- Teammates do not add tasks that spawn other teammates (flat roster).
