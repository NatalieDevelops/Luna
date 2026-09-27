#!/usr/bin/env python3
"""
calibrate_sensefur.py
=====================
Collect baseline pressure readings from SenseFur v2 and save to binary file.
Run before first boot and after skin reassembly.

Usage:
    python3 scripts/calibrate_sensefur.py --output config/sensefur_cal.bin
    python3 scripts/calibrate_sensefur.py --output config/sensefur_cal.bin --samples 1000
"""

import argparse
import sys
import time

import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--samples", type=int, default=500)
    parser.add_argument("--i2c-bus", type=int, default=1)
    parser.add_argument("--i2c-addr", type=lambda x: int(x, 0), default=0x48)
    parser.add_argument("--simulate", action="store_true",
                        help="Run without hardware (produces near-zero baseline)")
    args = parser.parse_args()

    from ruby.tactile.sensefur import SenseFurArray, SenseFurCalibrator
    arr = SenseFurArray(
        i2c_bus=args.i2c_bus,
        i2c_address=args.i2c_addr,
        sample_rate_hz=100,
        calibration_file="/dev/null",
    )
    if args.simulate:
        arr._bus = None

    arr._load_calibration()
    arr._open_i2c()

    cal = SenseFurCalibrator(arr, samples=args.samples)
    cal.run(args.output)


if __name__ == "__main__":
    main()
