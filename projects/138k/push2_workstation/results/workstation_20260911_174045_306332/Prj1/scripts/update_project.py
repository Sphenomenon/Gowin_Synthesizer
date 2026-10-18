#!/usr/bin/env python3
"""Regenerate the Gowin source manifest; --check detects unregistered files."""
from pathlib import Path
import argparse
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]

def render():
    project = ET.Element("Project")
    ET.SubElement(project, "Template").text = "FPGA"
    ET.SubElement(project, "Version").text = "5"
    ET.SubElement(project, "Device", name="GW5AST-138C", pn="GW5AST-LV138PG484AC2/I1").text = "gw5ast138c-006"
    files = ET.SubElement(project, "FileList")
    paths = sorted((ROOT / "src").rglob("*.v")) + sorted((ROOT / "vendor").rglob("*.v"))
    paths += sorted((ROOT / "constraints").glob("*.cst")) + sorted((ROOT / "constraints").glob("*.sdc"))
    for path in paths:
        kind = {".v": "verilog", ".cst": "cst", ".sdc": "sdc"}[path.suffix]
        ET.SubElement(files, "File", path=path.relative_to(ROOT).as_posix(), type="file."+kind, enable="1")
    ET.indent(project, space="    ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE gowin-fpga-project>\n' + ET.tostring(project, encoding="unicode") + '\n'

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = ROOT / "Prj1.gprj"
    expected = render()
    if args.check:
        if output.read_text(encoding="utf-8") != expected:
            raise SystemExit("Prj1.gprj is stale; run scripts/update_project.py")
        print("PASS project manifest")
    else:
        output.write_text(expected, encoding="utf-8", newline="\n")
        print(output)
