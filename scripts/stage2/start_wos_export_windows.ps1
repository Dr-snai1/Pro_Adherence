#Requires -Version 5.1
<#
Pro_Adherence Stage2 WoS: upload 501..30635 via native Chrome UI to owner-only
project Google Drive, retaining C: fallback until independent Drive verification.

No USB/D: writes, no re-export of 1..500, no arbitrary locations.
Outputs: raw WoS TXT batches, SHA/UT/NR manifest, exact reproducibility script ZIP.
DO NOT delete C: staging until 03 has verified remote bytes and IDs.
#>
param([switch]$PreflightOnly)
$ErrorActionPreference = 'Stop'
$folderId = '1h9Y-wjhpl3gc1wog0VP_qPaCxBWoeVyV'
$expectedTotal = 30635
$root = $env:LOCALAPPDATA
if (!$root -or !([System.IO.Path]::GetFullPath($root).StartsWith('C:\',[System.StringComparison]::OrdinalIgnoreCase))) {
    throw 'C: LOCALAPPDATA missing; no alternative drive will be chosen'
}
$base = Join-Path $root 'Pro_Adherence\WoS_Stage2_Temp'
$deps = Join-Path $base 'python_deps'
$toolDir = Join-Path $base 'runner'
New-Item -ItemType Directory -Path $base,$deps,$toolDir -Force | Out-Null

# Search the pre-existing project Python, then installed Windows Python 3.
$projectPython = 'C:\Pro_Adherence\python-3.13.16\python.exe'
$python = $null
$pyFlags = @()
if (Test-Path -LiteralPath $projectPython) {
    $python = $projectPython
} elseif (Get-Command py.exe -ErrorAction SilentlyContinue) {
    $python = 'py.exe'
    $pyFlags = @('-3.13')
} elseif (Get-Command python.exe -ErrorAction SilentlyContinue) {
    $python = 'python.exe'
} else {
    throw 'Python 3.13 not found; installation and code execution stopped'
}
# Windows PowerShell 5.1 can strip quotes in python -c; use a real CLI
# version flag instead of passing a fragile Python expression through shells.
$versionOutput = & $python @pyFlags --version 2>&1
$versionExit = $LASTEXITCODE
$versionText = ($versionOutput | Out-String).Trim()
if ($versionExit -ne 0 -or $versionText -notmatch '^Python 3\.13(?:\.\d+)?(?:\s|$)') {
    throw "Project requires Python 3.13; command: $python $($pyFlags -join ' '); status: $versionExit; output: $versionText"
}
Write-Host "PYTHON_VERSION_OK: $versionText"
if ($PreflightOnly) {
    Write-Host "PYTHON_PREFLIGHT_ONLY_PASS: no browser, internet, export or upload started"
    return
}
$env:PYTHONPATH = $deps
$env:TEMP = Join-Path $base 'temporary'
$env:TMP = $env:TEMP
$env:PYTHONDONTWRITEBYTECODE = '1'
New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null

# Immutable GitHub commit after the new Drive session implementation landed.
# Script source is public code only, never private research data.
$codeCommit = '90d1e47f06f2bef9d0f850e72c44e0bbaa866bcd'
$baseUrl = "https://raw.githubusercontent.com/Dr-snai1/Pro_Adherence/$codeCommit"
$names = @(
    'wos_drive_session.py',
    'wos_ui_export.py',
    'wos_search_plan.py'
)
foreach ($name in $names) {
    $dst = Join-Path $toolDir $name
    if (!(Test-Path -LiteralPath $dst)) {
        Invoke-WebRequest "$baseUrl/scripts/stage2/$name" -OutFile $dst -UseBasicParsing
    }
}
# Immutable frozen scientific source used by the WoS search planner.
$configName = 'medication-adherence-SELECTED.v1.json'
$configPath = Join-Path $toolDir $configName
if (!(Test-Path -LiteralPath $configPath)) {
    Invoke-WebRequest "$baseUrl/configs/pubmed/$configName" -OutFile $configPath -UseBasicParsing
}
$selfInBundle = Join-Path $toolDir 'start_wos_export_windows.ps1'
if ([System.IO.Path]::GetFullPath($PSCommandPath) -ine [System.IO.Path]::GetFullPath($selfInBundle)) {
    Copy-Item -LiteralPath $PSCommandPath -Destination $selfInBundle -Force
}

if (!(Test-Path -LiteralPath (Join-Path $deps 'playwright\__init__.py'))) {
    & $python @pyFlags -m pip install --disable-pip-version-check --no-cache-dir --target $deps 'playwright==1.55.0'
    if ($LASTEXITCODE -ne 0) { throw 'Playwright installation failed' }
}
Write-Host "Using authorized temporary C: folder: $base"
Write-Host "Project private Drive: https://drive.google.com/drive/folders/$folderId"
Write-Host 'The first 500 records are already archived. Script starts at 501.'
Write-Host 'IMPORTANT: files remain on C: until Drive upload and independent remote verification.'
& $python @pyFlags (Join-Path $toolDir 'wos_drive_session.py')
if ($LASTEXITCODE -ne 0) {
    throw "Export/upload stopped. Preserve C: files and console message; exit $LASTEXITCODE."
}
Write-Host 'WoS source batches and final manifest/scripts uploaded via Google Drive UI.'
Write-Host 'CLEANUP PROHIBITED until independent Drive checks match SHA256 manifest.'
