#!/usr/bin/env python3
"""Emit packets from production keyboard RTL, with independent host expectations.

This runner does not alter RTL, the synthesizer project, or either board.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]


def target_expectation(packet: bytes) -> tuple[int, int, int]:
    """Independent contract for the synthesizer's supported generic events."""
    cin, status, a, b = packet
    family = status >> 4
    if cin & 15 != family or a > 127 or b > 127:
        return -1, 0, 0
    if family == 8:
        return 0, a, b
    if family == 9:
        return (1 if b else 0), a, b
    if family == 10:
        return 5, a, b
    if family == 11:
        return 2, a, b
    if family == 12:
        return 3, a, 0
    if family == 14:
        return 4, a, b
    return -1, 0, 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=HERE / "generated")
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    compiler = shutil.which("iverilog")
    runner = shutil.which("vvp")
    if not compiler or not runner:
        raise SystemExit("iverilog and vvp are required")
    rtl = [
        PROJECT / "rtl/instrument/midi_performance.v",
        PROJECT / "rtl/transport/usb_midi_codec.v",
    ]
    testbench = HERE / "tb_packet_vectors.v"
    executable = out / "packet_vectors.vvp"
    raw = out / "usb_midi_vectors_raw.csv"
    compile_cmd = [compiler, "-g2012", "-s", "tb_packet_vectors", "-o", str(executable),
                   str(testbench), *(str(path) for path in rtl)]
    subprocess.run(compile_cmd, check=True)
    # Icarus' Verilog $fopen rejects UTF-8 paths. Keep its filename ASCII and
    # select the destination using subprocess' Unicode-aware working directory.
    run_cmd = [runner, executable.name, f"+output={raw.name}"]
    completed = subprocess.run(run_cmd, cwd=out, check=True, text=True, capture_output=True)
    print(completed.stdout, end="")
    (out / "simulation.log").write_text(completed.stdout + completed.stderr)
    source_counts: collections.Counter[str] = collections.Counter()
    kind_counts: collections.Counter[int] = collections.Counter()
    csv_path = out / "usb_midi_vectors.csv"
    with raw.open(newline="") as src, csv_path.open("w", newline="") as dest:
        reader = csv.DictReader(src)
        writer = csv.DictWriter(dest, fieldnames=[
            "source", "status", "a", "b", "length", "packethex",
            "kind", "expecta", "expectb", "requested_b",
        ])
        writer.writeheader()
        for row in reader:
            packet = bytes.fromhex(row["packethex"])
            assert len(packet) == 4
            assert tuple(packet[1:]) == tuple(int(row[name]) for name in ("status", "a", "b"))
            kind, a, b = target_expectation(packet)
            row.update(kind=kind, expecta=a, expectb=b)
            writer.writerow(row)
            source_counts[row["source"]] += 1
            kind_counts[kind] += 1
    count = sum(source_counts.values())
    assert count == 2052, (count, source_counts)
    report = {
        "result": "PASS", "wire_packets": count,
        "host_forwarded_packets": count - kind_counts[-1],
        "host_ignored_packets": kind_counts[-1],
        "source_counts": dict(source_counts),
        "host_kind_counts": dict(sorted(kind_counts.items())),
        "production_sources": {
            str(path.relative_to(PROJECT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in rtl
        },
        "testbench_sha256": hashlib.sha256(testbench.read_bytes()).hexdigest(),
        "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "compile_command": compile_cmd, "simulation_command": run_cmd,
        "simulation_working_directory": str(out),
        "scope": "Production GW25K performance/codec RTL; expected generic synth event contract. No hardware test.",
    }
    (out / "packet_vectors_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"PASS vectors: {count} packets -> {csv_path}")


if __name__ == "__main__":
    main()
