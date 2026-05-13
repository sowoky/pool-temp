# Probe COM3 for an ESP32 - reads chip ID. Sanity test for cable/port/boot mode.
# If this can't connect, no flash command will either.
$python  = "$env:USERPROFILE\.platformio\penv\Scripts\python.exe"
$esptool = "$env:USERPROFILE\.platformio\packages\tool-esptoolpy\esptool.py"
& $python $esptool --port COM3 chip_id
