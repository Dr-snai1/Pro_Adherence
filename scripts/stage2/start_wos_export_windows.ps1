#Requires -Version 5.1
<#
Stage 2 WoS batch exporter launcher. Use only for authorized WoS UI exports.
By default, imports owner-provided verified first 500 records from Downloads
and tests exactly ONE new chunk 501-1000. Run with -All only after approval.
Working files use the standard per-user local app-data folder; project evidence is archived separately to private Google Drive. No drive letter is assumed.
#>
param([switch]$All)

$ErrorActionPreference = 'Stop'
$appData = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { $env:TEMP }
if (-not $appData) { throw 'Cannot find a per-user temporary working folder' }
$base = Join-Path $appData 'Pro_Adherence\WoS_staging'
# Resolve installed Python using Windows launcher or PATH, without assuming C: or D:.
$pythonExe = $null
$pythonArgs = @()
if (Get-Command py.exe -ErrorAction SilentlyContinue) {
    $pythonExe = 'py.exe'
    $pythonArgs = @('-3')
} elseif (Get-Command python.exe -ErrorAction SilentlyContinue) {
    $pythonExe = 'python.exe'
} else {
    throw 'Python 3 is not installed or not on PATH; no files have been changed'
}
$ver = & $pythonExe @pythonArgs -c 'import sys; print(sys.version_info.major, sys.version_info.minor)'
if ($LASTEXITCODE -ne 0 -or -not $ver -or -not ($ver -match '^3\s+\d+')) {
    throw "Python 3 launch failed or version invalid: $ver"
}
$shaFirst = '3247EC52DABE2AB3A156DF6B57BFDD38B4E0496861458E70D0DE0F5FE59CE020'
$codeCommit = 'de541ddca5523c722a8e526fd696fcc6228d6d79'
$codeUrl = "https://raw.githubusercontent.com/Dr-snai1/Pro_Adherence/$codeCommit/scripts/stage2/wos_ui_export.py"
New-Item -ItemType Directory -Path $base -Force | Out-Null
$exports = Join-Path $base 'exports'
$temporary = Join-Path $base 'tmp'
$deps = Join-Path $base 'python_deps'
New-Item -ItemType Directory -Path $exports,$temporary,$deps -Force | Out-Null
$env:TEMP = $temporary
$env:TMP = $temporary
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
$env:PYTHONPATH = $deps
$destFirst = Join-Path $exports 'wos_000001_000500.txt'
if (Test-Path -LiteralPath $destFirst) {
    if ((Get-FileHash -LiteralPath $destFirst -Algorithm SHA256).Hash -ne $shaFirst) {
        throw 'Existing first batch differs; refusing to overwrite/mix search runs'
    }
} else {
    $downloadDirs = @((Join-Path $env:USERPROFILE 'Downloads'), (Join-Path $env:USERPROFILE 'Desktop'))
    $candidates = @()
    foreach ($d in $downloadDirs) {
        if (Test-Path -LiteralPath $d) {
            $candidates += @(Get-ChildItem -LiteralPath $d -Filter 'savedrecs*.txt' -File -ErrorAction Stop)
        }
    }
    $matching = @($candidates | Where-Object {
        (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash -eq $shaFirst
    })
    if ($matching.Count -lt 1) {
        throw 'Original first 500-record file not found in Downloads/Desktop. Keep it there or copy it there; SHA256 must match recorded batch'
    }
    Copy-Item -LiteralPath $matching[0].FullName -Destination $destFirst -ErrorAction Stop
    if ((Get-FileHash -LiteralPath $destFirst -Algorithm SHA256).Hash -ne $shaFirst) {
        throw 'First batch staging SHA256 mismatch'
    }
}
Write-Host 'First batch 1-500 SHA256 verified; will NOT export it again.'
$helper = Join-Path $base 'wos_ui_export.py'
if (!(Test-Path -LiteralPath $helper)) {
    Invoke-WebRequest -Uri $codeUrl -OutFile $helper -UseBasicParsing
}
if (!(Test-Path -LiteralPath (Join-Path $deps 'playwright\__init__.py'))) {
    & $pythonExe @pythonArgs -m pip install --no-cache-dir --disable-pip-version-check --target $deps 'playwright==1.55.0'
    if ($LASTEXITCODE -ne 0) { throw 'Playwright installation failed: Python pip may be unavailable' }
}
$max = 1
if ($All) { $max = 0 }
Write-Host "Local staging (temporary; NOT Google Drive): $base"
Write-Host "Now launching Chrome. Sign in and open the FULL 180-term WoS results (30,635 English Articles), then press Enter in the console."
Write-Host "Trial new export: records 501-1000; -All = remaining records 501-30635."
& $pythonExe @pythonArgs $helper --total 30635 --output $base --max-batches $max --authorized-export
if ($LASTEXITCODE -ne 0) { throw "WoS exporter stopped with exit $LASTEXITCODE; do not repeat 1-500" }
Write-Host "WOS_BATCH_SESSION_FINISHED. Temporary download: $base\exports"
Write-Host 'IMPORTANT: New batches are NOT YET on Google Drive. Upload each completed batch to the project private Drive before deletion from staging.'
