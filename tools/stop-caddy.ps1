# Stops the Caddy service so it's not holding ports 80/443.
$Log = "C:\Users\kyler\workspace\pool-temp\website\stop-caddy.log"
"--- elevated: $([Security.Principal.WindowsIdentity]::GetCurrent().Name) ---" | Out-File $Log -Encoding utf8
try {
    Stop-Service PoolTempCaddy -Force -ErrorAction SilentlyContinue
    Set-Service PoolTempCaddy -StartupType Manual -ErrorAction SilentlyContinue
    Start-Sleep 2
    Get-Service PoolTempCaddy | Format-Table Name, Status, StartType -AutoSize | Out-String | Add-Content $Log
    "--- listeners on 80/443 after stop ---" | Add-Content $Log
    Get-NetTCPConnection -State Listen -LocalPort 80,443 -ErrorAction SilentlyContinue |
        Select-Object LocalAddress, LocalPort, OwningProcess | Format-Table -AutoSize | Out-String | Add-Content $Log
} catch { "EXCEPTION: $_" | Add-Content $Log }
