#!/usr/bin/env python3
"""Record and check the integrated workstation Basic Pitch UART result."""
import argparse
import re
import time

import serial


EXPECTED = [0xD1FFF498, 0xC603CCE8, 0x1E39D540,
            0x56F7DA28, 0xD5816B28, 0xCF7EF3A8]
REPORT = re.compile(rb"B138 ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/ttyUSB1")
    parser.add_argument("--timeout", type=float, default=1000)
    args = parser.parse_args()
    found = {}
    began = time.monotonic()
    with serial.Serial(args.port, 115200, timeout=0.5) as port:
        while time.monotonic() - began < args.timeout:
            raw = port.readline()
            match = REPORT.search(raw)
            if not match:
                continue
            bp, tf, nn, sd = (int(match.group(i), 16) for i in range(1, 5))
            elapsed = time.monotonic() - began
            status = (sd >> 2) & 15
            if status != 14:
                print(f"{elapsed:.1f}s model_status={status:X} {match.group(0).decode()}", flush=True)
                continue
            if bp & 0x10:
                page = nn & 7
                if page < 6:
                    observed = nn & 0xFFFF_FFF8
                    expected = EXPECTED[page] & 0xFFFF_FFF8
                    found[page] = observed
                    print(f"{elapsed:.1f}s page={page} hash_hi29={observed:08X} "
                          f"expected={expected:08X} bp={bp:08X} tf={tf:08X}", flush=True)
                    if observed != expected:
                        raise SystemExit(f"FAIL layer {page} hash")
                if len(found) == 6:
                    if bp != 0x0022131F:
                        raise SystemExit(f"FAIL final result {bp:08X}")
                    print(f"PASS 6/6 layer hash high bits, MIDI 24 frame 2, "
                          f"model E, elapsed={elapsed:.1f}s", flush=True)
                    return
            elif int(elapsed) % 30 == 0:
                print(f"{elapsed:.1f}s bp={bp:08X} tf={tf:08X} "
                      f"progress={nn >> 16:04X}", flush=True)
    raise SystemExit(f"TIMEOUT {len(found)}/6 layer hashes")


if __name__ == "__main__":
    main()
