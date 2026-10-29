#Requires -Version 5.1
<#
Pro_Adherence Stage2: 501..30635 WoS batch export, one verified ZIP
for private Google Drive. Google sign-in is NEVER attempted in Playwright.
Owner uploads ONE ZIP using ordinary signed-in Chrome after the batch run.

No USB/D: writes, no re-export of 1..500, no arbitrary locations.
Outputs: one all-batches ZIP containing 61 raw TXT, SHA/UT/NR manifest, exact scripts.
The original first 500 are ALREADY in owner-only Drive; do not duplicate them.
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
$codeCommit = '94f110d8105a40892862875458ae5d5505ba17ac'
$baseUrl = "https://raw.githubusercontent.com/Dr-snai1/Pro_Adherence/$codeCommit"
$names = @(
    'wos_drive_session.py',
    'wos_ui_export.py',
    'wos_search_plan.py'
)
foreach ($name in $names) {
    $dst = Join-Path $toolDir $name
    # Always fetch this immutable code revision. Cached previous Python had
    # broken Google automation and MUST NEVER run again.
    Invoke-WebRequest "$baseUrl/scripts/stage2/$name" -OutFile $dst -UseBasicParsing
}
# Immutable frozen scientific source used by the WoS search planner.
$configName = 'medication-adherence-SELECTED.v1.json'
$configPath = Join-Path $toolDir $configName
Invoke-WebRequest "$baseUrl/configs/pubmed/$configName" -OutFile $configPath -UseBasicParsing
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
Write-Host 'Automated Chrome opens Brunel Library; search Web of Science and use Brunel Sign In.'
Write-Host 'IMPORTANT: Smart Search is NOT the required results page.'
Write-Host 'Open the existing 30,635-result page in that Chrome (or paste its address into the console).'
Write-Host 'Early Enter will now show open tabs and ask again, instead of stopping.'
Write-Host 'Do not enter a Clarivate personal login or sign into Google there.'
Write-Host 'Final results+manifest+scripts will be packed into ONE ZIP on C:.'
Write-Host 'Then use your NORMAL Chrome to upload that ZIP into the project Google Drive.'
& $python @pyFlags (Join-Path $toolDir 'wos_drive_session.py')
if ($LASTEXITCODE -ne 0) {
    throw "Export/upload stopped. Preserve C: files and console message; exit $LASTEXITCODE."
}
Write-Host 'Archive is prepared on C: for one manual Google Drive upload in normal Chrome; NOT uploaded yet.'
Write-Host 'CLEANUP PROHIBITED until independent Drive checks match SHA256 manifest.'
