#!/usr/bin/env python3
"""Compile and sample the actual 428x142 RTL renderer; convert its PPM to PNG."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import tempfile
from PIL import Image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    output = (args.output or project / "reports/midi_keyboard_preview.png").resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    ppm = output.with_suffix(".ppm")
    sources = [project / "rtl/display/midi_landscape_view.v",
               project / "sim/tb_midi_landscape_view.v"]
    with tempfile.TemporaryDirectory(prefix="gw25k-midi-preview-") as temp:
        binary = Path(temp) / "view.vvp"
        subprocess.run(["iverilog", "-g2012", "-Wall", "-s", "tb_midi_landscape_view",
                        "-o", str(binary), *map(str, sources)], cwd=project, check=True)
        # Icarus $fopen rejects Unicode paths; rasterize in the ASCII temp path.
        temporary_ppm = Path(temp) / "preview.ppm"
        subprocess.run(["vvp", str(binary), f"+ppm={temporary_ppm}"], cwd=project, check=True)
        ppm.write_bytes(temporary_ppm.read_bytes())
    with Image.open(ppm) as raster:
        if raster.size != (428, 142):
            raise RuntimeError(f"Unexpected raster size: {raster.size}")
        raster.save(output)
        raster.resize((1284, 426), Image.Resampling.NEAREST).save(output.with_name(output.stem + "_3x.png"))
    metadata = {"source": "Icarus pixel-by-pixel sampling of midi_landscape_view RTL; no mock graphics",
                "size": [428, 142], "orientation": "reverse landscape: logical_x=427-native_y, logical_y=native_x",
                "layout": {"strip": "right-side vertical; fills bottom to top", "strip_panel": [384, 29, 419, 126],
                           "strip_track": [392, 43, 411, 112], "main_content_right": 375}, "inputs": {"keys_hex": "0125", "channel": 3, "transpose": -12,
                "velocity": 100, "program": 24, "strip_mode": "BEND", "brightness": 192,
                "strip_value": 166, "focus": "STRIP", "usb": True, "ble": True, "touch": True,
                "slider_chip": {"ready": True, "touched": True, "raw_position": 174,
                                "filtered_position": 166, "general_status_hex": "02",
                                "error_hex": "00", "overrun": False, "sample_count_hex": "7F"}},
                "sha256": {str(p.relative_to(project)): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in sources}, "png_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}
    output.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(output)


if __name__ == "__main__":
    main()
