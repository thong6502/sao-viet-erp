#!/usr/bin/env bash
# Thin Unix wrapper for the cross-platform memory sweep. Passes args through.
# Report only:  ./tools/memory_sweep.sh
# Apply:        ./tools/memory_sweep.sh --apply
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$(command -v python3 || command -v python)"
exec "$PY" "$SCRIPT_DIR/memory_sweep.py" "$@"
