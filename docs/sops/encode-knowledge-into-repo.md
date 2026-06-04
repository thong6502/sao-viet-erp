# SOP: Encode Unseen Knowledge Into The Repo

`memory/` = non-derivable one-liners (a PREFERENCE / DECISION / FACT hook plus a
short topic file). **THIS SOP = durable knowledge -> repo docs.** When the thing
to capture is real system knowledge (how it works, what the product should do, a
security/reliability rule, plan context, an external reference), it belongs in a
repo doc — not in the memory index. The memory index has silent ~200-line /
~25 KB caps and is the wrong home for documents; use it only for the terse
non-derivable hook that points at where the real knowledge now lives.

Use this SOP when important context still lives in chat threads, tickets, shared
docs, or people's heads, and a fresh session keeps re-discovering it.

## Goal

Make agent-invisible knowledge discoverable in the codebase so a fresh session
can act on it without relying on prior conversation.

## Trigger Signals

- The agent keeps asking how the system works.
- Humans say "we decided this in chat" or "follow what X said last week."
- Reviews reference product or security rules that are not written in-repo.
- New sessions repeat discovery work that should already be settled.

## Execution SOP

1. List the invisible knowledge sources: shared docs, chats, tacit team rules,
   verbal decisions.
2. For each source, classify it: is this architecture, product behavior, design
   rationale, reliability expectation, execution state, or reference material?
3. Encode it into the matching repo artifact (this repo's layout):

   | Knowledge type | Target in this repo |
   |----------------|---------------------|
   | Architecture / boundaries | `docs/ARCHITECTURE.md` |
   | Reliability / runtime signals | `docs/RELIABILITY.md` |
   | Product behavior | `docs/product-specs/` `<PLACEHOLDER: create on first use>` |
   | Design rationale (why, not just what) | `docs/design-docs/` `<PLACEHOLDER: create on first use>` |
   | Repeated external references | `docs/references/` `<PLACEHOLDER: create on first use>` |
   | Execution state (where work stopped, what's next) | `progress.md` + `feature_list.json` |

   For durable multi-session plans (not per-session state), use `docs/PLANS.md` /
   `docs/exec-plans/`; keep `progress.md` + `feature_list.json` for the live
   per-session state.

4. Replace vague statements with operationally useful wording.
5. Remove or deprecate stale copies so the repo keeps one discoverable truth.
6. If the fact is a non-derivable preference/decision (not a document), instead
   add ONE hook to `memory/MEMORY.md` -> `memory/topics/<slug>.md`. Do not store
   derivable content (architecture, code patterns, versions) in memory — it
   drifts; that content belongs in the docs above.

## Good Encoding Rules

- Write for discoverability, not for literary completeness.
- Prefer short documents with clear filenames.
- Link related artifacts together (use forward-slash relative links).
- Store durable rules, not meeting transcripts.
- Update the repo in the same session that the decision is made.

## Definition Of Done

- A fresh agent can discover the relevant rule without asking a human.
- The same fact is not scattered across multiple contradictory files.
- The new artifact lives close to the code or workflow it governs.
- Any rule worth enforcing mechanically has a check wired into the single
  verification source of truth (`./init.sh` / `./init.ps1`), not just prose.
