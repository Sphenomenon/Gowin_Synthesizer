#!/usr/bin/env python3
"""Decode B138 model-request trace from diagnostic UserCode 0x67."""
import argparse
import re
import time

import serial

REPORT = re.compile(rb'B138 ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8})')
NAMES = ('bp_req', 'bp_ready', 'cdc_valid', 'cdc_ready', 'ddr_req',
         'ddr_ready', 'rsp', 'rsp_fifo', 'mem_reset', 'calibrated')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', default='/dev/ttyUSB1')
    parser.add_argument('--seconds', type=float, default=60)
    args = parser.parse_args()
    start = time.monotonic()
    previous = None
    with serial.Serial(args.port, 115200, timeout=0.5, exclusive=True) as port:
        while time.monotonic() - start < args.seconds:
            match = REPORT.search(port.readline())
            if not match:
                continue
            _, tf, _, sd = (int(match.group(i), 16) for i in range(1, 5))
            model = (sd >> 2) & 15
            trace = (tf >> 6) & 0x3ff
            if (model, trace) == previous:
                continue
            previous = (model, trace)
            fields = ' '.join(f'{name}={(trace >> (9-i)) & 1}'
                              for i, name in enumerate(NAMES))
            print(f'{time.monotonic()-start:.1f}s model={model:X} '
                  f'trace={trace:03X} {fields} {match.group(0).decode()}',
                  flush=True)


if __name__ == '__main__':
    main()
