# Build the current firmware, copy it to where Caddy serves it (versioned +
# unversioned "current" pointer), and regenerate the auto-update manifest.
#
# Bump FW_VERSION in src/main.cpp first, then run this. Devices will pick up
# the new build on their next auto-update poll (default every hour).
#
#   .\tools\publish-firmware.ps1                            # build + publish
#   .\tools\publish-firmware.ps1 -Notes "fixed sensor X"    # add release notes
#   .\tools\publish-firmware.ps1 -OTA                       # also OTA the local
#                                                            # device on the LAN

param(
    [string]$Notes = "",
    [switch]$OTA
)

$ErrorActionPreference = "Stop"

$Project   = (Resolve-Path "$PSScriptRoot\..").Path
$MainCpp   = Join-Path $Project "src\main.cpp"
$FwDir     = Join-Path $Project "website\static\firmware"
$Manifest  = Join-Path $FwDir "latest.json"
$PioExe    = "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe"
$PublicUrl = "https://temp.kyro-labs.com"

# 1. Extract FW_VERSION from main.cpp (the line that defines it).
$versionLine = Select-String -Path $MainCpp -Pattern 'FW_VERSION\s*=\s*"([^"]+)"' | Select-Object -First 1
if (-not $versionLine) {
    Write-Error "Could not find FW_VERSION in $MainCpp"
}
$version = $versionLine.Matches[0].Groups[1].Value
Write-Host "FW_VERSION: $version"

# 2. Build.
Write-Host "--- building ---"
& $PioExe run -e esp32dev | Select-Object -Last 6
if ($LASTEXITCODE -ne 0) { Write-Error "build failed" }

$binSrc = Join-Path $Project ".pio\build\esp32dev\firmware.bin"
if (-not (Test-Path $binSrc)) { Write-Error "firmware.bin not found at $binSrc" }

# 3. Stage.
New-Item -ItemType Directory -Force -Path $FwDir | Out-Null
$binVersioned = Join-Path $FwDir "firmware-$version.bin"
$binCurrent   = Join-Path (Split-Path $FwDir) "firmware.bin"   # /static/firmware.bin for Mac OTA one-liner
Copy-Item $binSrc $binVersioned -Force
Copy-Item $binSrc $binCurrent   -Force
$binSize = (Get-Item $binVersioned).Length

# 4. Write manifest. Done in Python to avoid PowerShell UTF-8-BOM nonsense.
$venvPy = Join-Path $Project "website\.venv\Scripts\python.exe"
& $venvPy -c @"
import json, datetime
m = {
    'version':     '$version',
    'url':         '$PublicUrl/static/firmware/firmware-$version.bin',
    'size_bytes':  $binSize,
    'released_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    'notes':       '''$Notes'''.strip(),
}
import os
with open(r'$Manifest', 'w', encoding='utf-8', newline='\n') as f:
    json.dump(m, f, indent=2)
print('manifest:')
print(json.dumps(m, indent=2))
"@

# 5. Optional: also OTA the device on the local LAN right now.
if ($OTA) {
    Write-Host "--- OTA push to pool-temp.local ---"
    Remove-Item Env:PLATFORMIO_UPLOAD_FLAGS -ErrorAction SilentlyContinue
    & $PioExe run -e esp32dev_ota -t upload
    if ($LASTEXITCODE -ne 0) { Write-Warning "OTA push failed (will still self-update next poll)" }
}

Write-Host ""
Write-Host "Published firmware $version."
Write-Host "  Versioned:    $PublicUrl/static/firmware/firmware-$version.bin"
Write-Host "  Latest alias: $PublicUrl/static/firmware.bin"
Write-Host "  Manifest:     $PublicUrl/static/firmware/latest.json"
Write-Host ""
Write-Host "Devices with auto-update enabled will pick this up on their next poll."
Write-Host "Mac OTA one-liner (forces immediate install on a specific device):"
Write-Host "  curl -fsSO $PublicUrl/static/firmware.bin && \"
Write-Host "    curl -fsSO $PublicUrl/static/espota.py && \"
Write-Host "    python3 espota.py -i pool-temp.local -p 3232 -a pool-ota -f firmware.bin"
