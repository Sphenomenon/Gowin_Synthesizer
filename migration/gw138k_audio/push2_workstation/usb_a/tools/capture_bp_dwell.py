#!/usr/bin/env python3
"""Capture the CNN per-state dwell telemetry carried by the B138 NN word.

0x81 telemetry format (analysis mode, model_status E, result_valid 0):

    NN word = {debug_progress[15:0], dwell[15:0]}
      debug_progress: FSM state = (nn >> 26) & 0x3f  (unchanged decode)
      dwell[15:14] = page, dwell[13:0] = cycles[24:11]

The pipeline buckets its FSM states into eight dwell counters (25-bit cycle
counts).  A 25M-cycle divider (0.5 s at 50 MHz, matched to the report tick)
latches the just-finished window totals and advances the page, so each B138
report shows one page's cycles-per-0.5 s at 2048-cycle (40.96 us) resolution.

Buckets: 0 CQT, 1 NORM+plane cache, 2 CONTOUR, 3 REDUCE+NOTES,
4 NOTE_OUT+ONSET, 5 ONSET_OUT+stream glue, 6 DP/Viterbi, 7 other.

Also tracks stream_wave (frame counter, bp[28:20]) for the frame rate and
score_count (sd[31:24]) for window completions.
"""
import argparse
import re
import time
from collections import defaultdict

REPORT = re.compile(rb"B138 ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8})")

PAGE_NAMES = ["CQT", "NORM", "CONTOUR", "REDUCE+NOTES",
              "NOTE_OUT+ONSET", "ONSET_OUT+GLUE", "DP", "OTHER"]
UNIT_CYCLES = 2048
WINDOW_SECONDS = 0.5


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/ttyUSB1")
    parser.add_argument("--seconds", type=float, default=180)
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    dwell_samples = defaultdict(list)
    frame_trace = []          # (time, stream_wave)
    resets = []               # window boundary times
    last_wave = None
    score_steps = []
    last_score = None
    began = None
    bad_status = 0

    log = open(args.label and f"dwell_{args.label}.log" or "dwell.log", "w")

    def emit(line):
        print(line, flush=True)
        log.write(line + "\n")
        log.flush()

    try:
        with __import__("serial").Serial(args.port, 115200, timeout=0.5) as port:
            emit(f"# capture begin {time.strftime('%F %T')} label={args.label!r}")
            while True:
                raw = port.readline()
                if began is None:
                    began = time.monotonic()
                if time.monotonic() - began > args.seconds:
                    break
                match = REPORT.search(raw)
                if not match:
                    continue
                bp, tf, nn, sd = (int(match.group(i), 16) for i in range(1, 5))
                elapsed = time.monotonic() - began
                status = (sd >> 2) & 15
                wave = (bp >> 20) & 0x1FF
                result_valid = (bp >> 4) & 1
                score = (sd >> 24) & 0xFF
                if status != 14:
                    bad_status += 1
                    emit(f"{elapsed:7.1f}s status={status:X} raw={match.group(0).decode()}")
                    continue
                log.write(f"{elapsed:7.1f}s bp={bp:08X} tf={tf:08X} nn={nn:08X} sd={sd:08X}\n")
                if last_wave is not None and wave < last_wave:
                    resets.append(elapsed)
                    emit(f"{elapsed:7.1f}s -- window restart (wave {last_wave}->{wave})")
                if last_score is not None and score != last_score:
                    score_steps.append((elapsed, score))
                    emit(f"{elapsed:7.1f}s == score_count {last_score}->{score}")
                last_wave, last_score = wave, score
                frame_trace.append((elapsed, wave))
                if not result_valid:
                    page = (nn >> 14) & 3
                    units = nn & 0x3FFF
                    dwell_samples[page].append((elapsed, units))
                    state = (nn >> 26) & 0x3F
                    emit(f"{elapsed:7.1f}s wave={wave:3d} state={state:2d} "
                         f"page={page} dwell={units * UNIT_CYCLES / 50e6 * 1000:6.1f}ms")
                else:
                    emit(f"{elapsed:7.1f}s wave={wave:3d} result_valid=1 "
                         f"(hash page {(nn & 7)}, dwell occluded)")
    finally:
        log.close()

    # ---- frame rate from the stream_wave slope between restarts ----
    emit("\n==== frame rate ====")
    if len(frame_trace) > 2:
        segments = []
        start = 0
        for i in range(1, len(frame_trace)):
            if frame_trace[i][1] < frame_trace[i - 1][1]:
                segments.append((start, i))
                start = i
        segments.append((start, len(frame_trace)))
        for a, b in segments:
            t0, w0 = frame_trace[a]
            t1, w1 = frame_trace[b - 1]
            if t1 - t0 >= 2 and w1 > w0:
                emit(f"  segment {t0:7.1f}s..{t1:7.1f}s  frames {w0}->{w1}  "
                     f"rate={(w1 - w0) / (t1 - t0):.3f} frames/s  "
                     f"({(t1 - t0) / (w1 - w0):.2f} s/frame)")
    emit(f"  window restarts at: {[f'{t:.1f}s' for t in resets]}")
    emit(f"  score steps: {[(f'{t:.1f}s', n) for t, n in score_steps]}")

    # ---- dwell aggregation ----
    emit("\n==== per-state dwell (mean ms per 0.5 s window) ====")
    total_ms = 0.0
    means = {}
    for page in range(8):
        samples = [u for _, u in dwell_samples.get(page, [])]
        if samples:
            mean_units = sum(samples) / len(samples)
            mean_ms = mean_units * UNIT_CYCLES / 50e6 * 1000
            means[page] = mean_ms
            total_ms += mean_ms
    for page in range(8):
        if page in means:
            share = 100.0 * means[page] / total_ms if total_ms else 0
            emit(f"  page {page} {PAGE_NAMES[page]:<16} {means[page]:7.1f} ms  "
                 f"{share:5.1f} %  (n={len(dwell_samples[page])})")
        else:
            emit(f"  page {page} {PAGE_NAMES[page]:<16} (no samples)")
    emit(f"  summed mean {total_ms:.1f} ms (expect ~500 ms if capture is clean)")
    if bad_status:
        emit(f"  ({bad_status} reports skipped for model_status != E)")


if __name__ == "__main__":
    main()
