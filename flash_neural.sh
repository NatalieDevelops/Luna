#!/usr/bin/env bash
# flash_neural.sh -- Flash OpenClaw firmware to the Claude Neural Unit v3
# Usage: ./scripts/flash_neural.sh --port /dev/ttyUSB0 [--verify] [--dry-run]
set -euo pipefail

PORT="/dev/ttyUSB0"
VERIFY=0
DRY_RUN=0
FIRMWARE="firmware/openclaw_neural_v0.9.2.bin"

usage() {
  echo "Usage: $0 --port <port> [--verify] [--dry-run]"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case $1 in
    --port)    PORT="$2"; shift 2 ;;
    --verify)  VERIFY=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    *)         usage ;;
  esac
done

if [[ ! -e "$PORT" ]]; then
  echo "ERROR: port $PORT not found. Is the neural unit connected?"
  exit 1
fi

if [[ ! -f "$FIRMWARE" ]]; then
  echo "ERROR: firmware binary not found at $FIRMWARE"
  exit 1
fi

echo "[flash_neural] Target port : $PORT"
echo "[flash_neural] Firmware    : $FIRMWARE"
echo "[flash_neural] Verify      : $VERIFY"

if [[ $DRY_RUN -eq 1 ]]; then
  echo "[flash_neural] DRY RUN -- no writes performed"
  exit 0
fi

echo "[flash_neural] Entering bootloader..."
python3 -c "
import serial, time
s = serial.Serial('$PORT', 115200, timeout=1)
s.write(b'BOOTLOADER\r\n')
time.sleep(0.5)
resp = s.read_all()
print('  bootloader response:', resp)
s.close()
"

echo "[flash_neural] Flashing with avrdude..."
avrdude -p m2560 -c arduino -P "$PORT" -b 115200 \
  -U "flash:w:$FIRMWARE:r" ${VERIFY:+-U "flash:v:$FIRMWARE:r"}

echo "[flash_neural] Done. Rebooting..."
python3 -c "
import serial, time
s = serial.Serial('$PORT', 115200, timeout=2)
s.write(b'REBOOT\r\n')
time.sleep(1.5)
s.write(b'PING\r\n')
resp = s.readline()
print('  PING response:', resp)
s.close()
"
echo "[flash_neural] Neural unit online."
