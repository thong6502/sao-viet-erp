# MEMORY index (always-on, bounded)

<!--
This file is the ALWAYS-ON memory index. It is loaded into every session, so it is
HARD-CAPPED at read time: ~200 lines / ~25KB. The cap fires SILENTLY with no error —
entries past the cap simply disappear and the most recent memories are the ones lost.

RULES (see memory/README.md for the full protocol — do NOT inline that here):
  1. ONE LINE PER ENTRY. A terse hook only. No multi-sentence summaries. A multi-line
     entry can hit the byte cap while still under the line cap and silently truncate.
  2. Format:  - [TYPE] <one-line hook> (YYYY-MM-DD) -> topics/<slug>.md
     TYPE is one of: PREFERENCE | DECISION | FACT  (see taxonomy below / in README).
  3. NEVER record derivable content (architecture, code patterns, file layout, version
     history, dependency lists). That stales and drifts. Detail goes in the topic file,
     never in this index.
  4. Two-step save: write topics/<slug>.md FIRST, then append the one-line hook here.
  5. If this index approaches ~150 lines, prune stale/superseded hooks before adding more.
-->

## What may be saved here (taxonomy)

SAVE only **non-derivable** facts, of exactly three TYPEs:

- **PREFERENCE** — tooling / style / workflow choices the user or team stated.
- **DECISION** — a deliberate choice + the reason, with a date.
- **FACT** — a non-derivable external constraint (credential locations, account/env
  quirks, conventions that are NOT visible anywhere in the repo).

NEVER save (it lives in the repo and will drift / go stale):

- Architecture, module layout, file structure.
- Code patterns, function signatures, API shapes.
- Version history, changelog, dependency versions.
- Anything you could re-derive by reading the code or running a command.

## Entry format

`- [TYPE] <terse one-line hook> (YYYY-MM-DD) -> topics/<slug>.md`

Keep each entry to a single line. If you need more than a line, the detail belongs in a
linked `topics/<slug>.md` file and the index just points to it. Detail in the index is a
guaranteed failure mode — it silently blows the byte cap.

## Preferences

<!-- Durable user/team preferences. Example shape (delete once real entries exist): -->
- [PREFERENCE] <PLACEHOLDER: e.g. Use uv, not pip - user preference> (<YYYY-MM-DD>) -> topics/<slug>.md

## Decisions

<!-- Non-derivable choices and their rationale lives in the topic file. -->
- [DECISION] <PLACEHOLDER: e.g. Chose pytest over unittest for the suite> (<YYYY-MM-DD>) -> topics/<slug>.md

## Facts

<!-- Non-derivable facts: external constraints, account/env quirks, who-owns-what. -->
- [FACT] <PLACEHOLDER: e.g. CI runs on Python 3.12 only> (<YYYY-MM-DD>) -> topics/<slug>.md
