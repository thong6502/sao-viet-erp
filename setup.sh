#!/usr/bin/env bash
# setup.sh — One-shot setup: backend (pip) + frontend (npm) deps + seed .env files.
#   Usage:  ./setup.sh            (run from the project root)
#   Then:   ./dev.sh to run the app, ./init.sh to verify.
# Keep in sync with setup.ps1 (same steps).
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Setup: GAN App / Sao Viet Nhat ERP ==="

# 1) Prerequisites
require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Thiếu '$1'. $2" >&2
    exit 1
  fi
  echo "[ok]   $1 -> $(command -v "$1")"
}
PY=python3
command -v python3 >/dev/null 2>&1 || PY=python
require_cmd "$PY" "Cài Python 3.10+ rồi chạy lại."
require_cmd npm "Cài Node.js 18+ (kèm npm) rồi chạy lại."

# 2) Seed .env from .env.example if missing (never overwrite — keep existing secrets)
ensure_env() {
  local example="$1" target="$2"
  if [ -f "$target" ]; then
    echo "[skip] $target đã có (giữ nguyên)"
  elif [ -f "$example" ]; then
    cp "$example" "$target"
    echo "[new]  $target (copy từ $example)"
  fi
}
echo
echo "--- .env ---"
ensure_env "$root/.env.example"          "$root/.env"
ensure_env "$root/backend/.env.example"  "$root/backend/.env"
ensure_env "$root/frontend/.env.example" "$root/frontend/.env"

# 3) Backend deps
echo
echo "--- Backend deps (pip) ---"
"$PY" -m pip install -r "$root/backend/requirements.txt"

# 4) Frontend deps
echo
echo "--- Frontend deps (npm) ---"
( cd "$root/frontend" && npm install )

echo
echo "=== Setup xong ==="
echo "Tiếp theo:"
echo "  ./dev.sh      # chạy backend (:8000) + frontend (:5173)"
echo "  ./init.sh     # verify (pytest + compileall)"
echo "Đăng nhập demo: admin / admin123"
echo "LƯU Ý: .env đang dùng JWT_SECRET mặc định (dev). Đổi nó + đặt APP_ENV=production trước khi deploy thật."
