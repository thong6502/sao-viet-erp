#!/bin/bash
# Validate project skills under .claude/skills/.
# Keep in sync with validate-skills.ps1 (same checks, same exit codes).
#
# Checks, per .claude/skills/*/SKILL.md:
#   - file has a YAML frontmatter block (--- ... ---)
#   - frontmatter has a non-empty `name:` and `description:`
#   - `name` matches the skill's directory name
#   - every relative markdown/link target referenced in SKILL.md exists
# Exits non-zero on the first failure so it can gate CI.
set -euo pipefail

# Resolve repo root: this script lives at .claude/skills/scripts/.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

fail() { echo "SKILL VALIDATION FAILED: $1" >&2; exit 1; }

found_any=0
for skill_md in "$SKILLS_DIR"/*/SKILL.md; do
  [ -e "$skill_md" ] || continue
  found_any=1
  skill_dir="$(dirname "$skill_md")"
  dir_name="$(basename "$skill_dir")"
  echo "=== validating $dir_name ==="

  # Frontmatter must start at line 1 and be delimited by --- ... ---
  first_line="$(head -n 1 "$skill_md")"
  [ "$first_line" = "---" ] || fail "$dir_name/SKILL.md: missing frontmatter (first line must be ---)"

  # Extract frontmatter block (between the first two --- lines).
  fm="$(awk 'NR==1{next} /^---[[:space:]]*$/{exit} {print}' "$skill_md")"

  name_val="$(printf '%s\n' "$fm" | sed -n 's/^name:[[:space:]]*//p' | head -n 1 | tr -d '\r')"
  [ -n "$name_val" ] || fail "$dir_name/SKILL.md: frontmatter missing non-empty 'name:'"
  [ "$name_val" = "$dir_name" ] || fail "$dir_name/SKILL.md: name '$name_val' != directory '$dir_name'"

  # description may be inline or a YAML block scalar (>- / |) — accept either form.
  if ! printf '%s\n' "$fm" | grep -Eq '^description:[[:space:]]*([^[:space:]].*|[>|].*)?$'; then
    fail "$dir_name/SKILL.md: frontmatter missing 'description:'"
  fi

  # Every relative link target in SKILL.md must resolve to a real file.
  # Matches markdown links: ](path) where path is not http(s):// or #anchor.
  links="$(grep -oE '\]\(([^)]+)\)' "$skill_md" | sed -E 's/^\]\(//; s/\)$//' || true)"
  while IFS= read -r link; do
    [ -n "$link" ] || continue
    case "$link" in
      http://*|https://*|mailto:*|\#*) continue ;;
    esac
    target="${link%%#*}"   # strip any #anchor
    [ -n "$target" ] || continue
    [ -e "$skill_dir/$target" ] || fail "$dir_name/SKILL.md: broken link -> $target"
  done <<< "$links"

  echo "ok: $dir_name"
done

[ "$found_any" -eq 1 ] || fail "no SKILL.md files found under $SKILLS_DIR"
echo "=== all skills valid ==="
