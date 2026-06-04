#!/usr/bin/env pwsh
# Validate project skills under .claude/skills/ (Windows equivalent of validate-skills.sh).
# Keep in sync with validate-skills.sh (same checks, same exit codes).
#
# Checks, per .claude/skills/*/SKILL.md:
#   - file has a YAML frontmatter block (--- ... ---)
#   - frontmatter has a non-empty `name:` and `description:`
#   - `name` matches the skill's directory name
#   - every relative markdown link referenced in SKILL.md exists
# Exits non-zero on the first failure so it can gate CI.
$ErrorActionPreference = 'Stop'

function Fail([string]$msg) {
    Write-Error "SKILL VALIDATION FAILED: $msg"
    exit 1
}

# Resolve skills dir: this script lives at .claude/skills/scripts/.
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SkillsDir = (Resolve-Path (Join-Path $ScriptDir '..')).Path

$skillFiles = Get-ChildItem -Path $SkillsDir -Directory |
    ForEach-Object { Join-Path $_.FullName 'SKILL.md' } |
    Where-Object { Test-Path $_ }

if (-not $skillFiles) { Fail "no SKILL.md files found under $SkillsDir" }

foreach ($skillMd in $skillFiles) {
    $skillDir = Split-Path -Parent $skillMd
    $dirName  = Split-Path -Leaf $skillDir
    Write-Host "=== validating $dirName ==="

    $lines = Get-Content -LiteralPath $skillMd
    if ($lines.Count -lt 1 -or $lines[0].Trim() -ne '---') {
        Fail "$dirName/SKILL.md: missing frontmatter (first line must be ---)"
    }

    # Collect frontmatter block (between first two --- lines).
    $fm = @()
    for ($i = 1; $i -lt $lines.Count; $i++) {
        if ($lines[$i].Trim() -eq '---') { break }
        $fm += $lines[$i]
    }

    $nameLine = $fm | Where-Object { $_ -match '^name:\s*(.+?)\s*$' } | Select-Object -First 1
    if (-not $nameLine) { Fail "$dirName/SKILL.md: frontmatter missing non-empty 'name:'" }
    $nameVal = ($nameLine -replace '^name:\s*', '').Trim()
    if (-not $nameVal) { Fail "$dirName/SKILL.md: frontmatter missing non-empty 'name:'" }
    if ($nameVal -ne $dirName) { Fail "$dirName/SKILL.md: name '$nameVal' != directory '$dirName'" }

    # description may be inline or a YAML block scalar (>- / |) — accept either.
    if (-not ($fm | Where-Object { $_ -match '^description:\s*(\S.*|[>|].*)?$' })) {
        Fail "$dirName/SKILL.md: frontmatter missing 'description:'"
    }

    # Every relative link target must resolve to a real file.
    $text = Get-Content -LiteralPath $skillMd -Raw
    foreach ($m in [regex]::Matches($text, '\]\(([^)]+)\)')) {
        $link = $m.Groups[1].Value.Trim()
        if ($link -match '^(https?://|mailto:|#)') { continue }
        $target = ($link -split '#', 2)[0]
        if (-not $target) { continue }
        $targetPath = Join-Path $skillDir $target
        if (-not (Test-Path -LiteralPath $targetPath)) {
            Fail "$dirName/SKILL.md: broken link -> $target"
        }
    }

    Write-Host "ok: $dirName"
}

Write-Host "=== all skills valid ==="
