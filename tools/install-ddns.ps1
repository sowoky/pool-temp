# Sets up the Cloudflare DDNS updater as a scheduled task running every 5 min.
# Prerequisites: kyleroden.com's nameservers must already be pointing at Cloudflare,
# and you must have a Cloudflare API token with Zone:DNS:Edit scope.
#
# Run from an elevated PowerShell:  Right-click -> Run with PowerShell as Admin
#
# The script prompts for the token and zone, then stores them as machine-scope env vars.

#requires -RunAsAdministrator

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
$WebsiteVenv = Join-Path $ProjectRoot "website\.venv\Scripts\python.exe"
$DdnsScript  = Join-Path $ProjectRoot "tools\cloudflare_ddns.py"
$TaskName    = "PoolTempCloudflareDDNS"

if (-not (Test-Path $WebsiteVenv)) {
    Write-Error "Python venv not found at $WebsiteVenv. Run website\run.bat first."
}
if (-not (Test-Path $DdnsScript)) {
    Write-Error "DDNS script not found at $DdnsScript."
}

# Verify the venv has requests installed (cloudflare_ddns.py needs it).
& $WebsiteVenv -c "import requests" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "venv missing 'requests' module. Run: $WebsiteVenv -m pip install requests"
}

# Prompt for secrets (don't echo the token).
$existingToken = [Environment]::GetEnvironmentVariable("CF_API_TOKEN", "Machine")
if ($existingToken) {
    Write-Host "CF_API_TOKEN already set machine-wide. Reusing."
} else {
    $token = Read-Host "Cloudflare API token (Zone:DNS:Edit scope)" -AsSecureString
    $plain = [System.Net.NetworkCredential]::new("", $token).Password
    [Environment]::SetEnvironmentVariable("CF_API_TOKEN", $plain, "Machine")
    Write-Host "Stored CF_API_TOKEN (machine scope)."
}

$existingZone = [Environment]::GetEnvironmentVariable("CF_ZONE_NAME", "Machine")
if (-not $existingZone) {
    $zone = Read-Host "Cloudflare zone (e.g. kyleroden.com)"
    [Environment]::SetEnvironmentVariable("CF_ZONE_NAME", $zone, "Machine")
} else {
    Write-Host "CF_ZONE_NAME already set: $existingZone"
}

$existingRecord = [Environment]::GetEnvironmentVariable("CF_RECORD_NAME", "Machine")
if (-not $existingRecord) {
    $defaultRec = [Environment]::GetEnvironmentVariable("CF_ZONE_NAME", "Machine")
    $rec = Read-Host "Full record name to update [$defaultRec]"
    if ([string]::IsNullOrWhiteSpace($rec)) { $rec = $defaultRec }
    [Environment]::SetEnvironmentVariable("CF_RECORD_NAME", $rec, "Machine")
}

# Sanity-run once.
Write-Host "`nRunning one-shot DDNS update as a sanity check..."
$env:CF_API_TOKEN   = [Environment]::GetEnvironmentVariable("CF_API_TOKEN",   "Machine")
$env:CF_ZONE_NAME   = [Environment]::GetEnvironmentVariable("CF_ZONE_NAME",   "Machine")
$env:CF_RECORD_NAME = [Environment]::GetEnvironmentVariable("CF_RECORD_NAME", "Machine")
& $WebsiteVenv $DdnsScript
if ($LASTEXITCODE -ne 0) {
    Write-Error "DDNS script returned non-zero. Fix the error above before installing the task."
}

# Register scheduled task: every 5 minutes, run as SYSTEM so it works regardless of login state.
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Removing existing scheduled task '$TaskName'..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$action    = New-ScheduledTaskAction `
                -Execute $WebsiteVenv `
                -Argument "`"$DdnsScript`"" `
                -WorkingDirectory (Split-Path $DdnsScript)
$trigger   = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask `
    -TaskName    $TaskName `
    -Action      $action `
    -Trigger     $trigger `
    -Principal   $principal `
    -Settings    $settings `
    -Description "Updates Cloudflare DNS A record with current public IP for $($env:CF_RECORD_NAME)" | Out-Null

Write-Host "`nScheduled task '$TaskName' installed (runs every 5 min as SYSTEM)."
Write-Host "Inspect:  Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo"
Write-Host "Run now:  Start-ScheduledTask -TaskName $TaskName"
