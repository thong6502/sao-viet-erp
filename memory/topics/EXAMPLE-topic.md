<!--
Topic file template. COPY this to memory/topics/<slug>.md for each real memory, then add
ONE one-line hook to memory/MEMORY.md pointing here (topic file first, index second).
This EXAMPLE file is referenced by no index hook on purpose, so the orphan sweep will
NOT delete it (its name starts with EXAMPLE and the sweep skips EXAMPLE-*.md and .gitkeep).
Delete it once you understand the shape, or keep it as a reference.
-->
# <PLACEHOLDER: human-readable title>

- **Type:** PREFERENCE | DECISION | FACT  (pick one)
- **Recorded:** <YYYY-MM-DD>
- **Index hook:** <the exact one-line hook used in MEMORY.md>

## Detail

<PLACEHOLDER: the full content — rationale, context, scope. This is the on-demand layer,
so length is fine here. Do NOT store anything derivable from the codebase (architecture,
code patterns, file layout, versions) — only the non-derivable preference/decision/fact.>

## Supersedes / related

<PLACEHOLDER: link to any topic file this replaces, or "none". When you supersede a
memory, prune the old one-line hook from MEMORY.md so the index stays bounded.>
