#!/usr/bin/env python3
"""Verify the serialized HDMI clock against installed official Gowin models.

Run with Icarus on PATH, e.g. under WSL. Only the four required primitives are
extracted to ignored build output; the vendor simulation library is not copied
into version control. --simlib or GOWIN_SIMLIB selects an installed gw5a folder.
"""
from pathlib import Path
import argparse
import hashlib
import json
from gowin_paths import gowin_simlib
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simlib", type=Path)
    args = parser.parse_args()
    for command in ("iverilog", "vvp"):
        if not shutil.which(command):
            parser.error(f"{command} is required; run where Icarus is installed")
    primitive = gowin_simlib(args.simlib) / "prim_sim.v"
    text = primitive.read_text(encoding="utf-8", errors="replace")
    blocks = []
    for name in ("GSR", "CLKDIV", "OSER10", "ELVDS_OBUF"):
        match = re.search(r"^module\s+" + name + r"\s*\(.*?^endmodule\b[^\n]*", text, re.M | re.S)
        if not match:
            raise SystemExit(f"FAIL official primitive missing: {name}")
        blocks.append(match[0])
    build = ROOT / "build" / "tmds_clock_primitive"
    build.mkdir(parents=True, exist_ok=True)
    extracted = build / "official_primitive_models.v"
    extracted.write_text("`timescale 1ns/1fs\n" + "\n\n".join(blocks) + "\n", encoding="utf-8")
    sources = [ROOT / "vendor/sipeed_dvi/video_pll_1080p_gw5a.v",
               ROOT / "vendor/sipeed_dvi/dvi_tx_clk_drv.v",
               ROOT / "vendor/sipeed_dvi/dvi_tx_tmds_phy.v",
               ROOT / "vendor/sipeed_dvi/dvi_tx_top.v",
               ROOT / "vendor/sipeed_dvi/dvi_tx_tmds_enc.v",
               ROOT / "sim/primitives/tb_tmds_clock.sv"]
    binary = build / "tb_tmds_clock.vvp"
    commands = [["iverilog", "-g2012", "-s", "tb_tmds_clock", "-o", str(binary), str(extracted), *map(str, sources)],
                ["vvp", str(binary)]]
    logs = []
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, timeout=60)
        logs.append(result.stdout)
        if result.returncode:
            (build / "run.log").write_text("\n".join(logs), encoding="utf-8")
            raise SystemExit(result.stdout + "\nFAIL official TMDS clock test")
    if "PASS official Gowin TMDS clock: all 9 startup/phase cases" not in logs[-1]:
        raise SystemExit("FAIL official TMDS clock completion marker missing")
    (build / "run.log").write_text("\n".join(logs), encoding="utf-8")
    evidence = {"primitive_model_sha256": hashlib.sha256(primitive.read_bytes()).hexdigest(),
                "source_sha256": {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in sources + [Path(__file__).resolve()]},
                "phase_delays_ns": [0.0, 2.041, 2.775], "startup_cases_per_phase": 3,
                "clock_word_d9_to_d0": "1111100000", "raw_divider_duty_percent": 60,
                "forwarded_clock_duty_percent": 50, "clock_period_unit_intervals": 10,
                "ordered_rgb_words_checked_per_case": 120, "data_lanes_checked": 3,
                "alignment": "one forwarded-clock falling edge marks D0 on all lanes; discard exactly seven startup words, no phase search",
                "limits": "Official digital models and a PCLK phase sweep; not analog PLL, complete SDF, PCB or receiver validation."}
    (build / "evidence.json").write_text(json.dumps(evidence, indent=2)+"\n", encoding="utf-8")
    print(logs[-1].strip())
    print(f"Evidence: {build / 'evidence.json'}")


if __name__ == "__main__":
    main()
