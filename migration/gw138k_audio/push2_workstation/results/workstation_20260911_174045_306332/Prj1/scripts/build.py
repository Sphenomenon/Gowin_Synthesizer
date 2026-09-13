#!/usr/bin/env python3
"""Build a fresh isolated Prj1 snapshot; never overwrite the source tree's impl/build."""
from pathlib import Path
import argparse
from datetime import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys

from gowin_paths import gowin_shell, gowin_simlib
from audit_ddr_reset_sequence import SOURCE as DDR_REFERENCE

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flow", choices=("all", "syn"), default="all")
    parser.add_argument("--gowin-shell")
    parser.add_argument("--simlib", type=Path)
    parser.add_argument("--work-dir", type=Path, help="new, non-existent output directory")
    parser.add_argument("--prepare-only", action="store_true", help="copy inputs for isolated regressions without invoking Gowin")
    args = parser.parse_args()
    work = (args.work_dir or ROOT / "out" / datetime.now().strftime("build_%Y%m%d_%H%M%S_%f")).resolve()
    if work.exists():
        parser.error(f"refusing to overwrite existing output: {work}")
    # Do not permit recursive snapshots or accidentally place output among RTL.
    if work == ROOT or any(path in work.parents for path in (ROOT / name for name in ("src", "vendor", "docs", "scripts", "constraints", "sim", "tools", "build", "impl"))):
        parser.error("work directory must be outside project inputs and historical build/impl")
    shell = None if args.prepare_only else gowin_shell(args.gowin_shell)
    simlib = None if args.prepare_only else gowin_simlib(args.simlib)
    subprocess.run([sys.executable, str(ROOT / "scripts/update_project.py"), "--check"], check=True)
    work.mkdir(parents=True)
    project = work / "Prj1"
    project.mkdir()
    for name in ("Prj1.gprj", "constraints", "src", "vendor", "scripts", "sim", "tools", "docs"):
        source = ROOT / name
        if source.is_dir():
            shutil.copytree(source, project / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(source, project / name)
    reference = work / "reference"
    reference.mkdir()
    for source in (DDR_REFERENCE, DDR_REFERENCE.with_suffix(".v")):
        shutil.copy2(source, reference / source.name)
    inputs = {str(path.relative_to(work)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(work.rglob("*")) if path.is_file()}
    (work / "snapshot.json").write_text(json.dumps({"source": str(ROOT), "inputs_sha256": inputs,
                                                   "board_tested": False}, indent=2) + "\n")
    print(f"Isolated project: {project}", flush=True)
    if args.prepare_only:
        return
    env = dict(os.environ, PRJ1_FLOW=args.flow, GOWIN_SIMLIB=str(simlib),
               PRJ1_DDR_REFERENCE=str(reference / DDR_REFERENCE.name))
    with (work / "gowin.log").open("w", encoding="utf-8") as log:
        result = subprocess.run([str(shell), "scripts/build.tcl"], cwd=project, env=env,
                                stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise SystemExit(f"FAIL Gowin (exit {result.returncode}); see {work / 'gowin.log'}")
    if args.flow == "all":
        result = subprocess.run([sys.executable, "scripts/check_build.py"], cwd=project, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        (work / "check_build.log").write_text(result.stdout, encoding="utf-8")
        print(result.stdout, end="")
        if result.returncode:
            raise SystemExit(result.returncode)
    else:
        print(f"Synthesis finished; place/route and timing not checked. Log: {work / 'gowin.log'}")


if __name__ == "__main__":
    main()
