#!/usr/bin/env python3
"""Sweep orphaned memory topic files.

The two-step memory save (write topics/<slug>.md, THEN append a one-line hook to
MEMORY.md) can crash between steps, leaving a topic file that no index hook points to.
Orphans do not corrupt the index but accumulate on disk. This script finds topic files
that are not referenced by memory/MEMORY.md.

Cross-platform: pure stdlib, runs identically on Windows (PowerShell) and Unix (bash/CI).

Usage:
    python memory/sweep_orphans.py            # dry-run (default, safe): list orphans
    python memory/sweep_orphans.py --apply    # delete the orphaned topic files

Exits non-zero in dry-run if orphans are found (useful as a CI/verification check);
exits zero after a successful --apply.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Resolve paths relative to THIS file so cwd does not matter (works from any shell/dir).
MEMORY_DIR = Path(__file__).resolve().parent
INDEX = MEMORY_DIR / "MEMORY.md"
TOPICS_DIR = MEMORY_DIR / "topics"

# Files in topics/ that are scaffolding, never orphans.
SKIP = {".gitkeep"}


def referenced_slugs(index_text: str) -> set[str]:
    """Return the set of topics/<name>.md filenames referenced by the index."""
    # Matches '-> topics/<name>.md' regardless of surrounding text.
    return {m.group(1) for m in re.finditer(r"topics/([^\s)]+\.md)", index_text)}


def find_orphans() -> list[Path]:
    if not TOPICS_DIR.is_dir():
        return []
    index_text = INDEX.read_text(encoding="utf-8") if INDEX.exists() else ""
    referenced = referenced_slugs(index_text)
    orphans = []
    for f in sorted(TOPICS_DIR.glob("*.md")):
        if f.name in SKIP or f.name.startswith("EXAMPLE"):
            continue
        if f.name not in referenced:
            orphans.append(f)
    return orphans


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sweep orphaned memory topic files.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete orphaned topic files. Without this flag, only lists them (dry-run).",
    )
    args = parser.parse_args(argv)

    orphans = find_orphans()
    if not orphans:
        print("No orphaned topic files.")
        return 0

    print(f"Found {len(orphans)} orphaned topic file(s):")
    for f in orphans:
        print(f"  {f.relative_to(MEMORY_DIR)}")

    if args.apply:
        for f in orphans:
            f.unlink()
        print(f"Deleted {len(orphans)} orphaned topic file(s).")
        return 0

    print("\nDry-run only. Re-run with --apply to delete.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
