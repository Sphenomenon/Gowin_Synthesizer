#!/usr/bin/env python3
"""Native ASAN/UBSAN regression of the production GW25K PL/MIDI host.

No USB access. The test compiles firmware.c and gw25k_panel.h unchanged, with
only USB transactions, time and MMIO replaced by a deterministic device mock.
Optionally pass --output PATH to preserve logs and exact input hashes there.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import select
import shutil
import struct
import subprocess
import tempfile
import zlib


def png_from_ppm(source: Path, target: Path) -> None:
    pixels = source.read_bytes().split(b"\n255\n", 1)[1]
    width, height = 428, 142
    assert len(pixels) == width * height * 3
    scan = b"".join(b"\0" + pixels[y * width * 3:(y + 1) * width * 3] for y in range(height))
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    target.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                       + chunk(b"IDAT", zlib.compress(scan, 9)) + chunk(b"IEND", b""))


def rtl_exchange(binary: Path, helper: list[str], output: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    def line_from(pipe) -> str:
        if not select.select([pipe], [], [], 15)[0]:
            raise TimeoutError("host/RTL response timed out")
        line = pipe.readline()
        if not line:
            raise RuntimeError("host/RTL exited during transaction")
        return line.rstrip("\r\n")
    with (output / "rtl_host.stderr.log").open("w") as he, (output / "rtl_endpoint.stderr.log").open("w") as de:
        host = subprocess.Popen([str(binary), "--rtl"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=he, text=True, bufsize=1)
        device = subprocess.Popen(helper, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=de, text=True, bufsize=1)
        try:
            while True:
                line = line_from(host.stdout)
                if line.startswith("PASS "):
                    (output / "rtl_exchange.log").write_text(line + "\n")
                    print(line)
                    break
                prefix, manual, wire = line.split(" ", 2)
                assert prefix == "PL"
                kind = wire[6:8]
                counts[kind] = counts.get(kind, 0) + 1
                device.stdin.write("M " + manual + "\n"); device.stdin.flush()
                assert line_from(device.stdout) == "OK"
                octets = " ".join(wire[i:i + 2] for i in range(0, len(wire), 2))
                device.stdin.write("X " + str(len(wire) // 2) + " " + octets + "\n"); device.stdin.flush()
                reply = line_from(device.stdout)
                host.stdin.write(reply + "\n"); host.stdin.flush()
            assert host.wait(timeout=15) == 0
            device.stdin.write("Q\n"); device.stdin.flush()
            assert device.wait(timeout=15) == 0
        finally:
            for process in (host, device):
                if process.poll() is None:
                    process.kill();process.wait()
    for kind in ("01", "02", "20", "21"):
        assert counts.get(kind, 0)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compiler", default="cc")
    parser.add_argument("--endpoint-rtl", type=Path, help="Actual GW25K rtl/control/panel_display_endpoint.v for closed-loop cross-project regression")
    args = parser.parse_args()
    sim = Path(__file__).resolve().parent
    root = sim.parent
    output = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix="gw25k-panel-"))
    output.mkdir(parents=True, exist_ok=True)
    stage = output / "source"
    (stage / "sim").mkdir(parents=True, exist_ok=True)
    vendor = root / "vendor/usb_host_fs_8fc3/firmware"
    headers = [vendor / "minlibc.h", *sorted((vendor / "usb").glob("*.h"))]
    staged_inputs: dict[Path, Path] = {}
    for name in ("firmware.c", "gw25k_panel.h"):
        shutil.copy2(root / name, stage / name)
        staged_inputs[root / name] = stage / name
    for name in ("test_gw25k_panel.c", "test_generic_midi.c", "test_hotplug.c", "run_gw25k_panel.py"):
        shutil.copy2(sim / name, stage / "sim" / name)
        staged_inputs[sim / name] = stage / "sim" / name
    driver = sim / "tb_gw25k_panel_endpoint.v"
    shutil.copy2(driver, stage / "sim" / driver.name)
    staged_inputs[driver] = stage / "sim" / driver.name
    endpoint = None
    if args.endpoint_rtl:
        endpoint = stage / "panel_display_endpoint.v"
        shutil.copy2(args.endpoint_rtl.resolve(), endpoint)
        staged_inputs[args.endpoint_rtl.resolve()] = endpoint
    staged_headers = stage / "headers"
    staged_headers.mkdir(exist_ok=True)
    for path in headers:
        shutil.copy2(path, staged_headers / path.name)
        staged_inputs[path] = staged_headers / path.name
    hashes = {str(source.relative_to(root) if source.is_relative_to(root) else source): hashlib.sha256(copy.read_bytes()).hexdigest()
              for source, copy in staged_inputs.items()}
    binary = output / "test_gw25k_panel"
    command = [args.compiler, "-std=c99", "-O1", "-g", "-Wall", "-Wextra",
               "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
               "-I" + str(staged_headers),
               str(stage / "sim/test_gw25k_panel.c"), "-o", str(binary)]
    passed = False
    rtl_counts = None
    try:
        with (output / "compile.log").open("w") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        with (output / "test.log").open("w") as log:
            subprocess.run([str(binary)], stdout=log, stderr=subprocess.STDOUT, check=True)
        print((output / "test.log").read_text(), end="")
        for name in ("generic_midi", "hotplug"):
            regression_binary = output / name
            regression_command = command[:-3] + [str(stage / "sim" / ("test_" + name + ".c")), "-o", str(regression_binary)]
            with (output / (name + "_compile.log")).open("w") as log:
                subprocess.run(regression_command, stdout=log, stderr=subprocess.STDOUT, check=True)
            with (output / (name + "_test.log")).open("w") as log:
                subprocess.run([str(regression_binary)], stdout=log, stderr=subprocess.STDOUT, check=True)
            print((output / (name + "_test.log")).read_text(), end="")
        subprocess.run([str(binary), "--render", str(output / "renderer.ppm")], check=True)
        png_from_ppm(output / "renderer.ppm", output / "renderer.png")
        if endpoint:
            rtl_command = ["iverilog", "-g2012", "-s", "tb_gw25k_panel_endpoint",
                           "-o", str(output / "endpoint.vvp"), str(endpoint), str(stage / "sim" / driver.name)]
            with (output / "rtl_compile.log").open("w") as log:
                subprocess.run(rtl_command, stdout=log, stderr=subprocess.STDOUT, check=True)
            rtl_counts = rtl_exchange(binary, ["vvp", str(output / "endpoint.vvp")], output)
        passed = True
    finally:
        (output / "verification.json").write_text(json.dumps({
            "passed": passed, "hardware_tested": False,
            "scope": "production firmware PL screen/MIDI output against streaming USB mock",
            "inputs": hashes, "compile_command": command,
            "actual_endpoint_rtl": bool(endpoint), "rtl_request_counts": rtl_counts,
            "existing_generic_and_push_hotplug": True,
        }, indent=2) + "\n")
        print(output)
        if not passed:
            for name in ("compile.log", "test.log", "rtl_compile.log", "rtl_host.stderr.log", "rtl_endpoint.stderr.log"):
                path = output / name
                if path.exists():
                    print(path.read_text()[-12000:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
