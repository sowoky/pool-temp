# Diagnose and free port 80 so Caddy can bind it.
# Writes a result log the parent shell can read back.

$Log = "C:\Users\kyler\workspace\pool-temp\website\fix-port80.log"
"--- elevated: $([Security.Principal.WindowsIdentity]::GetCurrent().Name) ---" | Out-File $Log -Encoding utf8

try {
    # 1. Show EVERYTHING listening on port 80 (admin sees more than non-admin).
    "--- all listeners on :80 (with full process info) ---" | Add-Content $Log
    Get-NetTCPConnection -State Listen -LocalPort 80 -ErrorAction SilentlyContinue | ForEach-Object {
        $proc = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
        $svc  = Get-CimInstance Win32_Service | Where-Object { $_.ProcessId -eq $_.OwningProcess }
        "$($_.LocalAddress):$($_.LocalPort)  PID=$($_.OwningProcess)  Name=$($proc.Name)  Path=$($proc.Path)"
    } | Add-Content $Log

    "--- ALL TCP state on port 80 ---" | Add-Content $Log
    Get-NetTCPConnection | Where-Object { $_.LocalPort -eq 80 } | ForEach-Object {
        "$($_.LocalAddress):$($_.LocalPort) -> $($_.RemoteAddress):$($_.RemotePort)  $($_.State)  PID=$($_.OwningProcess)"
    } | Add-Content $Log

    # 2. Show current URL ACLs touching :80.
    "--- netsh http show urlacl (full) ---" | Add-Content $Log
    netsh http show urlacl | Add-Content $Log

    # 3. Delete the Temporary_Listen_Addresses URL ACL on port 80.
    "--- deleting URL ACL http://+:80/Temporary_Listen_Addresses/ ---" | Add-Content $Log
    netsh http delete urlacl url='http://+:80/Temporary_Listen_Addresses/' | Add-Content $Log

    # 4. Try a Python bind test after the delete (still as SYSTEM/admin).
    "--- python bind 0.0.0.0:80 after URL ACL delete ---" | Add-Content $Log
    & "C:\Users\kyler\workspace\pool-temp\website\.venv\Scripts\python.exe" -c "import socket; s=socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.bind(('0.0.0.0', 80)); print('SUCCESS 0.0.0.0:80'); s.close()" 2>&1 | Add-Content $Log

    "--- python bind 127.0.0.1:80 ---" | Add-Content $Log
    & "C:\Users\kyler\workspace\pool-temp\website\.venv\Scripts\python.exe" -c "import socket; s=socket.socket(); s.bind(('127.0.0.1', 80)); print('SUCCESS 127.0.0.1:80'); s.close()" 2>&1 | Add-Content $Log

    # 5. Try restarting the Caddy service.
    "--- restarting PoolTempCaddy ---" | Add-Content $Log
    Stop-Service PoolTempCaddy -Force -ErrorAction SilentlyContinue
    Start-Sleep 2
    try {
        Start-Service PoolTempCaddy -ErrorAction Stop
        Start-Sleep 6
        "service start OK" | Add-Content $Log
    } catch {
        "service start FAILED: $_" | Add-Content $Log
    }

    "--- service state ---" | Add-Content $Log
    Get-Service PoolTempCaddy | Format-Table Name, Status, StartType -AutoSize | Out-String | Add-Content $Log

    "--- listeners on 80/443 ---" | Add-Content $Log
    Get-NetTCPConnection -State Listen -LocalPort 80,443 -ErrorAction SilentlyContinue |
        Select-Object LocalAddress, LocalPort, OwningProcess |
        Format-Table -AutoSize | Out-String | Add-Content $Log

    "--- caddy.err.log tail ---" | Add-Content $Log
    Get-Content C:\ProgramData\Caddy\caddy.err.log -Tail 30 -ErrorAction SilentlyContinue | Add-Content $Log
}
catch {
    "EXCEPTION: $_" | Add-Content $Log
}
