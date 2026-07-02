#!/bin/bash
set -e

echo "=== Verification ==="

echo "=== python -m pytest ==="
python -m pytest

echo "=== python -m compileall . ==="
python -m compileall -q -x '([\\/](\.git|node_modules|\.venv|venv|dist|\.pytest_cache))' .

echo "=== Verification Complete ==="
