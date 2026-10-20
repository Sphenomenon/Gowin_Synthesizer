#!/usr/bin/env python3
"""Validate the complete MIDI board sources, protocols and behavioral tests.

All HDL paths are relative and every process runs from this project root.
Executables live in a temporary directory while firmware paths stay relative
to the project. New reports go to results/ by default, preserving imported evidence.
Gowin I/O models are simulation-only. This runner performs no FPGA download.
"""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time


PROJECT = Path(__file__).resolve().parents[1]
INCLUDE_FLAGS = ["-I", "rtl/usb_board/vendor", "-I", "."]
IO_MODELS = "sim/gowin_io_models.v"
REFERENCE = "vendor/qt2160_reference"
PANEL_REFERENCE = "vendor/gowin_panel_interface"
REFERENCE_FIRMWARE = [
    "../RTL8723DS_BLE/vendor/rtl8723ds_ble/firmware/rtl8723ds_fw.bin",
    "../RTL8723DS_BLE/vendor/rtl8723ds_ble/firmware/rtl8723ds_config.bin",
]


def now():
    return datetime.datetime.now().astimezone().isoformat()


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def input_names():
    """Hash complete RTL/ROM, constraints, configs, tests and build tooling."""
    names = {"sources.f", "build.tcl", "build.sh", "run_sim.sh"}
    for directory in ("rtl", "constraints", "config", "sim", "tools", REFERENCE, PANEL_REFERENCE):
        for path in (PROJECT / directory).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                names.add(path.relative_to(PROJECT).as_posix())
    names.update(REFERENCE_FIRMWARE)
    return sorted(names)


def source_names():
    names = []
    for line in (PROJECT / "sources.f").read_text().splitlines():
        name = line.split("#", 1)[0].strip()
        if not name:
            continue
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("sources.f must use project-relative HDL paths: " + name)
        if not (PROJECT / name).is_file():
            raise ValueError("Missing sources.f entry: " + name)
        names.append(name)
    if len(names) != len(set(names)):
        raise ValueError("sources.f contains duplicate entries")
    actual = {path.relative_to(PROJECT).as_posix() for path in (PROJECT / "rtl").rglob("*.v")}
    if set(names) != actual:
        raise ValueError("sources.f differs from all rtl/*.v: missing=" +
                         str(sorted(actual - set(names))) + " extra=" + str(sorted(set(names) - actual)))
    if IO_MODELS in names:
        raise ValueError("Simulation-only Gowin models must not enter synthesis sources.f")
    return names


def discover_tests():
    tests = []
    for path in sorted((PROJECT / "sim").glob("tb_*.v")):
        # Shared slave models deliberately have no top matching their filename.
        if re.search(r"\bmodule\s+" + re.escape(path.stem) + r"\b", path.read_text()):
            tests.append(path.stem)
    if not tests:
        raise ValueError("No HDL testbenches discovered")
    return tests


def verify_reference(reference=REFERENCE):
    root = PROJECT / reference
    entries = []
    for number, line in enumerate((root / "MANIFEST_SHA256.txt").read_text().splitlines(), 1):
        if not line.strip():
            continue
        match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?(.+)", line.strip())
        if not match:
            raise ValueError("Invalid reference manifest line " + str(number))
        expected, name = match.groups()
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe reference manifest path: " + name)
        path = root / relative
        if not path.is_file() or sha256(path) != expected.lower():
            raise ValueError("Original reference checksum mismatch: " + reference + "/" + name)
        entries.append(name)
    if not entries or len(entries) != len(set(entries)):
        raise ValueError("Reference manifest is empty or duplicated")
    return {"manifest": reference + "/MANIFEST_SHA256.txt", "verified_files": len(entries)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='New evidence directory; default results/checks_TIMESTAMP')
    args = parser.parse_args()
    reports = args.output.resolve() if args.output else PROJECT / 'results' / datetime.datetime.now().strftime('checks_%Y%m%d_%H%M%S_%f')
    reports.mkdir(parents=True, exist_ok=True)
    print(reports, flush=True)
    os.chdir(PROJECT)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    manifest = {
        "schema_version": 2,
        "started_at": now(),
        "scope": "complete midi_keyboard_top Verilog-2005 elaboration and behavioral/protocol regression",
        "top_module": "midi_keyboard_top",
        "simulation_models": IO_MODELS,
        "working_directory": str(PROJECT),
        "hardware_validated": False,
        "passed": False,
        "checks": [],
        "sha256": {},
    }
    log_lines, failures = [], []

    def record(name, ok, details=None):
        entry = {"name": name, "returncode": 0 if ok else 1}
        if details is not None:
            entry["details"] = details
        manifest["checks"].append(entry)
        if not ok:
            failures.append(name)
        return ok

    def run(name, command, require_pass=False, timeout=240):
        print(name, flush=True)
        started = time.monotonic()
        output, returncode = "", 1
        try:
            result = subprocess.run(command, cwd=PROJECT, env=env, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    timeout=timeout, check=False)
            output, returncode = result.stdout, result.returncode
        except subprocess.TimeoutExpired as error:
            partial = error.stdout or ""
            output = partial.decode(errors="replace") if isinstance(partial, bytes) else partial
            output += "\nRunner timeout after " + str(timeout) + " seconds.\n"
            returncode = 124
        except OSError as error:
            output = str(error) + "\n"
            returncode = 127
        log_lines.extend(["$ " + shlex.join(map(str, command)), output])
        if output:
            print(output, end="" if output.endswith("\n") else "\n", flush=True)
        # Icarus can print $error/$readmemh errors and still exit zero. Require
        # a test's own PASS marker and reject diagnostic errors independently.
        diagnostic_error = bool(re.search(r"(?m)^\s*(?:ERROR:|FATAL:)", output))
        pass_marker = bool(re.search(r"(?m)^\s*PASS(?:\b|:)", output))
        ok = returncode == 0 and not diagnostic_error and (not require_pass or pass_marker)
        manifest["checks"].append({
            "name": name, "command": list(map(str, command)), "returncode": returncode,
            "passed": ok, "elapsed_seconds": round(time.monotonic() - started, 3),
            "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
            "pass_marker_required": require_pass,
        })
        if not ok:
            failures.append(name)
        return ok

    try:
        for tool in ("iverilog", "vvp"):
            if not shutil.which(tool):
                raise RuntimeError(tool + " is required")
        names = input_names()
        manifest["sha256"] = {name: sha256(PROJECT / name) for name in names}
        sources = source_names()
        record("Complete sources.f coverage", True, {"rtl_files": len(sources)})
        configs = sorted((PROJECT / "config").glob("*.json"))
        for path in configs:
            json.loads(path.read_text())
        record("Configuration JSON parsing", True, {"files": len(configs)})
        reference = verify_reference()
        manifest["reference_integrity"] = reference
        record("Original QT2160 manifest checksums", True, reference)
        panel_reference = verify_reference(PANEL_REFERENCE)
        manifest["panel_reference_integrity"] = panel_reference
        record("Original panel interface manifest checksums", True, panel_reference)
        run("Icarus version", ["iverilog", "-V"])
        run("USB descriptor generator --check", [sys.executable, "tools/generate_usb_descriptors.py", "--check"], require_pass=True)
        tests = discover_tests()
        manifest["testbenches"] = tests
        with tempfile.TemporaryDirectory(prefix="gw25k-midi-sim-") as temporary:
            manifest["temporary_executables"] = temporary
            run("Board top elaboration (Verilog-2005)",
                ["iverilog", "-g2005", "-Wall", *INCLUDE_FLAGS, "-s", "midi_keyboard_top",
                 "-tnull", "-c", "sources.f", IO_MODELS])
            for test in tests:
                executable = str(Path(temporary) / test)
                command = ["iverilog", "-g2012", "-Wall", *INCLUDE_FLAGS, "-s", test,
                           "-o", executable, "-c", "sources.f", IO_MODELS, "sim/" + test + ".v"]
                if run(test + " compile", command):
                    run(test, ["vvp", executable], require_pass=True)
                    if test == "tb_ble_board_system":
                        run(test + " wrong-ROM rejection", ["vvp", executable, "+wrong_rom"], require_pass=True)
                if test == "tb_usb_board_device":
                    fs_executable = executable + "_fs"
                    fs_command = command.copy()
                    fs_command[fs_command.index(executable)] = fs_executable
                    fs_command[1:1] = ["-P", "tb_usb_board_device.HIGH_SPEED=0"]
                    if run(test + " full-speed compile", fs_command):
                        run(test + " full-speed", ["vvp", fs_executable], require_pass=True)
            run("Python screen protocol", [sys.executable, "-m", "unittest", "discover",
                                           "-s", "sim", "-p", "test_*.py", "-v"])
        changed = [name for name, digest in manifest["sha256"].items()
                   if not (PROJECT / name).is_file() or sha256(PROJECT / name) != digest]
        changed.extend(sorted(set(input_names()) - set(manifest["sha256"])))
        manifest["inputs_changed_during_run"] = changed
        record("Input hashes stable throughout regression", not changed, changed)
        manifest["passed"] = not failures
    except (RuntimeError, OSError, ValueError) as error:
        manifest["error"] = str(error)
        failures.append(str(error))
        print(error, file=sys.stderr, flush=True)
    finally:
        manifest["failed_checks"] = failures
        manifest["finished_at"] = now()
        log_text = "\n".join(log_lines)
        (reports / "simulation.log").write_text(log_text)
        manifest["log_sha256"] = hashlib.sha256(log_text.encode()).hexdigest()
        (reports / "validation.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    if manifest["passed"]:
        print("PASS complete MIDI regression: " + str(len(manifest.get("testbenches", []))) +
              " testbenches, USB HS/FS, BLE ROM rejection, reference integrity and Python protocol", flush=True)
    else:
        print("FAILED checks: " + "; ".join(failures), file=sys.stderr, flush=True)
    return 0 if manifest["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
