# Local-build fallback for the firmware publishing pipeline. Normally CI
# (.github/workflows/firmware.yml) handles this: bump FW_VERSION, push to
# main, GitHub Actions builds + commits the binary + manifest + makes a
# Release. Run this script only when you want to publish without pushing
# (e.g. you're at the pool and can't wait for CI).
#
#   .\tools\publish-firmware.ps1                # build + stage locally (you commit)
#   .\tools\publish-firmware.ps1 -Notes "..."   # add manifest notes
#   .\tools\publish-firmware.ps1 -OTA           # also OTA push to pool-temp.local
#   .\tools\publish-firmware.ps1 -Push          # commit + push + (CI will then make the release)

param(
    [string]$Notes = "",
    [switch]$OTA,
    [switch]$Push
)

$ErrorActionPreference = "Stop"

$Project    = (Resolve-Path "$PSScriptRoot\..").Path
$MainCpp    = Join-Path $Project "src\main.cpp"
$FwDir      = Join-Path $Project "website\static\firmware"
$Manifest   = Join-Path $FwDir "latest.json"
$PioExe     = "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe"

# Where the device (and any Mac at the pool) fetches firmware from. The CI
# workflow uses the same scheme so the two paths stay in sync.
$RepoSlug   = "sowoky/pool-temp"
$RawBase    = "https://raw.githubusercontent.com/$RepoSlug/main/website/static/firmware"

# 1. Extract FW_VERSION.
$versionLine = Select-String -Path $MainCpp -Pattern 'FW_VERSION\s*=\s*"([^"]+)"' | Select-Object -First 1
if (-not $versionLine) { Write-Error "Could not find FW_VERSION in $MainCpp" }
$version = $versionLine.Matches[0].Groups[1].Value
Write-Host "FW_VERSION: $version"

# 2. Build.
Write-Host "--- building ---"
& $PioExe run -e esp32dev | Select-Object -Last 6
if ($LASTEXITCODE -ne 0) { Write-Error "build failed" }

$binSrc = Join-Path $Project ".pio\build\esp32dev\firmware.bin"
if (-not (Test-Path $binSrc)) { Write-Error "firmware.bin not found at $binSrc" }

# 3. Stage versioned binary inside the repo.
New-Item -ItemType Directory -Force -Path $FwDir | Out-Null
$binVersioned = Join-Path $FwDir "firmware-$version.bin"
Copy-Item $binSrc $binVersioned -Force
$binSize = (Get-Item $binVersioned).Length

# 4. Manifest. Hand-rolled so we don't pick up PowerShell's UTF-8 BOM nonsense.
$releasedAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$notesEsc   = ($Notes -replace '"', '\"')
$manifestJson = @"
{
  "version": "$version",
  "url": "$RawBase/firmware-$version.bin",
  "size_bytes": $binSize,
  "released_at": "$releasedAt",
  "notes": "$notesEsc"
}
"@
Set-Content -Path $Manifest -Value $manifestJson -Encoding utf8
Write-Host "manifest:"
Get-Content $Manifest

# 5. Optional immediate OTA to the LAN device.
if ($OTA) {
    Write-Host "--- OTA push to pool-temp.local ---"
    Remove-Item Env:PLATFORMIO_UPLOAD_FLAGS -ErrorAction SilentlyContinue
    & $PioExe run -e esp32dev_ota -t upload
    if ($LASTEXITCODE -ne 0) { Write-Warning "OTA push failed (will still self-update on next poll)" }
}

# 6. Optional commit + push. CI takes it from there (builds again, makes a Release).
if ($Push) {
    Write-Host "--- commit + push ---"
    git -C $Project add "website/static/firmware/firmware-$version.bin" "website/static/firmware/latest.json"
    git -C $Project commit -m "publish firmware $version$( if ($Notes) { " - $Notes" } else { "" } )"
    git -C $Project push
}

Write-Host ""
Write-Host "Published firmware $version."
Write-Host "  Binary:   $RawBase/firmware-$version.bin"
Write-Host "  Manifest: $RawBase/latest.json"
Write-Host ""
Write-Host "Devices with auto-update enabled will pick this up on their next poll"
Write-Host "(default 1h, after this commit is pushed to main on GitHub)."
Write-Host ""
Write-Host "Mac OTA one-liner (forces immediate install on a specific device):"
Write-Host "  mkdir -p /tmp/pt && cd /tmp/pt && \"
Write-Host "    curl -fsSL -o firmware.bin $RawBase/firmware-$version.bin && \"
Write-Host "    curl -fsSL -o espota.py https://raw.githubusercontent.com/espressif/arduino-esp32/master/tools/espota.py && \"
Write-Host "    python3 espota.py -i pool-temp.local -p 3232 -a pool-ota -f firmware.bin -d"
