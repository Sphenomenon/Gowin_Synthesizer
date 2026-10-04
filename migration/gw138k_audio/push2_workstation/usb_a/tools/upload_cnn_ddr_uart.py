#!/usr/bin/env python3
"""Load the official CNN model into board DDR and wait for DDR CRC verification."""
import argparse
import binascii
from pathlib import Path
import re
import struct
import time

import serial

ROOT = Path(__file__).resolve().parents[1]
WORDS = 52239
STATUS = re.compile(rb"B138 ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8})")


def model_bytes():
    path = ROOT / "rtl/music/weights/cnn_ddr_blob.mem"
    values = [int(line, 16) for line in path.read_text().splitlines()]
    if len(values) != WORDS or any(value > 0xffff for value in values):
        raise ValueError(f"invalid model blob: {path}, {len(values)} words")
    return struct.pack(f"<{WORDS}H", *values)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/ttyUSB1")
    parser.add_argument("--timeout", type=float, default=45)
    parser.add_argument("--chunk-size", type=int, default=256)
    parser.add_argument("--chunk-pause", type=float, default=0)
    args = parser.parse_args()
    data = model_bytes()
    crc = binascii.crc32(data) & 0xffffffff
    packet = b"BPN1" + data + struct.pack("<I", crc)
    print(f"model={len(data)} bytes crc32={crc:08x} port={args.port}", flush=True)
    with serial.Serial(args.port, 115200, timeout=0.2, write_timeout=10) as port:
        port.reset_input_buffer()
        drain_deadline = time.monotonic() + 3
        while time.monotonic() < drain_deadline and port.read(4096):
            pass
        start = time.monotonic()
        for offset in range(0, len(packet), args.chunk_size):
            port.write(packet[offset:offset + args.chunk_size])
            if args.chunk_pause:
                time.sleep(args.chunk_pause)
        port.flush()
        print(f"sent={len(packet)} bytes elapsed={time.monotonic()-start:.1f}s", flush=True)
        deadline = time.monotonic() + args.timeout
        last_status = None
        last_print = 0.0
        while time.monotonic() < deadline:
            line = port.readline()
            match = STATUS.search(line)
            if not match:
                continue
            sd = int(match.group(4), 16)
            status = (sd >> 2) & 15
            now = time.monotonic()
            if status != last_status or now - last_print >= 5:
                print(f"model_status={status:X} {match.group(0).decode()}", flush=True)
                last_status, last_print = status, now
            # DDR readback can finish before the first 2-Hz status report.
            if status == 14:
                return
            if status == 15:
                raise RuntimeError("board rejected model or DDR readback CRC")
    raise TimeoutError("model DDR readback did not finish")


if __name__ == "__main__":
    main()
