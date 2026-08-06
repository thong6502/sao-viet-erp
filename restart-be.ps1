# restart-be.ps1 — dọn các lượt init.ps1 đang chạy rồi dựng lại backend.
#
# Vì sao cần: chạy init.ps1 nhiều lượt chồng nhau thì các lượt cũ không tự chết, mỗi lượt ôm một
# pytest cày hết một lõi CPU. Kèm theo đó uvicorn --reload trên Windows hay KẸT: supervisor vẫn
# giữ cổng 8000 nên nhìn `netstat` tưởng đang chạy, mà gọi API thì treo chứ không phải 404.
#
# Dùng:
#   .\restart-be.ps1            dọn init.ps1 + dựng lại backend
#   .\restart-be.ps1 -ChiDon    chỉ dọn init.ps1, không đụng backend
[CmdletBinding()]
param(
  [int]$Port = 8000,
  [string]$RepoRoot = $PSScriptRoot,
  [string]$Python = 'python',
  [switch]$ChiDon
)

$ErrorActionPreference = 'Stop'

# ---- 1. Dừng mọi lượt init.ps1 và pytest con của nó -------------------------
# Khớp cả `-File .\init.ps1` lẫn `-Command ./init.ps1`. Loại trừ CHÍNH tiến trình đang chạy
# script này, không thì nó tự bắn vào chân mình.
$mau = 'init\.ps1|-m\s+pytest|\\pytest\.exe'
$rac = Get-CimInstance Win32_Process |
  Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match $mau }

if (-not $rac) {
  Write-Host "Khong co init.ps1/pytest nao dang chay."
} else {
  # Con trước, cha sau — giết cha trước thì pytest con thành mồ côi và vẫn cày CPU.
  foreach ($p in ($rac | Sort-Object ParentProcessId -Descending)) {
    $cl = ($p.CommandLine -replace '\s+', ' ')
    Write-Host ("dung {0}  {1}" -f $p.ProcessId, $cl.Substring(0, [Math]::Min(70, $cl.Length)))
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
  }
}

if ($ChiDon) { return }

# ---- 2. Giải phóng cổng -----------------------------------------------------
# Phải diệt CẢ CÂY, không chỉ tiến trình đang LISTEN: lúc kẹt, supervisor giữ cổng còn worker cũ
# vẫn sống nhưng không phục vụ.
foreach ($c in (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)) {
  $sup = $c.OwningProcess
  Get-CimInstance Win32_Process -Filter "ParentProcessId=$sup" |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  Stop-Process -Id $sup -Force -ErrorAction SilentlyContinue
  Write-Host "da giai phong cong $Port (PID $sup)"
}

for ($i = 0; $i -lt 10 -and (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue); $i++) {
  Start-Sleep -Milliseconds 300
}

# ---- 3. Dựng lại backend ----------------------------------------------------
$log = Join-Path $env:TEMP "uvicorn-$Port.log"
$p = Start-Process -FilePath $Python `
  -ArgumentList '-m', 'uvicorn', 'app.main:app', '--port', $Port, '--reload', '--timeout-graceful-shutdown', '1' `
  -WorkingDirectory (Join-Path $RepoRoot 'backend') `
  -RedirectStandardOutput $log -RedirectStandardError "$log.err" `
  -PassThru -WindowStyle Hidden
Write-Host "da khoi dong uvicorn PID $($p.Id) — log: $log"

# ---- 4. Chờ tới khi nó THẬT SỰ phục vụ -------------------------------------
# Cổng mở KHÔNG chứng minh app sống — lúc kẹt nó vẫn LISTEN. Phải gọi một endpoint thật.
for ($i = 1; $i -le 20; $i++) {
  try {
    if ((Invoke-WebRequest "http://127.0.0.1:$Port/openapi.json" -TimeoutSec 3 -UseBasicParsing).StatusCode -eq 200) {
      Write-Host "BE XANH sau $($i * 2)s — http://localhost:$Port" -ForegroundColor Green
      return
    }
  } catch { }
  Start-Sleep -Seconds 2
}
Write-Host "BE CHUA len sau 40s. Xem log: $log.err" -ForegroundColor Red
exit 1
