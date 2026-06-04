#!/usr/bin/env pwsh
# Thin PowerShell wrapper for the cross-platform memory sweep. Passes args through.
# Report only:  ./tools/memory_sweep.ps1
# Apply:        ./tools/memory_sweep.ps1 --apply
$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = (Get-Command python -ErrorAction SilentlyContinue) ?? (Get-Command python3 -ErrorAction SilentlyContinue)
if ($null -eq $py) { Write-Error 'Python not found on PATH'; exit 1 }
& $py.Source (Join-Path $scriptDir 'memory_sweep.py') @args
exit $LASTEXITCODE
