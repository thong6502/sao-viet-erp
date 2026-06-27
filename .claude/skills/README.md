# Project skills — reusable workflows as skills

This directory holds **project-local Claude Code skills**: reusable agent workflows that
apply across many sessions, packaged once instead of re-explained every time. Claude Code
auto-discovers any `.claude/skills/<name>/SKILL.md` in this repo.

Shipped skills (the 3-role GAN loop):

- [`plan/`](plan/SKILL.md) — Planner: converts a spec into `feature_list.json`.
- [`generate/`](generate/SKILL.md) — Generator: builds one feature at a time, then verifies.
- [`browser-validate/`](browser-validate/SKILL.md) — Evaluator: drives the running app and scores it.

Use any of these as the template for new workflow skills.

## What belongs here

- Reusable workflows for THIS repo (release, triage-bug, cut-changelog, etc.).
- Decision procedures, checklists, and copyable templates the agent loads on demand.

## What must NOT go here

- Project architecture / code structure facts — those drift; keep them in the codebase
  and docs, not in a skill.
- Secrets, tokens, private URLs.
- Destructive commands without explicit, documented user approval.

## Skill layout (progressive disclosure)

```
.claude/skills/<name>/
  SKILL.md              # frontmatter + shortest reliable workflow (always loaded)
  references/*.md       # deeper material, loaded only when relevant
  templates/*           # copyable artifacts
```

## SKILL.md frontmatter contract

```yaml
---
name: <kebab-case, matches the directory name>
description: >-
  <front-loaded trigger keywords first>, then a short "Use to ... Not for ..." clause.
license: MIT
---
```

- **Front-load distinctive trigger keywords** at the very start of `description`. Skill
  descriptions are concatenated and capped per entry (~150 chars) in the skill listing;
  anything past the cap is truncated and the skill won't trigger reliably. Lead with the
  keywords, not prose.
- `name` MUST equal the directory name.
- Every file referenced from `SKILL.md` (links into `references/`, `templates/`) MUST
  exist. Verify with the validator below before committing.

## Validate before committing

Run the cross-platform validator from the repo root. It checks that every `SKILL.md` has
valid `name`/`description` frontmatter, that `name` matches its folder, and that every
relative link inside `SKILL.md` resolves to a real file.

```bash
# Unix / macOS / CI
bash .claude/skills/scripts/validate-skills.sh
```

```powershell
# Windows / PowerShell
pwsh -File .claude/skills/scripts/validate-skills.ps1
```

Both exit non-zero on the first problem so they can gate CI. Keep the two scripts in sync
(same checks, same exit codes) exactly like `init.sh` / `init.ps1`.

## Adding a new workflow skill

1. Copy one of the shipped skills above to `.claude/skills/<new-name>/` and rewrite `SKILL.md`.
2. Replace every `<PLACEHOLDER>` and remove sections that don't apply.
3. Trim `references/` / `templates/` to what the new workflow actually needs.
4. Run the validator (above) — fix every reported issue.
5. Add a one-line pointer to the skill from `AGENTS.md` only if it changes the default
   routing; otherwise discovery is automatic.
