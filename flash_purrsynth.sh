#!/usr/bin/env bash
# flash_purrsynth.sh -- Flash PurrSynth v2.1 audio chip firmware
set -euo pipefail

PORT="/dev/ttyUSB1"
FIRMWARE="firmware/purrsynth_v2.1.bin"

while [[ $# -gt 0 ]]; do
  case $1 in
    --port) PORT="$2"; shift 2 ;;
    *) echo "Usage: $0 --port <port>"; exit 1 ;;
  esac
done

echo "[flash_purrsynth] Port: $PORT"
echo "[flash_purrsynth] Flashing..."
avrdude -p attiny84 -c usbasp -P "$PORT" -U "flash:w:$FIRMWARE:r"
echo "[flash_purrsynth] Done."
