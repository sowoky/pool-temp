$Log = "C:\Users\kyler\workspace\pool-temp\website\kick-caddy.log"
"--- elevated: $([Security.Principal.WindowsIdentity]::GetCurrent().Name) ---" | Out-File $Log -Encoding utf8

try {
    Clear-Content C:\ProgramData\Caddy\caddy.err.log -ErrorAction SilentlyContinue
    Stop-Service PoolTempCaddy -Force -ErrorAction SilentlyContinue
    Start-Sleep 2
    Start-Service PoolTempCaddy
    Start-Sleep 8

    "--- service ---" | Add-Content $Log
    Get-Service PoolTempCaddy | Format-Table Name, Status, StartType -AutoSize | Out-String | Add-Content $Log

    "--- listeners 80/443 ---" | Add-Content $Log
    Get-NetTCPConnection -State Listen -LocalPort 80,443 -ErrorAction SilentlyContinue |
        Select-Object LocalAddress, LocalPort, OwningProcess |
        Format-Table -AutoSize | Out-String | Add-Content $Log

    "--- caddy.err.log tail ---" | Add-Content $Log
    Get-Content C:\ProgramData\Caddy\caddy.err.log -Tail 40 -ErrorAction SilentlyContinue | Add-Content $Log
}
catch { "EXCEPTION: $_" | Add-Content $Log }
