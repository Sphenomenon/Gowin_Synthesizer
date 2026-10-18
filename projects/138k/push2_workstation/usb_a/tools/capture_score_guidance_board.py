#!/usr/bin/env python3
"""Capture the completed TF→CNN→score run without hiding CNN hash mismatches."""
import argparse
import re
import time

import serial

REPORT = re.compile(rb"B138 ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8})")
EXPECTED = [0xD1FFF498, 0xC603CCE8, 0x1E39D540,
            0x56F7DA28, 0xD5816B28, 0xCF7EF3A8]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', default='/dev/ttyUSB1')
    parser.add_argument('--timeout', type=float, default=900)
    args = parser.parse_args()
    begun = time.monotonic()
    last_progress = -30
    hashes = {}
    with serial.Serial(args.port, 115200, timeout=0.5, exclusive=True) as port:
        while time.monotonic() - begun < args.timeout:
            match = REPORT.search(port.readline())
            if not match:
                continue
            bp, tf, nn, sd = (int(match.group(i), 16) for i in range(1, 5))
            elapsed = time.monotonic() - begun
            score_count, first, last = (sd >> 24) & 255, (sd >> 17) & 127, (sd >> 10) & 127
            status = (sd >> 2) & 15
            if elapsed - last_progress >= 30:
                print(f'{elapsed:.1f}s bp={bp:08X} tf={tf:08X} progress={nn>>16:04X} '
                      f'model={status:X} score_count={score_count}', flush=True)
                last_progress = elapsed
            if bp & 0x10 and status == 14:
                page = nn & 7
                if page < 6:
                    observed = nn & 0xfffffff8
                    if page not in hashes:
                        hashes[page] = observed
                        print(f'{elapsed:.1f}s page={page} hash_hi29={observed:08X} '
                              f'expected={EXPECTED[page]&0xfffffff8:08X} '
                              f'score_count={score_count} first={first} last={last}', flush=True)
                if len(hashes) == 6 and score_count:
                    result_note = (bp >> 5) & 127
                    target = result_note + 24 if result_note < 24 else (
                        result_note + 12 if result_note < 36 else (
                            result_note - 12 if result_note > 99 else result_note))
                    aligned = first == target
                    print(f'RESULT bp={bp:08X} tf={tf:08X} score_count={score_count} '
                          f'first={first} last={last} committed_midi={result_note} '
                          f'push_target={target} frame={(bp>>20)&4095} aligned={aligned} '
                          f'hashes={",".join(f"{hashes[i]:08X}" for i in range(6))}', flush=True)
                    if not aligned:
                        raise SystemExit('FAIL first guide target disagrees with committed note')
                    return
    raise SystemExit(f'TIMEOUT score_count={score_count} hashes={len(hashes)}/6')


if __name__ == '__main__':
    main()
