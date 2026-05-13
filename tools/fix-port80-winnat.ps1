$Log = "C:\Users\kyler\workspace\pool-temp\website\fix-port80-winnat.log"
"--- elevated: $([Security.Principal.WindowsIdentity]::GetCurrent().Name) ---" | Out-File $Log -Encoding utf8

function Add-Log { param($Msg) $Msg | Add-Content $Log }
function Test-Bind {
    & "C:\Users\kyler\workspace\pool-temp\website\.venv\Scripts\python.exe" -c "import socket; s=socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.bind(('0.0.0.0', 80)); print('SUCCESS'); s.close()" 2>&1
}

try {
    Add-Log "--- state before ---"
    Add-Log "winnat: $((Get-Service winnat -ErrorAction SilentlyContinue).Status)"
    Add-Log "vmcompute: $((Get-Service vmcompute -ErrorAction SilentlyContinue).Status)"
    Add-Log "Docker Desktop Service: $((Get-Service 'com.docker.service' -ErrorAction SilentlyContinue).Status)"
    Add-Log "WSL distros running:"
    (wsl --list --running 2>&1) | Add-Content $Log

    Add-Log "--- current excluded port ranges ---"
    (netsh int ipv4 show excludedportrange protocol=tcp 2>&1) | Add-Content $Log

    Add-Log "--- bind test (before fix) ---"
    (Test-Bind) | Add-Content $Log

    Add-Log "--- stopping winnat (releases dynamic reservations) ---"
    (net stop winnat 2>&1) | Add-Content $Log

    Add-Log "--- adding port 80 to excluded range so winnat won't reclaim it ---"
    (netsh int ipv4 add excludedportrange protocol=tcp startport=80 numberofports=1 2>&1) | Add-Content $Log

    Add-Log "--- starting winnat ---"
    (net start winnat 2>&1) | Add-Content $Log

    Add-Log "--- bind test (after fix) ---"
    (Test-Bind) | Add-Content $Log

    Add-Log "--- starting PoolTempCaddy ---"
    Stop-Service PoolTempCaddy -Force -ErrorAction SilentlyContinue
    Start-Sleep 2
    try {
        Start-Service PoolTempCaddy -ErrorAction Stop
        Start-Sleep 6
        Add-Log "service start OK"
    } catch {
        Add-Log "service start FAILED: $_"
    }

    Add-Log "--- service state ---"
    Get-Service PoolTempCaddy | Format-Table Name, Status, StartType -AutoSize | Out-String | Add-Content $Log

    Add-Log "--- listeners on 80/443 ---"
    Get-NetTCPConnection -State Listen -LocalPort 80,443 -ErrorAction SilentlyContinue |
        Select-Object LocalAddress, LocalPort, OwningProcess |
        Format-Table -AutoSize | Out-String | Add-Content $Log

    Add-Log "--- caddy.err.log tail ---"
    Get-Content C:\ProgramData\Caddy\caddy.err.log -Tail 25 -ErrorAction SilentlyContinue | Add-Content $Log
}
catch {
    Add-Log "EXCEPTION: $_"
}
