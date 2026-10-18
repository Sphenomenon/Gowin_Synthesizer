#!/usr/bin/env python3
"""Reject missing/stale Gowin output, timing violations and inactive CDC constraints."""
from pathlib import Path
import hashlib
import json
from gowin_paths import gowin_simlib
import re
import xml.etree.ElementTree as ET
from check_serializer_startup import inspect_serializer_startup
from check_video_pll_init import inspect_video_pll_init
from audit_ddr_reset_sequence import SOURCE as DDR_AUDIT_SOURCE, EXPECTED_NETLIST_SHA256, EXPECTED_IP_SHA256

ROOT = Path(__file__).resolve().parents[1]


def inspect_ddr_audit():
    """Bind the routed timing allowance to the exact, audited C-version IP."""
    if not __debug__:
        return ["DDR source audit requires normal Python execution; do not use -O"], {}
    try:
        audit_file = ROOT / "docs/evidence/ddr_reset_sequence.json"
        audit = json.loads(audit_file.read_text(encoding="utf-8"))
        assert hashlib.sha256(DDR_AUDIT_SOURCE.read_bytes()).hexdigest() == EXPECTED_NETLIST_SHA256, \
            "DDR reset reference netlist changed"
        assert hashlib.sha256((ROOT / "vendor/gowin_ddr3/ddr3_memory_interface.v").read_bytes()).hexdigest() == EXPECTED_IP_SHA256, \
            "DDR IP differs from the audited C-version"
        assert audit["source_sha256"] == EXPECTED_NETLIST_SHA256 and audit["encrypted_ip_sha256"] == EXPECTED_IP_SHA256, \
            "DDR reset evidence hashes differ from the audited sources"
        cases = {case["case"]: case for case in audit["cases"]}
        assert set(cases) == {"startup", "recalibration", "external_reset", "lock_loss"}, "DDR reset scenarios missing"
        for case in cases.values():
            assert case["cells"] == 108 and case["clock_period_ns"] == 20, "DDR reset audit shape changed"
            events = [event for event in case["reset_falls"] if event["pll_enabled"] == 0]
            assert events and all(event["stopped_cycles"] >= 8 and event["cycles_to_restart"] >= 4 for event in events), \
                "DDR reset evidence no longer establishes the 80ns restart window"
        return [], {"source_sha256": EXPECTED_NETLIST_SHA256, "encrypted_ip_sha256": EXPECTED_IP_SHA256,
                    "sequence_evidence_sha256": hashlib.sha256(audit_file.read_bytes()).hexdigest(),
                    "sequence_checker_sha256": hashlib.sha256((ROOT / "scripts/audit_ddr_reset_sequence.py").read_bytes()).hexdigest()}
    except (OSError, AssertionError, KeyError, ValueError) as error:
        return [f"DDR reset source audit failed: {error}"], {}


def inspect_ddr_configuration_audit():
    """Bind DLL STEP/HOLD exceptions to the audited IP and official DQS models."""
    if not __debug__:
        return ["DDR configuration audit requires normal Python execution; do not use -O"], {}
    try:
        path = ROOT / "docs/evidence/ddr_configuration_paths.json"
        audit = json.loads(path.read_text(encoding="utf-8"))
        assert audit["reference_netlist_sha256"] == EXPECTED_NETLIST_SHA256 and \
            audit["encrypted_ip_sha256"] == EXPECTED_IP_SHA256, "DDR configuration evidence source hashes changed"
        simlib = gowin_simlib()
        assert hashlib.sha256((simlib / "prim_sim.v").read_bytes()).hexdigest() == audit["primitive_model_sha256"], \
            "official Gowin primitive model differs from configuration audit"
        models = audit["dqs_timing_models"]
        assert {model["file"] for model in models} == {"DQS_tsim_M.vp", "DQS_tsim_V.vp"} and len(models) == 2, \
            "DQS timing model audit incomplete"
        for model in models:
            assert hashlib.sha256((simlib / model["file"]).read_bytes()).hexdigest() == model["sha256"], \
                f"official DQS timing model changed: {model['file']}"
            assert len(model["hold_checks"]) == 2 and all("posedge PCLK" in line and "HOLD" in line for line in model["hold_checks"]), \
                "HOLD no longer has the audited PCLK checks"
        windows = audit["dll_step_frozen_windows"]
        assert {window["case"] for window in windows} == {"startup", "recalibration"}, "DLL STEP scenarios missing"
        assert all(window["frozen_before_restart_ns"] >= 620 for window in windows), "DLL STEP stable interval shrank"
        assert audit["hold_equation_cases_checked"] == 512 and audit["wstep_post_update_ui_registers"] == 2, \
            "DDR configuration logic audit incomplete"
        return [], {"evidence_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "checker_sha256": hashlib.sha256((ROOT / "scripts/audit_ddr_configuration_paths.py").read_bytes()).hexdigest(),
                    "reference_netlist_sha256": EXPECTED_NETLIST_SHA256, "encrypted_ip_sha256": EXPECTED_IP_SHA256,
                    "primitive_model_sha256": audit["primitive_model_sha256"], "dqs_timing_models": models}
    except (OSError, AssertionError, KeyError, ValueError) as error:
        return [f"DDR configuration source audit failed: {error}"], {}


def normalized(command):
    return " ".join(command.split())


def inspect_timing(text, sdc):
    """Read final STA, not intermediate PnR warnings; never relax timing failures."""
    errors = []
    counts = {}
    for kind in ("Setup", "Hold"):
        match = re.search(rf"<Numbers of {kind} Violated Endpoints>:(\d+)", text)
        counts[kind.lower()] = int(match[1]) if match else None
        if not match or int(match[1]):
            errors.append(f"{kind} timing violations: {counts[kind.lower()]}")
    # Includes detailed setup, hold, recovery, removal AND minimum pulse width.
    slacks = [float(s) for s in re.findall(r"^Slack\s*:\s*(-?[\d.]+)", text, re.M)]
    if not slacks:
        errors.append("detailed timing/pulse-width slacks missing")
    elif min(slacks) < 0:
        errors.append(f"negative detailed slack (including recovery/removal/pulse width): {min(slacks):.3f} ns")
    mpw_start = text.rfind("\n3.4 Minimum Pulse Width Report")
    mpw_end = text.rfind("\n3.5 High Fanout Nets Report")
    mpw_section = text[mpw_start:mpw_end] if mpw_start >= 0 and mpw_end > mpw_start else ""
    mpw_slacks = [float(s) for s in re.findall(r"^Slack\s*:\s*(-?[\d.]+)", mpw_section, re.M)]
    if not mpw_slacks:
        errors.append("detailed minimum pulse-width report missing")

    clock_section = text[text.rfind("\n2.2 Clock Summary"):text.rfind("\n2.3 Max Frequency Summary")]
    clocks = []
    for line in clock_section.splitlines():
        match = re.match(r"\s*\d+\s+(\S+)\s+(Base|Generated)\s+([\d.]+)\s+([\d.]+)MHz\s+", line)
        if match:
            clocks.append({"name": match[1], "type": match[2], "period_ns": float(match[3]),
                           "frequency_mhz": float(match[4]), "object": line.split()[-1]})
    expected = {
        "system": (r"^clk_50m$", 50.0),
        "ddr_memory": (r"^u_memory/u_pll/u_pll(?:_\d+)?/PLL_inst/CLKOUT2$", 400.0),
        "ddr_ui": (r"^u_memory/u_ddr3/gw3_top/u_ddr_phy_top/fclkdiv/CLKOUT$", 100.0),
        "video_reference": (r"^u_video/u_clock/g_hardware[./]u_pll/u_reference/PLL_inst/CLKOUT0$", 49.5),
        "video_serial": (r"^u_video/u_clock/g_hardware[./]u_pll/u_tmds/PLL_inst/CLKOUT0$", 742.5),
        "video_pixel": (r"^u_video/u_clock/g_hardware[./]u_pll/u_pixel_div/CLKOUT$", 148.5),
    }
    for label, (pattern, frequency) in expected.items():
        matches = [clock for clock in clocks if re.match(pattern, clock["object"])]
        if len(matches) != 1:
            errors.append(f"{label}: expected exactly one timed clock, found {len(matches)}")
        elif abs(matches[0]["frequency_mhz"] - frequency) > 0.001 or \
                abs(matches[0]["period_ns"] - 1000 / frequency) > 0.00051:
            errors.append(f"{label}: unexpected clock frequency/period: {matches[0]}")

    # Check every current SDC clock/exception, not one stale VGA constraint.
    constraint_section = text[text.rfind("\n3.8 Timing Constraints Report"):]
    reported = {}
    for line in constraint_section.splitlines():
        match = re.match(r"\s*TC_\S+\s+(\S+)\s+(.+)", line)
        if match:
            reported[normalized(match[2])] = match[1]
    commands = [normalized(line) for line in sdc.splitlines()
                if re.match(r"\s*(?:create_(?:generated_)?clock|set_(?:false_path|max_delay|min_delay|multicycle_path|clock_groups))\b", line)]
    if not commands:
        errors.append("no clock/CDC SDC constraints found")
    for command in commands:
        if reported.get(command) != "Actived":
            errors.append(f"SDC constraint not active in this report: {command}")

    # Actived can match only part of a bus. Require actual path examples for
    # every max-delay group too; zero overall violations catches paths moved
    # into DSP input registers that no longer match a source register name.
    start = text.rfind("\n3.7.1 Setup Analysis Report")
    end = text.rfind("\n3.7.2 Hold Analysis Report")
    exception_section = text[start:end] if start >= 0 and end > start else ""
    delay_paths = {}
    for match in re.finditer(r"Timing Path Constraint\[\d+\]: ([^\n]+)\n(.*?)(?=Timing Path Constraint\[|\Z)",
                             exception_section, re.S):
        delay_paths[normalized(match[1])] = match[2].count("Path Summary:")
    for command in commands:
        if command.startswith("set_max_delay ") and not delay_paths.get(command):
            errors.append(f"max-delay constraint has no reported data paths: {command}")
    return errors, {"setup_violated_endpoints": counts["setup"], "hold_violated_endpoints": counts["hold"],
                    "minimum_reported_slack_ns": min(slacks) if slacks else None,
                    "minimum_pulse_width_slack_ns": min(mpw_slacks) if mpw_slacks else None,
                    "clocks": clocks, "cdc_max_delay_reported_paths": delay_paths}


def check():
    pnr = ROOT / "impl" / "pnr"
    bitstream = pnr / "Prj1.fs"
    report = pnr / "Prj1.tr"
    sdf = pnr / "Prj1.sdf"
    routed_netlist = pnr / "Prj1.vo"
    if not all(path.is_file() for path in (bitstream, report, sdf, routed_netlist)):
        raise SystemExit("FAIL: build bitstream/timing report/SDF/routed netlist missing")
    text = report.read_text(encoding="utf-8", errors="replace")
    sdc = (ROOT / "constraints" / "tang_mega_138k.sdc").read_text(encoding="utf-8")
    errors, timing = inspect_timing(text, sdc)
    ddr_audit_errors, ddr_audit = inspect_ddr_audit()
    errors.extend(ddr_audit_errors)
    configuration_errors, configuration_audit = inspect_ddr_configuration_audit()
    errors.extend(configuration_errors)
    startup_errors, startup = inspect_serializer_startup(
        sdf.read_text(encoding="utf-8", errors="replace"),
        routed_netlist.read_text(encoding="utf-8", errors="replace"), ddr_audit, sdc)
    errors.extend(startup_errors)
    pll_init_errors, pll_init_audit = inspect_video_pll_init(
        sdf.read_text(encoding="utf-8", errors="replace"),
        routed_netlist.read_text(encoding="utf-8", errors="replace"), ROOT)
    errors.extend(pll_init_errors)
    project = ET.parse(ROOT / "Prj1.gprj")
    inputs = [ROOT / "Prj1.gprj", ROOT / "scripts" / "build.tcl"]
    inputs += [ROOT / element.attrib["path"] for element in project.findall("./FileList/File")]
    artifact_time = min(path.stat().st_mtime for path in (bitstream, report, sdf, routed_netlist))
    for path in inputs:
        if not path.is_file():
            errors.append(f"project input missing: {path.relative_to(ROOT)}")
        elif path.stat().st_mtime > artifact_time:
            errors.append(f"stale bitstream/report, rebuild after {path.relative_to(ROOT)}")
    logs = [ROOT / "impl" / "gwsynthesis" / "Prj1.log", pnr / "Prj1.log"]
    warnings = []
    for path in logs:
        if not path.is_file():
            errors.append(f"build log missing: {path}")
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if any(re.match(r"ERROR\s*\(", line) for line in lines):
            errors.append(f"build errors in {path}")
        warnings.extend(line for line in lines if re.match(r"WARN\s*\(", line))
    if errors:
        raise SystemExit("FAIL Gowin build:\n- " + "\n- ".join(errors))

    # Write success evidence only after all checks pass. On failure, historical
    # evidence remains identifiable by its original bitstream/input hashes.
    evidence = {
        "bitstream_sha256": hashlib.sha256(bitstream.read_bytes()).hexdigest(),
        "timing_report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
        "sdf_sha256": hashlib.sha256(sdf.read_bytes()).hexdigest(),
        "routed_netlist_sha256": hashlib.sha256(routed_netlist.read_bytes()).hexdigest(),
        "build_checker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "routed_startup_checker_sha256": hashlib.sha256((ROOT / "scripts/check_serializer_startup.py").read_bytes()).hexdigest(),
        "video_pll_init_checker_sha256": hashlib.sha256((ROOT / "scripts/check_video_pll_init.py").read_bytes()).hexdigest(),
        "inputs_sha256": {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in inputs},
        **timing, "serializer_startup_audit": startup, "ddr_configuration_audit": configuration_audit,
        "video_pll_init_audit": pll_init_audit,
        "warnings": warnings, "nominal_video_refresh_hz": 60.0,
        "board_tested": False,
    }
    out = ROOT / "build" / "build_evidence.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(evidence, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    reset_endpoints = len(startup["paths"]) + len(startup["pixel_divider"]["paths"]) + len(startup["ddr_phy"]["paths"])
    print("PASS Gowin build: fresh artifacts, zero reported timing violations, six clocks, active CDC budgets")
    print(f"Routed reset budget: {reset_endpoints} VO/SDF endpoints passed")
    print(f"PLL_INIT controls: {pll_init_audit['dynamic_endpoint_count']} routed endpoints, "
          f"worst {pll_init_audit['maximum_propagation_ns']:.3f} ns / 10 ns budget")
    print(f"Remaining warnings: {len(warnings)}; evidence: {out}")
    print(f"SHA256: {evidence['bitstream_sha256']}")


if __name__ == "__main__":
    check()
