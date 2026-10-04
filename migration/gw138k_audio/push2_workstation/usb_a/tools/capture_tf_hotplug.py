#!/usr/bin/env python3
"""Record 0x62 TF hotplug state transitions from the B138 UART report."""
import argparse
import re
import time

import serial

REPORT = re.compile(rb"B138 ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/ttyUSB1")
    parser.add_argument("--seconds", type=float, default=120)
    args = parser.parse_args()
    start = time.monotonic()
    previous = None
    with serial.Serial(args.port, 115200, timeout=0.5, exclusive=True) as port:
        while time.monotonic() - start < args.seconds:
            match = REPORT.search(port.readline())
            if not match:
                continue
            bp, tf, nn, sd = (int(match.group(i), 16) for i in range(1, 5))
            model = (sd >> 2) & 15
            trace = (tf >> 5) & 0x7ff
            status = (
                model, tf >> 16, (trace >> 8) & 7,
                (trace >> 4) & 15, (trace >> 3) & 1,
                (trace >> 2) & 1, (trace >> 1) & 1, trace & 1,
                (tf >> 2) & 1,
            )
            if status == previous:
                continue
            print(
                f"{time.monotonic()-start:.1f}s "
                f"model={model:X} rate={status[1]} fs={status[2]} card={status[3]} "
                f"sector_busy={status[4]} sector_allow={status[5]} "
                f"scan_done={status[6]} lost_seen={status[7]} "
                f"wav_ready={status[8]} raw={match.group(0).decode()}",
                flush=True,
            )
            previous = status


if __name__ == "__main__":
    main()
