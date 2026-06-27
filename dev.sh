#!/usr/bin/env bash
# dev.sh — Run BOTH Backend (FastAPI :8000) and Frontend (Vite :5173) with one command.
#   Backend runs in the background; Frontend in the foreground (logs interleave here).
#   Ctrl+C stops both.
# Usage:  ./dev.sh
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Install frontend deps on first run
if [ ! -d "$root/frontend/node_modules" ]; then
  echo "[dev] Installing frontend deps (first run)..."
  (cd "$root/frontend" && npm install)
fi

echo "[dev] Backend  -> http://localhost:8000"
echo "[dev] Frontend -> http://localhost:5173"
echo "[dev] Login: admin@example.com / admin123"
echo "[dev] Ctrl+C to stop both."
echo

# Backend in the background
( cd "$root/backend" && python -m uvicorn app.main:app --port 8000 --reload ) &
backend_pid=$!

cleanup() {
  echo
  echo "[dev] Stopping backend..."
  kill "$backend_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Frontend in the foreground
( cd "$root/frontend" && npm run dev )
