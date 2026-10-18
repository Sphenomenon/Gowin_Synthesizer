#!/usr/bin/env python3
"""Synthesize the abstract MIDI core in an isolated ASCII directory.

This entry point deliberately does not run PnR or produce a board bitstream.
Synthesis completion is not board I/O validation or 50 MHz timing sign-off.
"""

from __future__ import annotations

import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_IDE = Path("/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE")
LOCK_PATH = Path("/private/tmp/gw25k-build.lock")
TOP = "midi_keyboard_core"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def timestamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def input_files() -> list[Path]:
    """Keep the Tcl source list explicit and ensure it includes all RTL."""
    script = PROJECT / "build_core.tcl"
    text = script.read_text()
    runs = re.findall(r"^\s*run\s+(\S+)\s*$", text, re.MULTILINE)
    if runs != ["syn"]:
        raise ValueError("build_core.tcl must contain exactly one run syn and no other run phase")
    names = re.findall(r"^\s*add_file\s+(\S+)\s*$", text, re.MULTILINE)
    sources = [PROJECT / name for name in names]
    if len(sources) != len(set(sources)):
        raise ValueError("build.tcl contains duplicate sources")
    if any(not source.is_file() or source.suffix != ".v" for source in sources):
        raise ValueError("build_core.tcl must list existing core RTL sources")
    if len(sources) != 7:
        raise ValueError("expected seven framework RTL files; review build.tcl when changing the core")
    if not re.search(r"^set_option\s+-disable_io_insertion\s+1\s*$", text, re.MULTILINE):
        raise ValueError("abstract core synthesis requires -disable_io_insertion 1")
    return [script, PROJECT / "build_core.sh", Path(__file__).resolve(), *sources]


def write_manifest(path: Path, manifest: dict) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def main() -> int:
    # Share the existing board examples' process lock and fail without touching
    # reports if another compiler owns it. No parallel Gowin license processes.
    with LOCK_PATH.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another GW25K build is active; synthesis was not started.", file=sys.stderr)
            return 1
        return synthesize()


def synthesize() -> int:
    reports = PROJECT / "reports"
    reports.mkdir(exist_ok=True)
    manifest_path = reports / "synthesis.json"
    saved_log = reports / "synthesis.log"
    ide = Path(os.environ.get("GW25K_IDE_DIR", str(DEFAULT_IDE))).expanduser().resolve()
    executable = ide / "bin/gw_sh"
    manifest = {
        "schema_version": 1,
        "started_at": timestamp(),
        "phase": "synthesis_only",
        "top_module": TOP,
        "device": "GW5A-LV25MG121NC1/I0",
        "target_clock_hz": 50000000,
        "io_insertion_disabled": True,
        "passed": False,
        "tool_returncode": None,
        "synthesis_confirmed": False,
        "place_and_route_run": False,
        "timing_signed_off": False,
        "bitstream_generated": False,
        "downloadable": False,
        "tool": str(executable),
        "log": "reports/synthesis.log",
        "inputs": [],
        "artifacts": [],
        "limitations": "Abstract core synthesis only: no board top, physical constraints, PnR, timing sign-off, USB/BLE hardware integration or bitstream.",
    }
    stage = None
    exit_code = 1
    try:
        files = input_files()
        # Copy only immutable snapshots of declared inputs, excluding old output
        # directories. Their hashes describe precisely what this run consumed.
        stage = Path(tempfile.mkdtemp(prefix="gw25k-midi-syn-", dir="/private/tmp"))
        manifest["stage_directory"] = str(stage)
        for source in files:
            relative = source.relative_to(PROJECT)
            destination = stage / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            manifest["inputs"].append({"path": relative.as_posix(), "sha256": sha256(destination)})
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise FileNotFoundError(f"Gowin gw_sh not executable: {executable}; set GW25K_IDE_DIR")
        manifest["tool_sha256"] = sha256(executable)
        print(f"ASCII synthesis directory: {stage}", flush=True)
        print("Running synthesis only; no PnR or board bitstream.", flush=True)
        write_manifest(manifest_path, manifest)
        environment = dict(os.environ, DYLD_LIBRARY_PATH=str(ide / "lib"),
                           DYLD_FRAMEWORK_PATH=str(ide / "lib"))
        with saved_log.open("w") as output:
            result = subprocess.run([str(executable), str(stage / "build_core.tcl")],
                                    cwd=stage, env=environment, stdout=output,
                                    stderr=subprocess.STDOUT, check=False)
        manifest["tool_returncode"] = result.returncode
        output_text = saved_log.read_text(errors="replace")
        complete = "GowinSynthesis finish" in output_text
        manifest["synthesis_completion_marker"] = complete
        manifest["warning_count"] = len(re.findall(r"^\s*WARN\b", output_text, re.MULTILINE))
        error_lines = re.findall(r"^\s*(?:ERROR\b|Error:).*", output_text, re.MULTILINE)
        if result.returncode != 0 or error_lines:
            raise RuntimeError(f"Gowin synthesis failed (return code {result.returncode}); inspect reports/synthesis.log")
        if not complete:
            raise RuntimeError("Gowin did not report synthesis completion")
        if (stage / "impl/pnr").exists() or list(stage.rglob("*.fs")):
            raise RuntimeError("Unexpected PnR/bitstream output in synthesis-only run; refusing to report success")
        synthesized = stage / "impl/gwsynthesis"
        netlist = synthesized / f"{TOP}.vg"
        if not netlist.is_file() or netlist.stat().st_size == 0:
            raise RuntimeError("No fresh synthesized midi_keyboard_core netlist was produced")
        if not re.search(r"\bmodule\s+" + TOP + r"\s*\(", netlist.read_text(errors="replace")):
            raise RuntimeError("Synthesized netlist does not contain the actual application core top")
        # Keep compiler evidence beside the manifest; these are netlists and
        # synthesis reports, never downloadable images or a PnR timing result.
        for source in sorted(synthesized.iterdir()):
            if source.suffix not in (".vg", ".html", ".xml"):
                continue
            destination = reports / source.name
            shutil.copy2(source, destination)
            manifest["artifacts"].append({
                "path": destination.relative_to(PROJECT).as_posix(),
                "sha256": sha256(destination),
                "kind": "synthesis_netlist" if source.suffix == ".vg" else "synthesis_report",
                "downloadable": False,
            })
        manifest["synthesis_confirmed"] = True
        manifest["passed"] = True
        exit_code = 0
    except (OSError, ValueError, RuntimeError) as error:
        manifest["error"] = str(error)
        if manifest["tool_returncode"] is None:
            saved_log.write_text(f"Synthesis was not completed: {error}\n")
        print(str(error), file=sys.stderr, flush=True)
        if stage:
            print(f"Diagnostic stage retained at {stage}", file=sys.stderr, flush=True)
    finally:
        manifest["finished_at"] = timestamp()
        manifest["log_sha256"] = sha256(saved_log) if saved_log.is_file() else None
        write_manifest(manifest_path, manifest)
    if manifest["passed"]:
        print("Synthesis confirmed. No PnR, timing sign-off, bitstream, or hardware validation.", flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
