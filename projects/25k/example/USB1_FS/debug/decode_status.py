"""Decode USB1's 50 MHz status bus from a Gowin GAO CSV."""
import argparse
import csv
import json
from pathlib import Path


def snapshot(value):
    line = (value >> 10) & 3
    names = {
        15: 'pll_locked', 14: 'reset60n', 13: 'usb_bus_reset_released',
        12: 'attach_intent_unconnected', 9: 'overflow_seen', 8: 'received_seen',
        7: 'heartbeat50', 6: 'heartbeat60', 5: 'line_activity_seen',
        4: 'se0_long_seen', 3: 'se1_long_seen', 2: 'monitor_settled', 1: 'j_long_seen',
        0: 'heartbeat50_fast',
    }
    return {'raw_hex': f'{value:016X}',
            'line_transitions_saturated16': value >> 48,
            'se0_consecutive_cycles_saturated16': (value >> 32) & 0xffff,
            'j_consecutive_cycles_saturated16': (value >> 16) & 0xffff,
            'line_state': line, 'line_name': ('SE0', 'FS_K', 'FS_J', 'SE1')[line],
            'flags': {name: bool(value & (1 << bit)) for bit, name in names.items()}}


def decode(path):
    data_seen = False
    header = None
    samples = []
    with path.open(encoding='utf-8-sig', newline='') as source:
        for row in csv.reader(source):
            row = [cell.strip() for cell in row]
            while row and not row[-1]:
                row.pop()
            if not row:
                continue
            if not data_seen:
                data_seen = row == ['Data:']
                continue
            if header is None:
                header = row
                if (not row[0].startswith('time unit:') or len(set(row)) != len(row)
                        or 'status_50mhz[63:0]' not in row):
                    raise ValueError('CSV does not contain the USB1 50 MHz GAO bus')
                continue
            if len(row) != len(header):
                raise ValueError('CSV column count changed')
            value = int(row[header.index('status_50mhz[63:0]')], 16)
            if not 0 <= value < 1 << 64:
                raise ValueError('status exceeds 64 bits')
            samples.append({'sample': len(samples), 'export_time_label': row[0],
                            'status': snapshot(value)})
    if not samples:
        raise ValueError('no USB GAO samples found')
    return {'source': str(path.resolve()), 'sample_count': len(samples),
            'sample_clock_hz': 50000000,
            'note': 'CSV time labels are retained as exported; they do not establish USB bit timing. '
                    'Two-flop line samples are diagnostic observations, not a USB protocol trace.',
            'samples': samples}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        text = json.dumps(decode(args.csv), indent=2) + '\n'
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
