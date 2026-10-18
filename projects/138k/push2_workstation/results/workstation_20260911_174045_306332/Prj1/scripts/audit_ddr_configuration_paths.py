"""Audit bounded DDR configuration paths using reference netlist and public models.

No board access; no vendor source copies; no modification of the encrypted IP.
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import itertools
import json
from pathlib import Path
import re

import audit_ddr_reset_sequence as reset_audit
from gowin_paths import gowin_simlib


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simlib", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    args.simlib = gowin_simlib(args.simlib)
    source = reset_audit.SOURCE
    assert sha(source) == reset_audit.EXPECTED_NETLIST_SHA256
    assert sha(source.with_suffix(".v")) == reset_audit.EXPECTED_IP_SHA256
    assert sha(reset_audit.PROJECT / "vendor/gowin_ddr3/ddr3_memory_interface.v") == reset_audit.EXPECTED_IP_SHA256
    raw = source.read_text()
    params = {
        name: int(bits, 16 if radix == "h" else 2)
        for name, radix, bits in re.findall(r"defparam (\\\S+) \.INIT=\d+'([bh])([0-9A-Fa-f]+);", raw)
    }
    cells = {
        name: (typ, {pin: net.strip() for pin, net in re.findall(r"\.(\w+)\(([^()]*)\)", body)})
        for typ, name, body in re.findall(r"(?m)^(\w+) (\\\S+)\s+\((.*?)^\);", raw, re.S)
    }
    comb = {
        pins.get("F", pins.get("O")): (typ, name, pins)
        for name, (typ, pins) in cells.items() if typ.startswith("LUT") or typ == "INV"
    }
    base = reset_audit.BASE
    init = base + "u_ddr_init/"

    def evaluate(net: str, terminal: dict[str, int]) -> int:
        if net in terminal:
            return terminal[net]
        if net in ("GND", "VCC"):
            return int(net == "VCC")
        typ, name, pins = comb[net]
        if typ == "INV":
            return 1 - evaluate(pins["I"], terminal)
        index = sum(evaluate(pins["I" + str(i)], terminal) << i for i in range(int(typ[3:])))
        return (params[name] >> index) & 1

    # Snapshot enable is exactly a synchronized initialization edge and DLL LOCK.
    for old, recent, lock in itertools.product((0, 1), repeat=3):
        terminal = {base + "ddr_init_st_rrr": old, base + "ddr_init_st_rr": recent, base + "dll_lock": lock}
        assert evaluate(base + "n2474_3", terminal) == int(not old and recent and lock)
    for bit in range(8):
        typ, pins = cells[base + f"dll_step_base_{bit}_s0"]
        assert typ == "DFFCE" and pins["D"] == base + f"dll_step [{bit}]"
        assert pins["CE"] == base + "n2474_3" and pins["CLK"] == "clk_out"

    # Prove the eight-cycle pulse extension for all possible local histories.
    for bits in itertools.product((0, 1), repeat=9):
        adj, read_hold, *history = bits
        terminal = {init + "wrlvl_state.WRLVL_ADJ_DQS": adj, init + "hold_gen[0].hold_reg [0]": read_hold}
        terminal.update({init + f"hold_gen[0].hold_reg_d [{i}]": value for i, value in enumerate(history)})
        assert evaluate(init + "n2387_3", terminal) == int(any(bits))
    for lane in range(4):
        for configured, hold in itertools.product((0, 1), repeat=2):
            terminal = {init + f"read_rclksel_conf [{lane}]": configured, init + f"hold_gen[{lane}].hold_i": hold}
            assert evaluate(base + f"hold_Z [{lane}]", terminal) == int(hold and not configured)
        typ, pins = cells[init + f"read_rclksel_conf_{lane}_s0"]
        assert typ == "DFFCE" and pins["D"] == "VCC" and pins["CLEAR"] == "ddr_rst"
        _, pins = cells[init + f"hold_gen[{lane}].hold_i_s0"]
        assert pins["CLK"] == "clk_out" and pins["D"] == init + "n2387_3"
        _, dqs = cells[base + f"u_ddr_phy_wds/data_lane_gen[{lane}].u_ddr_phy_data_lane/u_ddr_phy_data_io/u_dqs"]
        assert dqs["PCLK"] == "clk_out" and dqs["FCLK"] == "memory_clk"

    # WSTEP has two further UI registers after the calibration update register.
    for bit in range(32):
        _, pins = cells[init + f"wstep_reg_d_{bit}_s0"]
        assert pins["D"] == init + f"wstep_reg [{bit}]" and pins["CLK"] == "clk_out"
        _, pins = cells[init + f"wstep_{bit}_s0"]
        assert pins["D"] == init + f"wstep_reg_d [{bit}]" and pins["CLK"] == "clk_out"

    # The official public timing checks place HOLD in the PCLK domain.
    models = []
    for filename in ("DQS_tsim_M.vp", "DQS_tsim_V.vp"):
        path = args.simlib / filename
        text = path.read_text()
        checks = [line.strip() for line in text.splitlines() if "$setuphold" in line and re.search(r"\bHOLD\b", line)]
        assert len(checks) == 2 and all("posedge PCLK" in line for line in checks)
        assert any("posedge HOLD" in line for line in checks) and any("negedge HOLD" in line for line in checks)
        models.append({"file": filename, "sha256": sha(path), "hold_checks": checks})
    primitive_path = args.simlib / "prim_sim.v"
    primitive = primitive_path.read_text(encoding="utf-8", errors="replace")
    dll = primitive.split("module DDRDLL (", 1)[1].split("endmodule", 1)[0]
    assert "else if(UPDNCNTL==0)" in dll and "step_reg_sig <= step_reg;" in dll
    assert 'assign STEP = (DLL_FORCE=="TRUE") ? 255 : step_reg_sig;' in dll

    # Keep the original 108-cell sequence evaluator; add only observed outputs.
    reset_audit.WATCH.extend([base + "uddcntln", base + "ddr_init_st_Z"])
    sequence = [reset_audit.run("startup", 16520), reset_audit.run("recalibration", 33100)]
    frozen_windows = []
    for case in sequence:
        previous = None
        frozen_at = None
        for row in case["trace"]:
            # columns: cycle, reset, enable, ready, cs3, stop_d, update_n, init_st.
            if previous is not None and previous[6] == 0 and row[6] == 1:
                frozen_at = row[0]
            if previous is not None and previous[2] == 0 and row[2] == 1:
                assert frozen_at is not None
                elapsed = row[0] - frozen_at
                assert elapsed >= 31
                frozen_windows.append({"case": case["case"], "step_frozen_cycle": frozen_at,
                                       "memory_restart_cycle": row[0], "frozen_before_restart_ns": elapsed * 20})
            previous = row

    result = {
        "reference_netlist_sha256": sha(source), "encrypted_ip_sha256": reset_audit.EXPECTED_IP_SHA256,
        "primitive_model_sha256": sha(primitive_path), "dqs_timing_models": models,
        "dll_snapshot_enable": "!ddr_init_st_rrr && ddr_init_st_rr && dll_lock",
        "dll_step_frozen_windows": frozen_windows,
        "hold_equation": "hold_i_next = WRLVL_ADJ_DQS || READ_CAL_HOLD_delayed_1 || OR(previous_7_cycles)",
        "hold_output_equation": "HOLD[lane] = hold_i[lane] && !read_rclksel_conf[lane]",
        "hold_equation_cases_checked": 512, "wstep_post_update_ui_registers": 2,
        "limits": "Logical/configuration audit, not analog DQS validation. Public HOLD timing models specify PCLK; keep real hold analysis and bounded propagation. WLOADN remains fully timed.",
    }
    encoded = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
        print(f"PASS DDR configuration audit: 620 ns STEP freeze window; 512 HOLD truth-table cases; 32 WSTEP pipelines; both official PCLK models. Evidence: {args.output}")
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
