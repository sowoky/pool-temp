# One-shot: stops PoolTempCaddy cleanly, kills any orphan caddy.exe,
# clears the err log, restarts the service, and writes a status dump to
# a log file the parent shell can read back.

$LogFile = "C:\Users\kyler\workspace\pool-temp\website\caddy-unstick.log"

"--- running as $([Security.Principal.WindowsIdentity]::GetCurrent().Name) ---" | Out-File $LogFile -Encoding utf8

try {
    "--- stopping service ---" | Add-Content $LogFile
    Stop-Service PoolTempCaddy -Force -ErrorAction SilentlyContinue | Out-Null
    Get-Process caddy -ErrorAction SilentlyContinue | ForEach-Object {
        "killing stray caddy.exe PID=$($_.Id)" | Add-Content $LogFile
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }

    "--- truncating err log ---" | Add-Content $LogFile
    Clear-Content 'C:\ProgramData\Caddy\caddy.err.log' -ErrorAction SilentlyContinue
    Clear-Content 'C:\ProgramData\Caddy\caddy.out.log' -ErrorAction SilentlyContinue

    "--- starting service ---" | Add-Content $LogFile
    Start-Service PoolTempCaddy -ErrorAction Stop
    Start-Sleep -Seconds 6

    "--- SERVICE STATE ---" | Add-Content $LogFile
    Get-Service PoolTempCaddy | Format-Table Name, Status, StartType -AutoSize | Out-String | Add-Content $LogFile

    "--- LISTENERS (80/443/2019/18080) ---" | Add-Content $LogFile
    Get-NetTCPConnection -State Listen -LocalPort 80,443,2019,18080 -ErrorAction SilentlyContinue |
        Select-Object LocalAddress, LocalPort, OwningProcess |
        Sort-Object LocalPort |
        Format-Table -AutoSize | Out-String | Add-Content $LogFile

    "--- ERR LOG (tail) ---" | Add-Content $LogFile
    Get-Content 'C:\ProgramData\Caddy\caddy.err.log' -Tail 50 -ErrorAction SilentlyContinue | Add-Content $LogFile
}
catch {
    "ERROR: $_" | Add-Content $LogFile
}
