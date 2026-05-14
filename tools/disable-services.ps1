# One-time cleanup for the pool-temp project's local server/Caddy footprint.
# Stops the PoolTempCaddy reverse-proxy service, disables it from autostart,
# and removes the firewall rules that exposed 80/443. Reversible: service
# definition stays, ProgramData\Caddy (cached cert + ACME account) stays.
#
# Run from an elevated PowerShell. Writes a result log to website\disable-services.log
# so the result can be inspected without elevation.

#requires -RunAsAdministrator

$ErrorActionPreference = "Continue"

$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
$Log         = Join-Path $ProjectRoot "website\disable-services.log"
New-Item -ItemType Directory -Force -Path (Split-Path $Log) | Out-Null

"--- elevated as: $([Security.Principal.WindowsIdentity]::GetCurrent().Name) ---" | Out-File $Log -Encoding utf8

function Log { param([string]$msg) $msg | Add-Content $Log }

# 1. PoolTempCaddy: stop + disable autostart.
$svc = Get-Service PoolTempCaddy -ErrorAction SilentlyContinue
if ($svc) {
    Log ""
    Log "--- PoolTempCaddy (before) ---"
    $svc | Format-Table Name, Status, StartType -AutoSize | Out-String | Add-Content $Log
    if ($svc.Status -eq 'Running') {
        Log "stopping PoolTempCaddy..."
        Stop-Service PoolTempCaddy -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
    Set-Service PoolTempCaddy -StartupType Disabled -ErrorAction SilentlyContinue
    Log "--- PoolTempCaddy (after) ---"
    Get-Service PoolTempCaddy | Format-Table Name, Status, StartType -AutoSize | Out-String | Add-Content $Log
} else {
    Log ""
    Log "--- PoolTempCaddy not installed; nothing to stop ---"
}

# 2. PoolTempWebsite: stop + disable if it exists.
$webSvc = Get-Service PoolTempWebsite -ErrorAction SilentlyContinue
if ($webSvc) {
    Log ""
    Log "--- PoolTempWebsite (before) ---"
    $webSvc | Format-Table Name, Status, StartType -AutoSize | Out-String | Add-Content $Log
    if ($webSvc.Status -eq 'Running') {
        Log "stopping PoolTempWebsite..."
        Stop-Service PoolTempWebsite -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
    Set-Service PoolTempWebsite -StartupType Disabled -ErrorAction SilentlyContinue
    Log "--- PoolTempWebsite (after) ---"
    Get-Service PoolTempWebsite | Format-Table Name, Status, StartType -AutoSize | Out-String | Add-Content $Log
} else {
    Log ""
    Log "--- PoolTempWebsite service not installed; nothing to stop ---"
    Log "    (the Flask dev server on :18080, if running, was started manually"
    Log "     and is not managed by a Windows service. Close that terminal/process"
    Log "     yourself if you want :18080 gone.)"
}

# 3. Remove firewall rules opened for Caddy.
Log ""
Log "--- firewall rules ---"
foreach ($name in 'PoolTempCaddy-80','PoolTempCaddy-443') {
    $r = Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue
    if ($r) {
        Remove-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue
        Log "removed: $name"
    } else {
        Log "absent:  $name"
    }
}

# 4. Optional scheduled task (Cloudflare DDNS) cleanup.
Log ""
Log "--- DDNS scheduled task ---"
$task = Get-ScheduledTask -TaskName 'PoolTempCloudflareDDNS' -ErrorAction SilentlyContinue
if ($task) {
    Unregister-ScheduledTask -TaskName 'PoolTempCloudflareDDNS' -Confirm:$false -ErrorAction SilentlyContinue
    Log "unregistered: PoolTempCloudflareDDNS"
} else {
    Log "absent: PoolTempCloudflareDDNS"
}

# 5. Final listener check on 80/443.
Log ""
Log "--- listeners on 80/443 (should be empty) ---"
Get-NetTCPConnection -State Listen -LocalPort 80,443 -ErrorAction SilentlyContinue |
    Select-Object LocalAddress, LocalPort, OwningProcess |
    Format-Table -AutoSize | Out-String | Add-Content $Log

Log ""
Log "--- done ---"
