# Flash firmware - MANUAL DANCE MODE.
# esptool does NOT reset the chip. Chip must already be in download mode before running:
#   1. Hold BOOT (or IO0)
#   2. Tap EN (or RST), release
#   3. Release BOOT
#   4. Run this script within ~10s
# Uses platformio.ini's upload_flags = --before=no_reset
$pio = "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe"
$projectDir = Split-Path $PSScriptRoot -Parent
& $pio run -d $projectDir --target upload --upload-port COM3
