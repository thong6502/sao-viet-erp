#!/usr/bin/env python3
"""Memory orphan sweep + index cap check (cross-platform: Windows + Unix).

Why this exists (Context Engineering / WRITE operation):
  * Saving a memory is two steps: write topics/<slug>.md, then add a line to MEMORY.md.
    A crash between the two steps leaves an ORPHAN topic file that is never referenced.
    Orphans do not corrupt the index but accumulate and fill disk. This sweep deletes
    topic files that no index line references.
  * The MEMORY.md index has SILENT hard caps (~200 lines / ~25 KB) enforced at read time.
    Over the cap, the newest entries vanish with NO error. This script also WARNS when the
    index is approaching those caps so the failure is visible before it bites.

Pure standard library. Same behavior on PowerShell and bash. Use absolute paths via --root
or run from the repo root (it resolves paths relative to this file's parent's parent).

Usage:
  python tools/memory_sweep.py            # report only (safe; no deletion)
  python tools/memory_sweep.py --apply    # actually delete orphan topic files
  python tools/memory_sweep.py --root /abs/path/to/repo

Exit codes: 0 = clean, 1 = orphans found (report mode) or cap exceeded.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Hard caps that mirror the silent read-time caps on the memory index.
MAX_INDEX_LINES = 200
MAX_INDEX_BYTES = 25 * 1024  # 25 KB
WARN_RATIO = 0.8  # warn at 80% of either cap

# Topic files that are scaffolding and must never be treated as orphans.
SKIP_NAMES = {".gitkeep"}


def resolve_root(arg_root: str | None) -> Path:
    if arg_root:
        return Path(arg_root).resolve()
    # tools/memory_sweep.py -> repo root is two parents up.
    return Path(__file__).resolve().parent.parent


def check_index_caps(index_path: Path) -> int:
    """Return number of cap problems (0 = ok). Warnings count as problems past 80%."""
    if not index_path.exists():
        print(f"[sweep] no index at {index_path} - nothing to check")
        return 0
    raw = index_path.read_bytes()
    n_bytes = len(raw)
    n_lines = raw.count(b"\n") + 1
    problems = 0
    if n_lines > MAX_INDEX_LINES:
        print(f"[sweep] FAIL: index has {n_lines} lines > {MAX_INDEX_LINES} cap "
              f"(newest entries are being SILENTLY dropped). Move detail to topics/.")
        problems += 1
    elif n_lines > MAX_INDEX_LINES * WARN_RATIO:
        print(f"[sweep] WARN: index lines {n_lines} are >{int(WARN_RATIO*100)}% of "
              f"the {MAX_INDEX_LINES} cap.")
    if n_bytes > MAX_INDEX_BYTES:
        print(f"[sweep] FAIL: index is {n_bytes} bytes > {MAX_INDEX_BYTES} cap "
              f"(newest entries are being SILENTLY dropped). Shorten entries to one line.")
        problems += 1
    elif n_bytes > MAX_INDEX_BYTES * WARN_RATIO:
        print(f"[sweep] WARN: index size {n_bytes} bytes is >{int(WARN_RATIO*100)}% of "
              f"the {MAX_INDEX_BYTES}-byte cap.")
    if problems == 0:
        print(f"[sweep] index ok: {n_lines} lines, {n_bytes} bytes")
    return problems


def find_orphans(index_path: Path, topics_dir: Path) -> list[Path]:
    """Topic files whose name is not referenced anywhere in the index text."""
    if not topics_dir.exists():
        return []
    index_text = index_path.read_text(encoding="utf-8", errors="replace") if index_path.exists() else ""
    orphans = []
    for topic in sorted(topics_dir.glob("*.md")):
        name = topic.name
        # Skip scaffolding and example files (mirror sweep_orphans.py behavior).
        if name in SKIP_NAMES or name.startswith("EXAMPLE"):
            continue
        # Match either the bare filename or the topics/<name> form, OS-agnostic.
        if name not in index_text and f"topics/{name}" not in index_text:
            orphans.append(topic)
    return orphans


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Memory orphan sweep + index cap check.")
    parser.add_argument("--root", default=None, help="Absolute repo root (defaults to repo containing this script).")
    parser.add_argument("--apply", action="store_true", help="Delete orphan topic files (default: report only).")
    args = parser.parse_args(argv)

    root = resolve_root(args.root)
    index_path = root / "memory" / "MEMORY.md"
    topics_dir = root / "memory" / "topics"

    cap_problems = check_index_caps(index_path)
    orphans = find_orphans(index_path, topics_dir)

    if not orphans:
        print("[sweep] no orphan topic files")
    else:
        verb = "Deleting" if args.apply else "Found (report only; pass --apply to delete)"
        print(f"[sweep] {verb} {len(orphans)} orphan topic file(s):")
        for o in orphans:
            print(f"  - {o}")
            if args.apply:
                o.unlink()

    if cap_problems:
        return 1
    if orphans and not args.apply:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
