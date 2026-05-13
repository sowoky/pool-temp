# Open serial monitor on COM3 @ 115200. Ctrl+C to exit.
# Tip: close this window before re-flashing - it holds COM3 open.
$pio = "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe"
$projectDir = Split-Path $PSScriptRoot -Parent
& $pio device monitor -d $projectDir -p COM3 -b 115200
