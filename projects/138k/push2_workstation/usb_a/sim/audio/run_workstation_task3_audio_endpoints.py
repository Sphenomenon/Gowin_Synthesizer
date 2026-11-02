#!/usr/bin/env python3
"""Small logical audio-endpoint composition, using actual maintained owners."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = [
        "rtl/workstation/workstation_task3_final_tap_export.sv",
        "rtl/workstation/workstation_task3_phone_command_ingress.sv",
        "rtl/workstation/workstation_task3_record_ingress.sv",
        "rtl/audio/workstation_ae350_pcm_owner.sv",
    ]
    extra_sources = [
        "rtl/workstation/workstation_task3_audio_exchange.sv",
        "rtl/workstation/workstation_task3_phone_command_proxy.sv",
        "rtl/workstation/workstation_task3_phone_command_mux.sv",
        "rtl/services/workstation_audio_clock_service.sv",
    ]
    suites = [
        ("audio_endpoints", 281, "PASS task3 audio endpoint logical composition checks=281 captured_physical=16 real_pcm_frames=256", sources),
        ("audio_exchange", 283, "PASS task3 audio exchange composition checks=283 final_tap_frames=16 remote_pcm_frames=256 clock_target=real", sources + extra_sources),
    ]
    paths = sources + extra_sources + [f"sim/audio/tb_workstation_task3_{name}.sv" for name, *_ in suites]
    paths.append("sim/audio/run_workstation_task3_audio_endpoints.py")
    before = {p: sha(root / p) for p in paths}
    outcomes = []
    suite_results = []
    for name, checks, expected, compile_sources in suites:
        top = f"tb_workstation_task3_{name}"
        binary = output / f"{name}.vvp"
        commands = [
            ["iverilog", "-g2012", "-s", top, "-o", str(binary), f"sim/audio/{top}.sv", *compile_sources],
            ["vvp", str(binary)],
        ]
        completed = True
        for number, command in enumerate(commands):
            result = subprocess.run(command, cwd=root, capture_output=True, text=True)
            log = output / (f"{name}_build.log" if number == 0 else f"{name}_run.log")
            log.write_text(result.stdout + result.stderr)
            outcomes.append({"suite": name, "argv": command, "returncode": result.returncode, "log": str(log), "log_sha256": sha(log)})
            if result.returncode:
                completed = False
                break
        suite_passed = completed and expected in (output / f"{name}_run.log").read_text()
        suite_results.append({"name": name, "passed": suite_passed, "checks": checks if suite_passed else 0})
    unchanged = before == {p: sha(root / p) for p in paths}
    passed = all(x["passed"] for x in suite_results) and unchanged
    report = {
        "schema": 2, "passed": passed, "source_unchanged": unchanged,
        "inputs_sha256": before, "invocations": outcomes, "suites": suite_results,
        "scope": "same-clock complete logical audio exchange and separate endpoints with actual maintained recording ingress, PCM1 owner and M clock service",
        "checks": sum(x["checks"] for x in suite_results), "physical_completion_fixture_frames_per_suite": 16, "pcm1_committed_frames_per_suite": 256,
        "covered": ["ordered tap payload and explicit remote arm ACK", "PCM1 descriptor/RAM/select/sample advance", "real M clock service target and held-address predecode", "W PCM/clock caller arbitration and matched responses", "stale request boot rejection", "disconnect queue discard", "tap overflow failure", "bounded owner timeout", "immediate PANIC revocation", "corrupted response boot rejection and remote cancellation", "missing remote return timeout and remote cancellation"],
        "not_verified": ["LCD pins/electrical/CDC/packet CRC", "physical M serializer or DAC", "W real HCI/SBC producer", "D DSP or final master gain", "physical 44.1k clock switching/barrier", "60-second raw DDR capture or BLE download", "whole-board profile integration or resource/timing"],
    }
    (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"passed": passed, "verification": str(output / "verification.json")}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
