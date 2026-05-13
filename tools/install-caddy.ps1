# Installs Caddy as a Windows service in front of the pool-temp website.
# Run from an elevated PowerShell.

#requires -RunAsAdministrator

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
$Caddyfile   = Join-Path $ProjectRoot "caddy\Caddyfile"
$ServiceName = "PoolTempCaddy"
$DataDir     = "C:\ProgramData\Caddy"

if (-not (Test-Path $Caddyfile)) {
    Write-Error "Caddyfile not found at $Caddyfile"
}

# 1. Install Caddy via winget if not already on PATH.
$caddyCmd = Get-Command caddy -ErrorAction SilentlyContinue
if (-not $caddyCmd) {
    Write-Host "Installing Caddy via winget..."
    winget install --id CaddyServer.Caddy --silent --accept-package-agreements --accept-source-agreements
    $env:Path += ";$env:LOCALAPPDATA\Microsoft\WinGet\Links;C:\Program Files\Caddy"
    $caddyCmd = Get-Command caddy -ErrorAction SilentlyContinue
    if (-not $caddyCmd) {
        # Fallback: search common install locations.
        $guess = @(
            "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\CaddyServer.Caddy_*\caddy.exe",
            "C:\Program Files\Caddy\caddy.exe"
        ) | ForEach-Object { Get-ChildItem $_ -ErrorAction SilentlyContinue } | Select-Object -First 1
        if ($guess) {
            $caddyCmd = [pscustomobject]@{ Source = $guess.FullName }
        } else {
            Write-Error "caddy.exe not found after install. Open a new terminal or install manually from https://caddyserver.com/download."
        }
    }
}
Write-Host "Caddy: $($caddyCmd.Source)"

# 2. Validate the Caddyfile.
& $caddyCmd.Source validate --config $Caddyfile --adapter caddyfile
if ($LASTEXITCODE -ne 0) {
    Write-Error "Caddyfile validation failed."
}

# 3. Ensure NSSM is installed (the website installer puts it there; if not, install).
$nssmCmd = Get-Command nssm -ErrorAction SilentlyContinue
if (-not $nssmCmd) {
    Write-Host "Installing NSSM via winget..."
    winget install --id NSSM.NSSM --silent --accept-package-agreements --accept-source-agreements
    $env:Path += ";$env:LOCALAPPDATA\Microsoft\WinGet\Links"
    $nssmCmd = Get-Command nssm -ErrorAction SilentlyContinue
    if (-not $nssmCmd) { Write-Error "NSSM still missing. Install manually." }
}

# 4. Open Windows Firewall for 80/443.
foreach ($port in 80, 443) {
    $ruleName = "PoolTempCaddy-$port"
    if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $port -Profile Any | Out-Null
        Write-Host "Opened firewall: TCP $port"
    }
}

# 5. Make sure data dir exists (Caddy stores certs/state there).
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null

# 6. Re-install service idempotently.
$existing = Get-Service $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Removing existing service '$ServiceName'..."
    & nssm stop   $ServiceName confirm | Out-Null
    & nssm remove $ServiceName confirm | Out-Null
}

Write-Host "Installing service '$ServiceName'..."
& nssm install $ServiceName $caddyCmd.Source "run" "--config" "`"$Caddyfile`"" "--adapter" "caddyfile"
& nssm set $ServiceName AppDirectory (Split-Path $Caddyfile)
& nssm set $ServiceName AppEnvironmentExtra "HOME=$DataDir" "USERPROFILE=$DataDir" "XDG_DATA_HOME=$DataDir" "XDG_CONFIG_HOME=$DataDir"
& nssm set $ServiceName Description "Caddy reverse proxy + Let's Encrypt for the pool-temp website"
& nssm set $ServiceName Start SERVICE_AUTO_START
& nssm set $ServiceName AppStdout (Join-Path $DataDir "caddy.out.log")
& nssm set $ServiceName AppStderr (Join-Path $DataDir "caddy.err.log")
& nssm set $ServiceName AppRotateFiles 1
& nssm set $ServiceName AppRotateBytes 10485760
& nssm set $ServiceName AppThrottle 5000
& nssm set $ServiceName AppExit Default Restart

& nssm start $ServiceName

Start-Sleep -Seconds 3
Get-Service $ServiceName | Format-Table Name, Status, StartType

Write-Host ""
Write-Host "Caddy service installed. Now in UniFi:"
Write-Host "  1. DELETE the existing 'pool-temp-http' rule (80 -> 192.168.1.81:18080)"
Write-Host "  2. CREATE: WAN  80 -> 192.168.1.81:80   (Caddy HTTP, redirects to HTTPS)"
Write-Host "  3. CREATE: WAN 443 -> 192.168.1.81:443  (Caddy HTTPS)"
Write-Host ""
Write-Host "Then visit https://temp.kyro-labs.com -- Caddy will fetch the cert on first hit."
Write-Host "Cert state lives at $DataDir.  Logs: $DataDir\caddy.*.log"
