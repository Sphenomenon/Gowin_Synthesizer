#!/usr/bin/env python3
"""Encode/decode the MIDI keyboard's 16-byte vendor-bulk control frames.

This tool performs no USB I/O. A future USB host adapter must move these bytes
over the vendor bulk interface without text encoding or CDC framing.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import struct
from typing import Any

MAGIC = b"MK"
VERSION = 1
FRAME_SIZE = 16
GET_STATUS = 0x01
GET_TOUCH = 0x02
GET_PLUCK = 0x03
SET_PLUCK_EMITTERS = 0x04
SET_PLUCK_THRESHOLDS = 0x05
GET_PLUCK_NOISE = 0x06
SET_CHANNEL = 0x10
SET_TRANSPOSE = 0x11
SET_PAGE = 0x20
SET_THEME = 0x21
CLEAR = 0x22
OPCODES = {
    GET_STATUS: "status", GET_TOUCH: "touch", GET_PLUCK: "pluck", SET_PLUCK_EMITTERS: "pluck-emitters",
    SET_PLUCK_THRESHOLDS: "pluck-thresholds", SET_CHANNEL: "channel", SET_TRANSPOSE: "transpose",
    GET_PLUCK_NOISE: "pluck-noise",
    SET_PAGE: "page", SET_THEME: "theme", CLEAR: "clear",
}
STATUSES = {0: "ok", 1: "bad_opcode", 2: "bad_argument", 3: "bad_crc", 4: "bad_version"}


def _integer(name: str, value: Any, low: int, high: int) -> int:
    # bool is a Python int subclass, but is not an integer protocol field here.
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if not low <= value <= high:
        raise ValueError(f"{name} must be in {low}..{high}")
    return value


def _bytes(data: Any) -> bytes:
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("frame must be bytes, bytearray, or memoryview")
    return bytes(data)


def crc16_ccitt(data: bytes) -> int:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xffff, no reflect/xorout)."""
    crc = 0xFFFF
    for value in _bytes(data):
        crc ^= value << 8
        for _ in range(8):
            crc = ((crc << 1) ^ (0x1021 if crc & 0x8000 else 0)) & 0xFFFF
    return crc


def _pack(opcode: int, sequence: int, arg0: int, arg1: int) -> bytes:
    header = struct.pack("<2sBBHII", MAGIC, VERSION, opcode, sequence, arg0, arg1)
    return header + struct.pack("<H", crc16_ccitt(header))


def _validate_request(opcode: int, arg0: int, arg1: int) -> None:
    if opcode not in OPCODES:
        raise ValueError(f"unknown request opcode 0x{opcode:02x}")
    if arg1 != 0:
        raise ValueError("request arg1 is reserved and must be zero")
    if opcode == GET_STATUS and arg0 != 0:
        raise ValueError("status arg0 must be zero")
    if opcode == GET_TOUCH and arg0 > 24:
        raise ValueError("touch word index must be in 0..24")
    if opcode in (GET_PLUCK, GET_PLUCK_NOISE) and arg0 > 15:
        raise ValueError("pluck word index must be in 0..15")
    if opcode == SET_PLUCK_EMITTERS and arg0 > 1:
        raise ValueError("diagnostic emitter enable must be 0 or 1")
    if opcode == SET_PLUCK_THRESHOLDS and (arg0 & 65535) <= (arg0 >> 16):
        raise ValueError("diagnostic thresholds require 0 <= OFF < ON <= 65535; pack OFF:ON")
    if opcode in (SET_CHANNEL, SET_PAGE) and arg0 > 15:
        raise ValueError("channel/page must be in 0..15")
    if opcode in (SET_THEME, CLEAR) and arg0 > 0xFFFF:
        raise ValueError("RGB565 color must be in 0..65535")
    signed = arg0 if arg0 < 0x80000000 else arg0 - 0x100000000
    if opcode == SET_TRANSPOSE and not -48 <= signed <= 48:
        raise ValueError("transpose must be in -48..48 semitones")


def encode_request(opcode: int, sequence: int = 0, arg0: int = 0, arg1: int = 0) -> bytes:
    """Encode a validated request; transpose arg0 accepts signed -48..48.

    Other request fields use unsigned integers. Channel is MIDI's wire value
    0..15 (UI channel 1..16). Negative transpose is encoded as int32 LE.
    """
    _integer("opcode", opcode, 0, 0x7F)
    _integer("sequence", sequence, 0, 0xFFFF)
    _integer("arg1", arg1, 0, 0xFFFFFFFF)
    if opcode == SET_TRANSPOSE:
        _integer("transpose", arg0, -48, 48)
        arg0 &= 0xFFFFFFFF
    else:
        _integer("arg0", arg0, 0, 0xFFFFFFFF)
    _validate_request(opcode, arg0, arg1)
    return _pack(opcode, sequence, arg0, arg1)


def encode_response(opcode: int, sequence: int, status: int = 0, result: int = 0) -> bytes:
    """Encode a response, principally for host software tests.

    opcode is the original request byte (0..255), including an unknown opcode
    rejected by the device. The response always sets bit 7.
    """
    _integer("opcode", opcode, 0, 0xFF)
    _integer("sequence", sequence, 0, 0xFFFF)
    _integer("status", status, 0, 4)
    _integer("result", result, 0, 0xFFFFFFFF)
    if status != 0 and result != 0:
        raise ValueError("error response result must be zero")
    if status == 0:
        if opcode & 0x80:
            raise ValueError("successful response must refer to a valid request opcode")
        _validate_request(opcode & 0x7F, 0 if (opcode & 0x7F) in (GET_STATUS, GET_TOUCH, GET_PLUCK, GET_PLUCK_NOISE) else result, 0)
    return _pack(opcode | 0x80, sequence, status, result)


@dataclass(frozen=True)
class Frame:
    opcode: int
    sequence: int
    arg0: int
    arg1: int

    @property
    def is_response(self) -> bool:
        return bool(self.opcode & 0x80)

    @property
    def command(self) -> str:
        return OPCODES.get(self.opcode & 0x7F, "unknown")

    @property
    def signed_arg0(self) -> int:
        return self.arg0 if self.arg0 < 0x80000000 else self.arg0 - 0x100000000

    @property
    def signed_arg1(self) -> int:
        return self.arg1 if self.arg1 < 0x80000000 else self.arg1 - 0x100000000


def decode_frame(data: bytes) -> Frame:
    """Decode one complete frame and validate framing, CRC, and field ranges.

    Error responses may echo an unknown opcode or one with request bit 7 set;
    these are accepted if the response status is known and result is zero.
    """
    data = _bytes(data)
    if len(data) != FRAME_SIZE:
        raise ValueError(f"frame must contain exactly {FRAME_SIZE} bytes")
    magic, version, opcode, sequence, arg0, arg1, checksum = struct.unpack("<2sBBHIIH", data)
    if magic != MAGIC:
        raise ValueError("invalid frame magic; expected MK")
    if crc16_ccitt(data[:14]) != checksum:
        raise ValueError("invalid CRC-16/CCITT-FALSE")
    if version != VERSION:
        raise ValueError(f"unsupported protocol version {version}")
    if opcode & 0x80:
        _integer("response status", arg0, 0, 4)
        if arg0 != 0 and arg1 != 0:
            raise ValueError("error response result must be zero")
        if arg0 == 0:
            _validate_request(opcode & 0x7F, 0 if (opcode & 0x7F) in (GET_STATUS, GET_TOUCH, GET_PLUCK, GET_PLUCK_NOISE) else arg1, 0)
    else:
        _validate_request(opcode, arg0, arg1)
    return Frame(opcode, sequence, arg0, arg1)


def _number(text: str) -> int:
    try:
        return int(text, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected an integer (decimal or 0x hexadecimal)") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for opcode, name in OPCODES.items():
        command = commands.add_parser(name)
        command.set_defaults(opcode=opcode)
        command.add_argument("--seq", type=_number, default=0, help="sequence number, 0..65535")
        if opcode != GET_STATUS:
            command.add_argument("value", type=_number)
    decode = commands.add_parser("decode")
    decode.add_argument("hex", help="16-byte frame as hex, optionally with spaces")
    args = parser.parse_args(argv)
    try:
        if args.command == "decode":
            frame = decode_frame(bytes.fromhex(args.hex))
            fields: dict[str, Any] = {
                "opcode": f"0x{frame.opcode:02x}", "command": frame.command,
                "response": frame.is_response, "sequence": frame.sequence,
                "arg0": frame.arg0, "arg1": frame.arg1,
            }
            if frame.is_response:
                fields["status"] = STATUSES[frame.arg0]
                if frame.command == "transpose" and frame.arg0 == 0:
                    fields["transpose"] = frame.signed_arg1
            elif frame.command == "transpose":
                fields["transpose"] = frame.signed_arg0
            print(json.dumps(fields, ensure_ascii=False, sort_keys=True))
        else:
            print(encode_request(args.opcode, args.seq, getattr(args, "value", 0)).hex(" "))
    except (ValueError, TypeError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
