#!/usr/bin/env python3
"""Portable Icarus HDL regression. Invoke from any directory, including WSL."""
from pathlib import Path
import argparse
from datetime import datetime
import hashlib
import json
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", help="single testbench stem, e.g. tb_pt8211_tx")
    parser.add_argument("--output-dir", type=Path, help="new output workspace; logs are saved under build/sim")
    parser.add_argument("--timeout", type=int, default=600, help="wall-clock seconds per compiler/simulator command (default: 600)")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    for tool in ("iverilog", "vvp"):
        if not shutil.which(tool):
            parser.error(f"{tool} is required; install Icarus Verilog or run inside WSL")
    sources = sorted((ROOT / "src").rglob("*.v"))
    # Encrypted DDR PHY is built by Gowin. Native user logic is verified with
    # ready/response memory models, without claiming analog PHY simulation.
    sources += sorted(p for p in (ROOT / "vendor").rglob("*.v") if "gowin_ddr3" not in p.parts)
    sources += sorted((ROOT / "sim" / "models").glob("*.v"))
    tests = sorted((ROOT / "sim").glob("tb_*.sv"))
    if args.test:
        tests = [p for p in tests if p.stem == args.test]
    if not tests:
        parser.error("No matching testbench")
    output = (args.output_dir or ROOT / "out" / datetime.now().strftime("sim_%Y%m%d_%H%M%S_%f")).resolve()
    if output.exists():
        parser.error(f"refusing to overwrite existing output: {output}")
    # Run HDL in this new workspace too: e.g. tb_note_transition writes a
    # relative build/sim trace. No simulator output may touch historical build/.
    build = output / "build" / "sim"
    build.mkdir(parents=True)
    inputs = sources + tests + [Path(__file__).resolve()]
    (output / "inputs_sha256.json").write_text(json.dumps(
        {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
         for path in inputs}, indent=2) + "\n", encoding="utf-8")
    results = []
    for tb in tests:
        out = build / (tb.stem + ".vvp")
        start = time.monotonic()
        commands = [
            ["iverilog", "-g2012", "-Wall", "-s", tb.stem, "-o", str(out), *map(str, sources), str(tb)],
            ["vvp", str(out)],
        ]
        logs = []
        for command in commands:
            try:
                result = subprocess.run(command, cwd=output, text=True, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, timeout=args.timeout)
            except subprocess.TimeoutExpired as error:
                captured = error.stdout or ""
                logs.append(captured.decode(errors="replace") if isinstance(captured, bytes) else captured)
                logs.append(f"FAIL {tb.stem}: wall-clock timeout after {args.timeout}s")
                (build / (tb.stem + ".log")).write_text("\n".join(logs), encoding="utf-8")
                raise SystemExit(logs[-1])
            logs.append(result.stdout)
            if result.returncode:
                print(result.stdout)
                (build / (tb.stem + ".log")).write_text("\n".join(logs), encoding="utf-8")
                raise SystemExit(f"FAIL {tb.stem} (exit {result.returncode})")
        if "PASS " not in logs[-1]:
            raise SystemExit(f"FAIL {tb.stem}: no completion marker")
        (build / (tb.stem + ".log")).write_text("\n".join(logs), encoding="utf-8")
        results.append(f"{tb.stem}: PASS ({time.monotonic()-start:.2f}s)")
        print(logs[-1].strip())
    (build / "summary.txt").write_text("\n".join(results)+"\n", encoding="utf-8")
    print(f"{len(results)} HDL tests passed; logs: {build}")

if __name__ == "__main__":
    main()
