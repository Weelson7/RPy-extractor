# One-at-a-time pass over a folder of installed games: copy each into Test-games/<slug>, run the
# integration runner on that copy only, keep the report, delete the copy and its workspace.
# Usage: powershell -File tools/games_pass.ps1 [-Source C:\Users\me\Games] [-SkipExtractOverGB 40]
param(
    [string]$Source = "C:\Users\weel-\Games",
    [double]$SkipExtractOverGB = 40,
    [string[]]$Skip = @("ApproximatelyUp-Modding", "CYPMods", "bannerlord", "AU")
)
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$games = Join-Path $root "Test-games"
$reports = Join-Path $root "viwo-data\games-pass"
New-Item -ItemType Directory -Force $reports | Out-Null
$log = Join-Path $reports "pass.log"

function Say($text) { $line = "{0} {1}" -f (Get-Date -Format "HH:mm:ss"), $text; $line | Tee-Object -FilePath $log -Append }

foreach ($dir in Get-ChildItem $Source -Directory) {
    if ($Skip -contains $dir.Name) { Say "skip $($dir.Name)"; continue }
    # a wrapper folder holding exactly one sub-folder and no files is unwrapped (AoE, zipped data)
    $src = $dir.FullName
    while ((Get-ChildItem $src -File).Count -eq 0 -and (Get-ChildItem $src -Directory).Count -eq 1) {
        $src = (Get-ChildItem $src -Directory)[0].FullName
    }
    $slug = ("pass-" + ($dir.Name -replace "[^A-Za-z0-9]+", "-").Trim("-")).ToLower()
    $size = (Get-ChildItem $src -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum / 1GB
    $free = (Get-PSDrive C).Free / 1GB
    if ($size * 1.1 -gt $free) { Say "$slug needs $([math]::Round($size,1)) GB, only $([math]::Round($free,1)) GB free: skipped"; continue }
    $copy = Join-Path $games $slug
    Say "copy $($dir.Name) ($([math]::Round($size,1)) GB) -> $slug"
    robocopy $src $copy /E /NFL /NDL /NJH /NJS /NP /R:1 /W:1 | Out-Null
    $out = Join-Path $reports $slug
    $extra = @()
    if ($size -gt $SkipExtractOverGB) { $extra = @("--skip-extract") }
    Say "run $slug $extra"
    & $python (Join-Path $root "tools\integration_games.py") --games $games --out $out --only $slug @extra 2>&1 | Select-Object -Last 3 | ForEach-Object { Say "  $_" }
    Remove-Item -Recurse -Force $copy -ErrorAction SilentlyContinue
    Get-ChildItem $out -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue  # workspaces, keep report.*
    Say "done $slug (copy and workspace removed)"
}
Say "pass finished"
