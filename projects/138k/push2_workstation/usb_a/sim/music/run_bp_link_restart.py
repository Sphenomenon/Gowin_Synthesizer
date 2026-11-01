#!/usr/bin/env python3
"""Real CNN link drain/restart, native DDR/CDC, default compatibility.

Uses the unchanged real model with the existing simulation-only preloaded
loader convention. WIN_LEN=2048 and FRAME_LIMIT=2 are lifecycle probes, not
musical accuracy or complete-workstation physical acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

from run_bp_config_ab import MUSIC_SOURCES

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SRC = ROOT / "rtl/music"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    # Preserve the production compilation-unit macro order.
    sources = [SRC / "basic_pitch_nn_ddr.sv"]
    sources += [SRC / name for name in MUSIC_SOURCES if name != "basic_pitch_nn_ddr.sv"]
    # Keep production literals and locked-builder anchors intact. Only the
    # simulation copy reduces the window and frame count, with exact drift
    # checking and both source/copy hashes recorded below.
    link_source = SRC / "basic_pitch_workstation_link.sv"
    link_text = link_source.read_text()
    anchor = ".WIN_LEN(43844),.FRAME_LIMIT(172),.OCTAVE_LIMIT(9)"
    if link_text.count(anchor) != 1:
        raise SystemExit("link dimensions anchor changed")
    link_copy = out / "basic_pitch_workstation_link.sv"
    link_copy.write_text(link_text.replace(anchor,
        ".WIN_LEN(2048),.FRAME_LIMIT(2),.OCTAVE_LIMIT(9)"))
    sources += [link_copy]
    sources += [SRC / name for name in (
        "basic_pitch_link_uart.sv",
        "basic_pitch_ddr16_port.sv", "basic_pitch_ddr_command_buffer.sv",
        "music_async_fifo.sv")]
    sources += [ROOT / "rtl/memory/workstation_sdp.sv",
                ROOT.parent / "touchboard_test/rtl/uart_tx.v",
                HERE / "tb_bp_link_restart.sv"]
    metadata = {
        "scope": "actual link native DDR/CDC lifecycle, not quality/physical acceptance",
        "parameters": {"WIN_LEN": 2048, "FRAME_LIMIT": 2,
                       "RESTART_TIMEOUT_CYCLES": 512, "source_period_ns": 20,
                       "memory_period_ns": 14},
        "model_sha256": hashlib.sha256((SRC / "weights/cnn_ddr_blob.mem").read_bytes()).hexdigest(),
        "model_loader": "simulation-only UART loader state DONE; real DDR model preload",
        "original_link_sha256": hashlib.sha256(link_source.read_bytes()).hexdigest(),
        "simulation_overlay": "exact one-anchor WIN_LEN=2048, FRAME_LIMIT=2; no production RTL mutation",
        "sources": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        "runs": [],
    }
    inference = []
    started = time.monotonic()
    for enabled in (1, 0):
        obj = out / f"obj_{enabled}"
        cmd = ["verilator", "--binary", "--timing", "--build-jobs", "4", "-Wno-fatal",
               "--top-module", "tb_bp_link_restart", "--Mdir", str(obj),
               f"-GDRAIN_ENABLE={enabled}", "-I" + str(SRC)] + [str(p) for p in sources]
        with (out / f"build_{enabled}.log").open("w") as log:
            result = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            raise SystemExit(f"build failed: {out / f'build_{enabled}.log'}")
        print(f"built drain_restart={enabled}", flush=True)
        with (out / f"run_{enabled}.log").open("w") as log:
            with subprocess.Popen([str(obj / "Vtb_bp_link_restart")], cwd=ROOT,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True) as process:
                lines = []
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    lines.append(line)
                    print(line, end="", flush=True)
                code = process.wait()
        output = "".join(lines)
        if code or "PASS actual Basic Pitch link restart" not in output:
            raise SystemExit(f"simulation failed: {out / f'run_{enabled}.log'}")
        observed = re.findall(r"^(?:INFERENCE|NOTE|LAYER) .*", output, flags=re.M)
        inference.append(observed)
        cases = re.findall(r"^CASE .*", output, flags=re.M)
        metadata["runs"].append({"drain_restart": enabled, "cases": cases,
                                 "inference": observed, "exit_code": code})
    if inference[0] != inference[1]:
        raise SystemExit("post-cancel real CNN inference differs from fresh default link")
    metadata["inference_equal"] = True
    metadata["status"] = "PASS"
    metadata["elapsed_seconds"] = round(time.monotonic() - started, 3)
    (out / "verification.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print("PASS post-cancel and default actual link six-layer hashes, writes and score equal")


if __name__ == "__main__":
    main()
