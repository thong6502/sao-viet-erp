#!/usr/bin/env pwsh
# PowerShell verification entrypoint (Windows equivalent of init.sh).
# Keep this in sync with init.sh.

$ErrorActionPreference = 'Stop'

# Native commands (python) don't throw on nonzero exit; check $LASTEXITCODE.
function Invoke-Step {
    param(
        [Parameter(Mandatory)] [string] $Name,
        [Parameter(Mandatory)] [scriptblock] $Command
    )
    Write-Host "=== $Name ==="
    & $Command
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Step failed: $Name (exit $LASTEXITCODE)"
        exit $LASTEXITCODE
    }
}

Write-Host "=== Verification ==="

$compileExclude = '([\\/](\.git|node_modules|\.venv|venv|dist|\.pytest_cache))'

Invoke-Step "python -m pytest"        { python -m pytest }
Invoke-Step "python -m compileall ."  { python -m compileall -q -x $compileExclude . }

Write-Host "=== Verification Complete ==="
