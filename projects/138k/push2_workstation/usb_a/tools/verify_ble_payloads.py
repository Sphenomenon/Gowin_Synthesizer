#!/usr/bin/env python3
"""Verify captured FFF1 notifications without opening a Bluetooth adapter.

Input: one 20-byte hexadecimal payload per line, or the teammate's JSON
capture schema {"packets": [{"raw": "42545354..."}, ...]}.
"""
from pathlib import Path
import argparse
import json


def crc16(data):
    value = 0xffff
    for byte in data:
        value ^= byte << 8
        for _ in range(8):
            value = ((value << 1) ^ (0x1021 if value & 0x8000 else 0)) & 0xffff
    return value


def decode_payload(raw):
    if isinstance(raw, str):
        raw = bytes.fromhex(raw)
    else:
        raw = bytes(raw)
    if len(raw) != 20:
        raise ValueError('Notification length must be exactly 20 bytes')
    if raw[:4] != b'BTST' or raw[12:18] != bytes(range(6)):
        raise ValueError('Not the original BTST test payload')
    if crc16(raw[:18]) != int.from_bytes(raw[18:20], 'little'):
        raise ValueError('CRC16 mismatch')
    return {'sequence': int.from_bytes(raw[4:8], 'little'),
            'device_uptime_ms': int.from_bytes(raw[8:12], 'little'), 'raw': raw.hex()}


def verify(raw_packets, minimum=3):
    decoded = []
    errors = []
    gaps = []
    for index, raw in enumerate(raw_packets):
        try:
            packet = decode_payload(raw)
        except (TypeError, ValueError) as error:
            errors.append({'index': index, 'error': str(error)})
            continue
        if decoded:
            previous = decoded[-1]
            step = (packet['sequence'] - previous['sequence']) & 0xffffffff
            elapsed = (packet['device_uptime_ms'] - previous['device_uptime_ms']) & 0xffffffff
            if step != 1:
                gaps.append({'index': index, 'previous': previous['sequence'], 'sequence': packet['sequence']})
            if elapsed == 0 or elapsed >= 0x80000000:
                errors.append({'index': index, 'error': 'Device timestamp did not advance'})
        decoded.append(packet)
    return {'passed': len(decoded) >= minimum and not errors and not gaps,
            'valid_count': len(decoded), 'minimum_count': minimum,
            'sequence_gaps': gaps, 'errors': errors, 'packets': decoded,
            'scope': 'Captured payload integrity only; input provenance determines which board was tested'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--minimum', type=int, default=3)
    args = parser.parse_args()
    if args.minimum < 1:
        parser.error('--minimum must be positive')
    text = args.input.read_text()
    if text.lstrip().startswith('{'):
        data = json.loads(text)
        raw_packets = [packet['raw'] for packet in data['packets']]
    else:
        raw_packets = [line.strip() for line in text.splitlines() if line.strip()]
    result = verify(raw_packets, args.minimum)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'packets'}, indent=2))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
