#!/usr/bin/env pwsh
# dev.ps1 — Chạy CẢ Backend (FastAPI :8000) lẫn Frontend (Vite :5173) bằng 1 lệnh.
#   Backend mở ở cửa sổ PowerShell riêng (xem log uvicorn); Frontend chạy ở cửa sổ này.
#   Ctrl+C (hoặc đóng cửa sổ này) sẽ dừng luôn backend.
# Dùng:  ./dev.ps1
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

# Cài frontend deps lần đầu (nếu chưa có node_modules)
if (-not (Test-Path "$root/frontend/node_modules")) {
  Write-Host "[dev] Cài frontend deps (lần đầu)..." -ForegroundColor Cyan
  Push-Location "$root/frontend"; npm install; Pop-Location
}

Write-Host "[dev] Backend  -> http://localhost:8000  (cửa sổ riêng)" -ForegroundColor Green
Write-Host "[dev] Frontend -> http://localhost:5173  (cửa sổ này)"   -ForegroundColor Green
Write-Host "[dev] Đăng nhập: admin@example.com / admin123"           -ForegroundColor DarkGray
Write-Host "[dev] Ctrl+C để dừng cả hai.`n"                          -ForegroundColor DarkGray

# Backend ở tiến trình/cửa sổ riêng để log uvicorn hiện rõ
$backend = Start-Process powershell -PassThru -ArgumentList @(
  '-NoExit', '-Command',
  "Set-Location '$root/backend'; python -m uvicorn app.main:app --port 8000 --reload"
)

try {
  # Frontend ở foreground — log Vite hiện ngay trong cửa sổ này
  Set-Location "$root/frontend"
  npm run dev
}
finally {
  Write-Host "`n[dev] Đang dừng backend..." -ForegroundColor Yellow
  if ($backend -and -not $backend.HasExited) {
    Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
  }
  # Dọn sạch tiến trình con của uvicorn còn giữ cổng 8000
  Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}
