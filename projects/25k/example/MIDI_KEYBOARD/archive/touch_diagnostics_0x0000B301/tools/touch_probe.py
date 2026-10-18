#!/usr/bin/env python3
"""Read touch diagnostics over the keyboard's USB vendor bulk interface.

Uses Python's standard library and libusb only. ``status`` and ``capture``
perform read-only requests. Only ``pause 0|1`` changes U2 acquisition state.
"""

from __future__ import annotations

import argparse
import csv
import ctypes as ct
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any

try:
    from . import screen_control as protocol
except ImportError:
    import screen_control as protocol


VID = 0xFB9A
PID = 0xFB9B
INTERFACE = 2
EP_OUT = 0x02
EP_IN = 0x82
FORMAT_ID = 0x54430101
DEFAULT_LIBRARY = "/opt/homebrew/lib/libusb-1.0.dylib"


class ProbeError(RuntimeError):
    """A USB transport, protocol, or diagnostic consistency failure."""


class UsbProbe:
    """A single claimed interface; all request/response pairs are synchronous."""

    def __init__(self, library: str = DEFAULT_LIBRARY, timeout_ms: int = 1000):
        self.library = library
        self.timeout_ms = timeout_ms
        self.sequence = 0
        self.context = ct.c_void_p()
        self.handle: int | None = None
        self.claimed = False
        self.lib: Any = None

    def __enter__(self) -> "UsbProbe":
        try:
            self.lib = ct.CDLL(self.library)
            declarations = {
                "libusb_init": ([ct.POINTER(ct.c_void_p)], ct.c_int),
                "libusb_exit": ([ct.c_void_p], None),
                "libusb_open_device_with_vid_pid":
                    ([ct.c_void_p, ct.c_uint16, ct.c_uint16], ct.c_void_p),
                "libusb_claim_interface": ([ct.c_void_p, ct.c_int], ct.c_int),
                "libusb_release_interface": ([ct.c_void_p, ct.c_int], ct.c_int),
                "libusb_close": ([ct.c_void_p], None),
                "libusb_bulk_transfer": ([ct.c_void_p, ct.c_ubyte,
                    ct.POINTER(ct.c_ubyte), ct.c_int, ct.POINTER(ct.c_int),
                    ct.c_uint], ct.c_int),
                "libusb_error_name": ([ct.c_int], ct.c_char_p),
            }
            for name, (arguments, result) in declarations.items():
                function = getattr(self.lib, name)
                function.argtypes = arguments
                function.restype = result
            self._check(self.lib.libusb_init(ct.byref(self.context)), "initialize libusb")
            self.handle = self.lib.libusb_open_device_with_vid_pid(self.context, VID, PID)
            if not self.handle:
                raise ProbeError(f"USB {VID:04x}:{PID:04x} not found or cannot be opened")
            self._check(self.lib.libusb_claim_interface(self.handle, INTERFACE),
                        f"claim interface {INTERFACE}")
            self.claimed = True
            return self
        except BaseException:
            self.close()
            raise

    def _check(self, result: int, operation: str) -> None:
        if result < 0:
            name = self.lib.libusb_error_name(result)
            label = name.decode("ascii", errors="replace") if name else str(result)
            raise ProbeError(f"{operation}: {label} ({result})")

    def close(self) -> None:
        """Release resources, including after timeouts, signals, or bad frames."""
        if self.handle:
            try:
                if self.claimed:
                    result = self.lib.libusb_release_interface(self.handle, INTERFACE)
                    if result < 0:
                        print(f"warning: release interface returned {result}", file=sys.stderr)
            finally:
                self.claimed = False
                self.lib.libusb_close(self.handle)
                self.handle = None
        if self.context.value:
            self.lib.libusb_exit(self.context)
            self.context = ct.c_void_p()

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    def request(self, opcode: int, arg0: int = 0) -> int:
        sequence = self.sequence
        self.sequence = (sequence + 1) & 0xFFFF
        payload = protocol.encode_request(opcode, sequence, arg0)
        outgoing = (ct.c_ubyte * len(payload)).from_buffer_copy(payload)
        transferred = ct.c_int()
        self._check(self.lib.libusb_bulk_transfer(self.handle, EP_OUT, outgoing,
                    len(payload), ct.byref(transferred), self.timeout_ms), "bulk OUT")
        if transferred.value != len(payload):
            raise ProbeError(f"short bulk OUT: {transferred.value}/{len(payload)} bytes")
        incoming = (ct.c_ubyte * protocol.FRAME_SIZE)()
        transferred.value = 0
        self._check(self.lib.libusb_bulk_transfer(self.handle, EP_IN, incoming,
                    len(incoming), ct.byref(transferred), self.timeout_ms), "bulk IN")
        if transferred.value != protocol.FRAME_SIZE:
            raise ProbeError(f"short bulk IN: {transferred.value}/{protocol.FRAME_SIZE} bytes")
        try:
            response = protocol.decode_frame(bytes(incoming))
        except (ValueError, TypeError) as error:
            raise ProbeError(f"invalid response: {error}") from error
        if response.opcode != (opcode | 0x80):
            raise ProbeError(f"response opcode 0x{response.opcode:02x}, expected 0x{opcode | 0x80:02x}")
        if response.sequence != sequence:
            raise ProbeError(f"response sequence {response.sequence}, expected {sequence}")
        if response.arg0 != 0:
            raise ProbeError(f"device rejected request: {protocol.STATUSES[response.arg0]}")
        return response.arg1

    def read_words(self, attempts: int = 20) -> tuple[list[int], int]:
        # Words 0/1/2/3 are an atomic published U1 group. Words 4/5 can
        # change independently even if the U1 frame counter remains unchanged.
        for attempt in range(attempts):
            before = self.request(protocol.GET_TOUCH, 6)
            words = [self.request(protocol.GET_TOUCH, index) for index in range(4)]
            after = self.request(protocol.GET_TOUCH, 6)
            if before == after:
                words.extend((self.request(protocol.GET_TOUCH, 4),
                              self.request(protocol.GET_TOUCH, 5), before,
                              self.request(protocol.GET_TOUCH, 7)))
                if words[7] != FORMAT_ID:
                    raise ProbeError(f"unsupported touch format 0x{words[7]:08x}; expected 0x{FORMAT_ID:08x}")
                return words, attempt
        raise ProbeError(f"no coherent U1 frame after {attempts} attempts")


def decode_words(words: list[int]) -> dict[str, int]:
    """Decode published format 1/revision 1 without touching USB."""
    if len(words) != 8 or any(type(word) is not int or not 0 <= word <= 0xFFFFFFFF
                              for word in words):
        raise ValueError("expected eight uint32 diagnostic words")
    if words[7] != FORMAT_ID:
        raise ValueError(f"unsupported touch format 0x{words[7]:08x}")
    result = {f"word{index}": word for index, word in enumerate(words)}
    accepted = words[0] & 0xFFFF
    before, after = words[1] & 0xFFFF, words[1] >> 16
    result.update(accepted_bitmap=accepted, key_sample_count=(words[0] >> 16) & 0xFF,
                  key_general_status=words[0] >> 24,
                  raw_detect_before=before, raw_detect_after=after,
                  slider_raw=words[4] & 0xFF, slider_filtered=(words[4] >> 8) & 0xFF,
                  slider_general_status=(words[4] >> 16) & 0xFF,
                  slider_sample_count=words[4] >> 24,
                  flags=words[5], key_error=(words[5] >> 8) & 0xFF,
                  slider_error=(words[5] >> 16) & 0xFF, frame_sequence=words[6])
    for key, word, channel in (("g", words[2], 9), ("h", words[3], 15)):
        signal, reference = word & 0xFFFF, word >> 16
        result.update({f"{key}_signal": signal, f"{key}_reference": reference,
                       f"{key}_delta": reference - signal,
                       f"{key}_detect_before": (before >> channel) & 1,
                       f"{key}_detect_after": (after >> channel) & 1,
                       f"{key}_accepted": (accepted >> channel) & 1})
    for bit, name in enumerate(("keypad_ready", "slider_ready", "slider_touched",
                                "pause_requested", "pause_acknowledged",
                                "slider_overflow", "keypad_overflow")):
        result[name] = (words[5] >> bit) & 1
    return result


def snapshot(probe: UsbProbe) -> dict[str, Any]:
    started = probe.sequence
    words, retries = probe.read_words()
    return {"timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "request_sequence_start": started,
            "request_sequence_end": (probe.sequence - 1) & 0xFFFF,
            "coherence_retries": retries, **decode_words(words)}


def capture(probe: UsbProbe, seconds: float, period_ms: float, output: Path) -> int:
    """Save each completed snapshot immediately; preserve partial data on failure."""
    output.parent.mkdir(parents=True, exist_ok=True)
    summary_path = output.with_suffix(".summary.json")
    if summary_path == output:
        raise ValueError("CSV output path must not end in .summary.json")
    start = time.monotonic()
    summary: dict[str, Any] = {
        "csv": str(output.resolve()), "requested_seconds": seconds,
        "requested_period_ms": period_ms, "samples": 0, "error": None,
        "g_accepted_samples": 0, "h_accepted_samples": 0,
        "g_detect_samples": 0, "h_detect_samples": 0,
        "slider_touched_samples": 0, "coherence_retries": 0,
        "note": "Word 0/1/2/3 share a U1 frame; word 4/5 are independently sampled. "
                "Delta is reference minus signal. No automatic threshold or calibration writes.",
    }
    exit_code = 0
    try:
        with output.open("w", newline="", encoding="utf-8") as stream:
            writer = None
            deadline = start
            while time.monotonic() - start < seconds:
                row = snapshot(probe)
                row = {"elapsed_seconds": round(time.monotonic() - start, 6), **row}
                if writer is None:
                    writer = csv.DictWriter(stream, fieldnames=list(row))
                    writer.writeheader()
                writer.writerow(row)
                stream.flush()
                summary["samples"] += 1
                summary["coherence_retries"] += row["coherence_retries"]
                for key in ("g", "h"):
                    summary[f"{key}_accepted_samples"] += row[f"{key}_accepted"]
                    summary[f"{key}_detect_samples"] += int(bool(
                        row[f"{key}_detect_before"] or row[f"{key}_detect_after"]))
                    for suffix, function in (("min", min), ("max", max)):
                        name = f"{key}_delta_{suffix}"
                        summary[name] = function(summary.get(name, row[f"{key}_delta"]),
                                                 row[f"{key}_delta"])
                summary["slider_touched_samples"] += row["slider_touched"]
                deadline += period_ms / 1000
                # Skip missed slots rather than issuing a burst of requests.
                now = time.monotonic()
                if deadline < now:
                    deadline = now
                delay = min(deadline, start + seconds) - now
                if delay > 0:
                    time.sleep(delay)
    except (ProbeError, OSError, ValueError, KeyboardInterrupt) as error:
        summary["error"] = "interrupted" if isinstance(error, KeyboardInterrupt) else str(error)
        exit_code = 130 if isinstance(error, KeyboardInterrupt) else 1
    finally:
        summary["elapsed_seconds"] = round(time.monotonic() - start, 6)
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
                                encoding="utf-8")
    print(json.dumps({"csv": str(output.resolve()), "summary": str(summary_path.resolve()),
                      **summary}, ensure_ascii=False))
    return exit_code


def set_pause(probe: UsbProbe, value: int, wait_seconds: float) -> None:
    accepted = probe.request(protocol.SET_TOUCH_TEST, value)
    if accepted != value:
        raise ProbeError(f"pause response accepted {accepted}, expected {value}")
    print(json.dumps({"pause_request_accepted": accepted,
                      "note": "Waiting for hardware acknowledgment"}), flush=True)
    deadline = time.monotonic() + wait_seconds
    last_flags = 0
    while True:
        last_flags = probe.request(protocol.GET_TOUCH, 5)
        actual = (last_flags >> 4) & 1
        requested = (last_flags >> 3) & 1
        ready = (last_flags >> 1) & 1
        error = (last_flags >> 16) & 0xFF
        if requested == value and actual == value and (value == 1 or ready == 1) and error == 0:
            print(json.dumps({"pause_acknowledged": actual, "pause_requested": requested,
                              "slider_ready": ready, "flags": last_flags}), flush=True)
            return
        if time.monotonic() >= deadline:
            raise ProbeError(f"pause/resume not confirmed after {wait_seconds:g}s; word5=0x{last_flags:08x}")
        time.sleep(0.04)


def positive_number(text: str) -> float:
    try:
        value = float(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected a positive finite number") from error
    if not 0 < value < float("inf"):
        raise argparse.ArgumentTypeError("expected a positive finite number")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", default=DEFAULT_LIBRARY, help="libusb shared library path")
    parser.add_argument("--timeout-ms", type=int, default=1000, help="each USB transfer timeout (default: 1000)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="read all eight diagnostic words with U1 frame consistency check")
    recording = commands.add_parser("capture", help="record read-only snapshots to CSV and a JSON summary")
    recording.add_argument("--seconds", type=positive_number, required=True)
    recording.add_argument("--period-ms", type=positive_number, default=40)
    recording.add_argument("--output", type=Path, required=True, help="CSV destination; summary uses .summary.json")
    pause = commands.add_parser("pause", help="request U2 acquisition pause (1) or normal acquisition (0)")
    pause.add_argument("value", type=int, choices=(0, 1))
    pause.add_argument("--wait-seconds", type=positive_number, default=5)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not 1 <= args.timeout_ms <= 60000:
        parser.error("--timeout-ms must be in 1..60000")
    try:
        with UsbProbe(args.library, args.timeout_ms) as probe:
            if args.command == "status":
                print(json.dumps(snapshot(probe), indent=2, ensure_ascii=False))
            elif args.command == "capture":
                return capture(probe, args.seconds, args.period_ms, args.output)
            else:
                set_pause(probe, args.value, args.wait_seconds)
    except (ProbeError, OSError, ValueError) as error:
        print(f"touch_probe: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
