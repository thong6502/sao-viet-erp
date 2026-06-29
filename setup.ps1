#!/usr/bin/env pwsh
# setup.ps1 — Cài đặt MỘT PHÁT: deps backend (pip) + frontend (npm) + tạo .env mẫu.
#   Dùng:   ./setup.ps1            (chạy ở thư mục gốc dự án)
#   Sau đó: ./dev.ps1 để chạy app, ./init.ps1 để verify.
# Giữ song song với setup.sh (cùng các bước).
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

Write-Host "=== Setup: GAN App / Sao Viet Nhat ERP ===" -ForegroundColor Cyan

# 1) Kiểm tra prerequisite
function Require-Cmd([string]$name, [string]$hint) {
  $cmd = Get-Command $name -ErrorAction SilentlyContinue
  if (-not $cmd) { Write-Error "Thiếu '$name'. $hint"; exit 1 }
  Write-Host "[ok]   $name -> $($cmd.Source)" -ForegroundColor DarkGray
}
Require-Cmd python "Cài Python 3.10+ rồi chạy lại."
Require-Cmd npm    "Cài Node.js 18+ (kèm npm) rồi chạy lại."

# 2) Tạo .env từ .env.example nếu CHƯA có (không ghi đè để khỏi mất secret)
function Ensure-Env([string]$example, [string]$target) {
  if (Test-Path $target) {
    Write-Host "[skip] $target đã có (giữ nguyên)" -ForegroundColor DarkGray
  } elseif (Test-Path $example) {
    Copy-Item $example $target
    Write-Host "[new]  $target (copy từ $example)" -ForegroundColor Green
  }
}
Write-Host "`n--- .env ---" -ForegroundColor Cyan
Ensure-Env "$root/.env.example"          "$root/.env"
Ensure-Env "$root/backend/.env.example"  "$root/backend/.env"
Ensure-Env "$root/frontend/.env.example" "$root/frontend/.env"

# 3) Backend deps
Write-Host "`n--- Backend deps (pip) ---" -ForegroundColor Cyan
python -m pip install -r "$root/backend/requirements.txt"
if ($LASTEXITCODE -ne 0) { Write-Error "pip install thất bại"; exit $LASTEXITCODE }

# 4) Frontend deps
Write-Host "`n--- Frontend deps (npm) ---" -ForegroundColor Cyan
Push-Location "$root/frontend"
npm install
$npmExit = $LASTEXITCODE
Pop-Location
if ($npmExit -ne 0) { Write-Error "npm install thất bại"; exit $npmExit }

Write-Host "`n=== Setup xong ===" -ForegroundColor Green
Write-Host "Tiếp theo:"
Write-Host "  ./dev.ps1     # chạy backend (:8000) + frontend (:5173)"
Write-Host "  ./init.ps1    # verify (pytest + compileall)"
Write-Host "Đăng nhập demo: admin@example.com / admin123"
Write-Host "LƯU Ý: .env đang dùng JWT_SECRET mặc định (dev). Đổi nó + đặt APP_ENV=production trước khi deploy thật." -ForegroundColor Yellow
