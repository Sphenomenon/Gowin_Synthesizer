#!/usr/bin/env python3
"""Measure PING/ACK round trips only; never trigger notes, apply patches or PANIC."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import sys
import time

from instrument_backend import SerialTransport


def measure(port: str, count: int = 100, backend: str = "auto", baud: int = 115200) -> dict:
    if not 1 <= count <= 10000:
        raise ValueError("count must be in 1..10000")
    transport = SerialTransport(port, baud, backend=backend)
    rows = []
    io_events = []
    original_write, original_read = transport.serial.write, transport.serial.read
    def measured_write(data):
        begin = time.perf_counter()
        result = original_write(data)
        io_events.append(("write", begin, time.perf_counter(), result))
        return result
    def measured_read(size):
        begin = time.perf_counter()
        result = original_read(size)
        io_events.append(("read", begin, time.perf_counter(), len(result)))
        return result
    transport.serial.write, transport.serial.read = measured_write, measured_read
    try:
        for _ in range(count):
            io_events.clear()
            started = time.perf_counter()
            ack = transport.command(0)
            completed = time.perf_counter()
            first_data = next((end for kind, begin, end, size in io_events if kind == "read" and size), None)
            rows.append({"sequence": ack.sequence, "rtt_ms": ack.rtt_ms,
                         "call_ms": (completed - started) * 1000,
                         "write_call_ms": sum(end-begin for kind, begin, end, size in io_events if kind == "write") * 1000,
                         "read_calls_ms": sum(end-begin for kind, begin, end, size in io_events if kind == "read") * 1000,
                         "first_nonempty_read_completed_ms": (first_data-started) * 1000 if first_data else None})
        profile = dict(transport.profile)
    finally:
        transport.close()
    values = sorted(row["rtt_ms"] for row in rows)
    return {"scope": "PING/ACK only; not keyboard-to-audio latency", "port": port, "baud": baud,
            "python": sys.version, "profile": profile, "count": count,
            "summary_ms": {"min": values[0], "median": statistics.median(values),
                           "p95": values[math.ceil(count * 0.95) - 1], "max": values[-1]},
            "rtt_over_10ms_count": sum(value > 10 for value in values), "samples": rows}


def measure_pipeline(port: str, count: int = 100, backend: str = "auto", baud: int = 115200,
                     interval_ms: float = 4.0) -> dict:
    """Synthetic PING arrivals through the production bounded transport API.

    Dispatch delay is measured from a scheduled local probe event, not a human
    key edge. No audio/patch opcodes or automatic retry are used.
    """
    if not 1 <= count <= 10000:
        raise ValueError("count must be in 1..10000")
    if not math.isfinite(interval_ms) or not 0.5 <= interval_ms <= 1000:
        raise ValueError("interval_ms must be in 0.5..1000")
    transport = SerialTransport(port, baud, backend=backend)
    rows, by_sequence = [], {}
    outstanding_max = 0
    try:
        transport.command(0)
        start = time.perf_counter()
        received = 0
        while received < count:
            for ack, timing in transport.poll_acks():
                row = by_sequence.pop(ack.sequence)
                if ack.status or ack.opcode != 0:
                    raise RuntimeError("unexpected PING ACK")
                row["rtt_ms"] = ack.rtt_ms
                row["ack_received_ms"] = (timing.ack_received - start) * 1000
                received += 1
            if len(rows) < count:
                scheduled = start + len(rows) * interval_ms / 1000
                if time.perf_counter() >= scheduled:
                    timing = transport.send_async(0)
                    if timing is not None:
                        row = {"index": len(rows), "sequence": timing.sequence,
                               "scheduled_ms": (scheduled - start) * 1000,
                               "write_started_ms": (timing.write_started - start) * 1000,
                               "dispatch_ms": (timing.write_started - scheduled) * 1000}
                        rows.append(row)
                        by_sequence[timing.sequence] = row
                        outstanding_max = max(outstanding_max, transport.pending_count)
            time.sleep(0.001)
        profile = dict(transport.profile)
    finally:
        transport.close()
    def summarize(values):
        values = sorted(values)
        return {"min": values[0], "median": statistics.median(values),
                "p95": values[math.ceil(len(values) * 0.95) - 1], "max": values[-1]}
    return {"scope": "Synthetic scheduled PING events, not keyboard or audio latency",
            "mode": "bounded_pipeline", "port": port, "baud": baud, "python": sys.version,
            "profile": profile, "count": count, "ack_count": received,
            "interval_ms": interval_ms, "outstanding_max": outstanding_max,
            "dispatch_summary_ms": summarize(row["dispatch_ms"] for row in rows),
            "rtt_summary_ms": summarize(row["rtt_ms"] for row in rows), "samples": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--serial-backend", choices=("auto", "ftdi", "pyserial"), default="auto")
    parser.add_argument("--pipeline", action="store_true", help="test bounded asynchronous PING dispatch")
    parser.add_argument("--interval-ms", type=float, default=4.0, help="synthetic PING arrival interval with --pipeline")
    parser.add_argument("--output", type=Path, help="save complete JSON evidence including each sample")
    args = parser.parse_args()
    try:
        if args.pipeline:
            result = measure_pipeline(args.port, args.count, args.serial_backend, args.baud, args.interval_ms)
        else:
            result = measure(args.port, args.count, args.serial_backend, args.baud)
        if args.output:
            args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({key: value for key, value in result.items() if key != "samples"},
                         indent=2, ensure_ascii=False))
    except (OSError, RuntimeError, ValueError, TimeoutError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
