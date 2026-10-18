"""Read-only logical audit of the vendor C-version PHY reset/clock-stop cone.

Evaluates the original generated .vo LUT truth tables and Gowin DFF semantics.
This is a control-sequence audit, not an analog PLL/DDR or metastability model.
"""
from __future__ import annotations

import functools
import argparse
import hashlib
import json
import os
import pathlib
import re

PROJECT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = pathlib.Path(os.environ.get("PRJ1_DDR_REFERENCE", PROJECT.parents[1] / (
    "Doc/tangMega-138K-example/ddr_memory/ddr_memory_test_uart/src/"
    "ddr3_memory_interface/ddr3_memory_interface.vo"
)))
EXPECTED_NETLIST_SHA256 = "0a21efa69eab7d8b9912bb6aaf880ad35de00d562cc451587c11bd3c002ed17b"
EXPECTED_IP_SHA256 = "4a6e26d2ccb8d01221103df4cdf71f3517d2700614020e0c414aafec04a495bc"
BASE = "\\gw3_top/u_ddr_phy_top/"
WATCH = ["ddr_rst", "pll_stop", BASE + "ddr_sync/ready", BASE + "cs_memsync [3]", BASE + "stop_d"]


def run(case: str, clocks: int = 42080) -> dict:
    raw = SOURCE.read_text()
    instances = re.findall(r"(?m)^(\w+) (\\\S+)\s+\((.*?)^\);", raw, re.S)
    params = {
        name: int(bits, 16 if base == "h" else 2)
        for name, base, bits in re.findall(r"defparam (\\\S+) \.INIT=\d+'([bh])([0-9A-Fa-f]+);", raw)
    }
    selected = [
        (typ, name, {pin: net.strip() for pin, net in re.findall(r"\.(\w+)\(([^()]*)\)", body)})
        for typ, name, body in instances
        if "/ddr_sync/" in name
        or re.search(r"/(ddr_rsti_reg_[012]_s0|stop_reg_[012]_s0|pll_stop_d_s0|n7_s2)$", name)
    ]
    assert len(selected) == 108, "Vendor reset cone changed; review the new implementation."
    comb = {pins.get("F", pins.get("O")): (typ, name, pins) for typ, name, pins in selected if not typ.startswith("DFF")}
    ff = [(typ, name, pins) for typ, name, pins in selected if typ.startswith("DFF")]
    state = {pins["Q"]: params[name] for typ, name, pins in ff}
    trace, last = [], None
    stop_since = None
    reset_falls = []
    for cycle in range(clocks):
        lock = cycle >= 20 and not (case == "lock_loss" and 33000 <= cycle < 33008)
        reset = cycle >= 8 and not (case == "external_reset" and 33000 <= cycle < 33008)
        ext = {
            "GND": 0, "VCC": 1, "rst_n": int(reset), "pll_lock": int(lock),
            BASE + "dll_lock": int(lock),
            BASE + "sys_reset_Z": int(case == "recalibration" and 33000 <= cycle < 33008),
        }

        @functools.lru_cache(None)
        def value(net: str) -> int:
            if net in state:
                return state[net]
            if net in ext:
                return ext[net]
            typ, name, pins = comb[net]
            if typ == "INV":
                return 1 - value(pins["I"])
            if typ.startswith("LUT"):
                index = sum(value(pins["I" + str(i)]) << i for i in range(int(typ[3:])))
                return (params[name] >> index) & 1
            raise ValueError((typ, name))

        # Async clear/preset settles between edges. DFFSE SET is synchronous.
        for unused in range(4):
            for typ, name, pins in ff:
                if "CLEAR" in pins and value(pins["CLEAR"]):
                    state[pins["Q"]] = 0
                if "PRESET" in pins and value(pins["PRESET"]):
                    state[pins["Q"]] = 1
            value.cache_clear()
        observation = tuple(value(net) for net in WATCH)
        if observation != last:
            trace.append([cycle, *observation])
        if observation[1] == 0 and (last is None or last[1] == 1):
            stop_since = cycle
        if last is not None and last[0] == 1 and observation[0] == 0:
            reset_falls.append({"cycle": cycle, "pll_enabled": observation[1], "stopped_cycles": None if stop_since is None else cycle - stop_since})
        if last is not None and last[1] == 0 and observation[1] == 1 and reset_falls:
            reset_falls[-1]["cycles_to_restart"] = cycle - reset_falls[-1]["cycle"]
            stop_since = None
        last = observation
        upcoming = {}
        for typ, name, pins in ff:
            if "CLEAR" in pins and value(pins["CLEAR"]):
                upcoming[pins["Q"]] = 0
            elif "PRESET" in pins and value(pins["PRESET"]):
                upcoming[pins["Q"]] = 1
            elif "SET" in pins and value(pins["SET"]):
                upcoming[pins["Q"]] = 1
            elif value(pins["CE"]):
                upcoming[pins["Q"]] = value(pins["D"])
        state.update(upcoming)
    return {"case": case, "cells": len(selected), "clock_period_ns": 20, "columns": ["cycle", *WATCH], "trace": trace, "reset_falls": reset_falls}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=pathlib.Path, default=SOURCE)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    SOURCE = args.source
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    vendor_hash = hashlib.sha256((PROJECT / "vendor/gowin_ddr3/ddr3_memory_interface.v").read_bytes()).hexdigest()
    sibling_hash = hashlib.sha256(SOURCE.with_suffix(".v").read_bytes()).hexdigest()
    assert source_hash == EXPECTED_NETLIST_SHA256, "Reference netlist changed; re-audit before relying on this evidence."
    assert vendor_hash == sibling_hash == EXPECTED_IP_SHA256, "Project IP must match the audited C-version reference byte for byte."
    result = {
        "source": str(SOURCE.relative_to(PROJECT.parents[1])) if SOURCE.is_relative_to(PROJECT.parents[1]) else str(SOURCE),
        "source_sha256": source_hash,
        "encrypted_ip_sha256": vendor_hash,
        "method": "Original LUT INIT tables; official DFFCE/DFFPE asynchronous clear/preset and DFFSE synchronous set semantics; no analog timing model.",
        "cases": [run(case, 51080 if case == "external_reset" else 42080) for case in ["startup", "recalibration", "external_reset", "lock_loss"]],
    }
    for case in result["cases"]:
        stopped_falls = [event for event in case["reset_falls"] if event["pll_enabled"] == 0]
        assert stopped_falls, case["case"]
        for event in stopped_falls:
            assert event["stopped_cycles"] >= 8 and event["cycles_to_restart"] >= 4, event
    encoded = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
        print(f"PASS: four reset/lock scenarios; 108 reference cells; trace written to {args.output}")
    else:
        print(encoded, end="")
