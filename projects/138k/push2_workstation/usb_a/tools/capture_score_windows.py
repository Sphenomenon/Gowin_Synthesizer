#!/usr/bin/env python3
"""Watch successive CNN windows and cumulative score on the B138 UART line."""
import argparse
import re
import time

import serial


REPORT = re.compile(rb'B138 ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8})')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', default='/dev/ttyUSB1')
    parser.add_argument('--seconds', type=float, default=1200)
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
            result = (bp >> 4) & 1
            state = None if result or model in (12, 15) else (nn >> 26) & 63
            score = (sd >> 24) & 255
            status = (model, result, state, score, (tf >> 2) & 1)
            if status == previous:
                continue
            previous = status
            print(f'{time.monotonic()-start:.1f}s model={model:X} '
                  f'pcm_ready={(tf >> 1) & 1} result={result} '
                  f'state={state} score={score} wav_ready={status[4]} '
                  f'{match.group(0).decode()}', flush=True)


if __name__ == '__main__':
    main()
