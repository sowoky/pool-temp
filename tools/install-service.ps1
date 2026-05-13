# Installs the pool-temp website as a Windows service via NSSM.
# Run from an elevated PowerShell:  Right-click -> Run with PowerShell as Admin
# Or:  Start-Process pwsh -Verb RunAs -ArgumentList "-File", ".\install-service.ps1"

#requires -RunAsAdministrator

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
$WebsiteDir  = Join-Path $ProjectRoot "website"
$VenvPython  = Join-Path $WebsiteDir ".venv\Scripts\python.exe"
$Waitress    = Join-Path $WebsiteDir ".venv\Scripts\waitress-serve.exe"
$ServiceName = "PoolTempWebsite"
$LogDir      = Join-Path $WebsiteDir "logs"

if (-not (Test-Path $Waitress)) {
    Write-Error "waitress-serve.exe not found at $Waitress. Run website\run.bat once to create the venv."
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# 1. Ensure NSSM is installed.
$nssmCmd = Get-Command nssm -ErrorAction SilentlyContinue
if (-not $nssmCmd) {
    Write-Host "Installing NSSM via winget..."
    winget install --id NSSM.NSSM --silent --accept-package-agreements --accept-source-agreements
    # winget user-scope installs end up under %LOCALAPPDATA%; refresh PATH for this session
    $env:Path += ";$env:LOCALAPPDATA\Microsoft\WinGet\Links"
    $nssmCmd = Get-Command nssm -ErrorAction SilentlyContinue
    if (-not $nssmCmd) {
        Write-Error "NSSM still not on PATH after winget install. Open a new terminal and re-run, or install manually from https://nssm.cc."
    }
}
Write-Host "NSSM: $($nssmCmd.Source)"

# 2. Stop any dev Flask process lurking on 18080.
$existingListener = Get-NetTCPConnection -State Listen -LocalPort 18080 -ErrorAction SilentlyContinue
foreach ($conn in $existingListener) {
    $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
    if ($proc -and $proc.ProcessName -eq "python" -and $proc.Path -like "*\website\.venv\Scripts\python.exe") {
        Write-Host "Stopping existing dev server PID=$($proc.Id)"
        Stop-Process -Id $proc.Id -Force
    }
}

# 3. Remove any prior version of the service so install is idempotent.
$existingSvc = Get-Service $ServiceName -ErrorAction SilentlyContinue
if ($existingSvc) {
    Write-Host "Removing existing service '$ServiceName'..."
    & nssm stop   $ServiceName confirm | Out-Null
    & nssm remove $ServiceName confirm | Out-Null
}

# 4. Install fresh.
Write-Host "Installing service '$ServiceName'..."
& nssm install $ServiceName $Waitress "--listen=0.0.0.0:18080" "app:app"
& nssm set $ServiceName AppDirectory $WebsiteDir
& nssm set $ServiceName AppEnvironmentExtra "POOL_API_KEY=dev-key"
& nssm set $ServiceName Description "Pool temperature monitor website (Flask via Waitress)"
& nssm set $ServiceName Start SERVICE_AUTO_START
& nssm set $ServiceName AppStdout (Join-Path $LogDir "service.out.log")
& nssm set $ServiceName AppStderr (Join-Path $LogDir "service.err.log")
& nssm set $ServiceName AppRotateFiles 1
& nssm set $ServiceName AppRotateBytes 10485760     # 10 MB
& nssm set $ServiceName AppStopMethodSkip 0
& nssm set $ServiceName AppThrottle 5000             # ms between restarts
& nssm set $ServiceName AppExit Default Restart

# 5. Start.
Write-Host "Starting service..."
& nssm start $ServiceName

Start-Sleep -Seconds 2
Get-Service $ServiceName | Format-Table Name, Status, StartType
Write-Host ""
Write-Host "Service installed. URLs:"
Write-Host "  http://localhost:18080/"
Write-Host "  http://192.168.1.81:18080/   (LAN)"
Write-Host ""
Write-Host "Manage:  Get-Service $ServiceName | Restart-Service"
Write-Host "Logs:    $LogDir"
