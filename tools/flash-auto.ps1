# Flash firmware - ESPTOOL AUTO-RESET MODE.
# Bypasses platformio.ini and calls esptool directly, letting it drive DTR/RTS
# to reset the chip into download mode automatically. Works on boards with
# proper auto-bootloader wiring. Just run it cold - no button-pressing needed.
$python     = "$env:USERPROFILE\.platformio\penv\Scripts\python.exe"
$esptool    = "$env:USERPROFILE\.platformio\packages\tool-esptoolpy\esptool.py"
$projectDir = Split-Path $PSScriptRoot -Parent
$bin        = Join-Path $projectDir ".pio\build\esp32dev\firmware.bin"
if (-not (Test-Path $bin)) {
    Write-Host "firmware.bin not found at $bin - run a build first (.\tools\flash.ps1 builds automatically)"
    exit 1
}
& $python $esptool --port COM3 --before default_reset --after hard_reset write_flash -z 0x1000 $bin
