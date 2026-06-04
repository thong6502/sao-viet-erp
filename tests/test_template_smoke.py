"""Template integrity smoke test.

Two jobs:
1. Keep `init.sh` / `init.ps1` green (pytest must collect at least one test).
2. Verify the GAN template's core files exist, so a fresh copy is never half-broken.

When you build the real app, add backend/unit tests alongside this one
(see `pytest.ini` -> testpaths).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The skeleton every GAN-template copy must ship with, grouped by role.
EXPECTED = [
    # base / router
    "AGENTS.md", "CLAUDE.md", "QUICKSTART.md", "feature_list.json", "progress.md",
    "init.sh", "init.ps1", "pytest.ini", ".gitignore", ".gitattributes",
    # Planner (human writes sprint -> agent offers options -> feature_list)
    "docs/PRODUCT_SENSE.md", "docs/product-specs/index.md", "docs/product-specs/_TEMPLATE.md",
    ".claude/skills/plan/SKILL.md",
    # Generator (build each feature)
    "docs/ARCHITECTURE.md", "docs/UI_DESIGN.md", ".claude/skills/generate/SKILL.md",
    # Evaluator (Playwright click + score)
    "docs/EVALUATION.md", ".claude/skills/browser-validate/SKILL.md",
    "docs/sops/browser-validation-loop.md",
    # Orchestration (ties the 3 roles into a loop)
    "docs/ORCHESTRATION.md", ".claude/workflows/gan-loop.js",
    # cross-cutting
    "docs/SECURITY.md",
]


def test_core_template_files_exist():
    missing = [p for p in EXPECTED if not (ROOT / p).exists()]
    assert not missing, f"GAN template is missing required files: {missing}"
