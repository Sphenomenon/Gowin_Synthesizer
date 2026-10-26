#!/usr/bin/env python3
"""Decode the dedicated, read-only BLE diagnostic UART (115200 8N1)."""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import re
import time


WORD_NAMES = (
    'magic', 'version', 'flags', 'uptime_ms', 'states', 'last_error_status_opcode',
    'hci_commands', 'patch_fragments', 'h5_rx_frames', 'h5_tx_frames',
    'h5_retries', 'uart_errors', 'protocol_errors', 'notifications', 'acl_rx',
    'att_requests', 'completed_packets', 'gatt_errors', 'bd_addr_low',
    'bd_addr_high', 'handle_rom', 'gatt_elapsed_ms', 'clock_hz', 'baud',
)


def decode_line(line):
    if isinstance(line, bytes):
        line = line.decode('ascii', errors='strict')
    if re.fullmatch(r'BLE1 [0-9A-F]{192}\n', line) is None:
        raise ValueError('Expected one BLE1 line with exactly 24 hex words')
    words = [int(line[5+i*8:13+i*8], 16) for i in range(24)]
    if words[0] != 0x42545647 or words[1] != 1 or words[22] != 50000000 or words[23] not in (115200, 921600):
        raise ValueError('Not the expected GW138K BLE status format or clock configuration')
    result = dict(zip(WORD_NAMES, words))
    flags = words[2]
    for bit, name in enumerate(('outputs_active', 'h5_link_up', 'initialized',
                               'connected', 'subscribed', 'failed', 'session_ended')):
        result[name] = bool(flags & (1 << bit))
    result['hci_valid_mask'] = (flags >> 9) & 7
    result['h5_state'] = words[4] & 255
    result['hci_state'] = (words[4] >> 8) & 255
    result['gatt_state'] = (words[4] >> 16) & 255
    result['error_code'] = words[5] >> 24
    result['hci_status'] = (words[5] >> 16) & 255
    result['hci_opcode'] = f'0x{words[5] & 65535:04x}'
    result['rom_version'] = words[20] & 255
    result['connection_handle'] = (words[20] >> 8) & 4095
    result['bd_address'] = f'{words[19] & 65535:04X}{words[18]:08X}'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', help='Dedicated BLE status port, never the RTL8723DS UART')
    parser.add_argument('--seconds', type=float, default=10)
    parser.add_argument('--input', type=Path, help='Decode a saved ASCII capture instead of opening a port')
    parser.add_argument('--output', type=Path, help='Save decoded records as JSON')
    args = parser.parse_args()
    if (args.port is None) == (args.input is None):
        parser.error('Choose exactly one of --port and --input')
    if args.seconds <= 0:
        parser.error('--seconds must be positive')
    records = []
    malformed = 0
    def accept(line):
        nonlocal malformed
        try:
            status = decode_line(line)
        except (ValueError, UnicodeError):
            malformed += 1
            return
        status['observed_at'] = datetime.now(timezone.utc).isoformat()
        records.append(status)
        print(json.dumps(status, ensure_ascii=False), flush=True)
    if args.input:
        for line in args.input.read_bytes().splitlines(keepends=True):
            accept(line)
    else:
        import serial
        # Reading only; do not assert reset/control modem lines on open.
        port = serial.Serial(port=None, baudrate=115200, timeout=0.25,
                             parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE)
        port.dtr = False
        port.rts = False
        port.port = args.port
        with port:
            deadline = time.monotonic() + args.seconds
            while time.monotonic() < deadline:
                line = port.read_until(b'\n', 512)
                if line:
                    accept(line)
    result = {'records': records, 'malformed_lines': malformed,
              'hardware_acceptance': 'capture_only; BLE scan/connect/notify requires separate evidence'}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    if not records:
        raise SystemExit('No complete BLE status frames were received')


if __name__ == '__main__':
    main()
