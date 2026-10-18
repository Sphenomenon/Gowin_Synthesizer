"""Decode BLE GAO CSV snapshots; exported time labels are not UART timing."""
import argparse
import csv
import json
from pathlib import Path


# Gowin exports grouped and single-bit signal values in hexadecimal.
WIDTHS = {
    'status[70:64]': 7,
    'status[135:128]': 8,
    'status[143:136]': 8,
    'status[191:184]': 8,
    'status[231:224]': 8,
    'status[199:192]': 8,
    'status[647:640]': 8,
    'usb1_line_state[1:0]': 2,
    'usb1_activity_seen': 1,
    'usb1_se0_long_seen': 1,
    'usb1_se1_long_seen': 1,
    'module_uart_tx': 1,
    'tx': 1,
    'bt_enable': 1,
    'drive_pins': 1,
}
FLAG_NAMES = ('outputs_active', 'h5_link_up', 'initialized', 'connected',
              'subscribed', 'failed', 'session_ended')


def snapshot(values):
    flags = values['status[70:64]']
    line = values['usb1_line_state[1:0]']
    return {
        'flags_hex': f'{flags:02X}',
        'flags': {name: bool(flags & (1 << bit))
                  for bit, name in enumerate(FLAG_NAMES)},
        'h5_state': values['status[135:128]'],
        'init_state': values['status[143:136]'],
        'error_code': values['status[191:184]'],
        'patch_fragments_low8': values['status[231:224]'],
        'hci_commands_low8': values['status[199:192]'],
        'rom_version': values['status[647:640]'],
        'usb1': {
            'line_state': line,
            'line_state_name': ('SE0', 'FS_K', 'FS_J', 'SE1')[line],
            'activity_seen': bool(values['usb1_activity_seen']),
            'se0_long_seen': bool(values['usb1_se0_long_seen']),
            'se1_long_seen': bool(values['usb1_se1_long_seen']),
        },
        'pins': {name: values[name] for name in
                 ('module_uart_tx', 'tx', 'bt_enable', 'drive_pins')},
    }


def decode(path):
    path = Path(path)
    header = None
    data_seen = False
    runs = []
    sample_count = 0
    first_time = last_time = None
    with path.open(encoding='utf-8-sig', newline='') as source:
        for line_number, row in enumerate(csv.reader(source), 1):
            row = [field.strip() for field in row]
            while row and not row[-1]:
                row.pop()
            if not row:
                continue
            if not data_seen:
                data_seen = row == ['Data:']
                continue
            if header is None:
                if not row[0].startswith('time unit:'):
                    raise ValueError(f'line {line_number}: missing Data time header')
                header = row
                if len(set(header)) != len(header):
                    raise ValueError('duplicate CSV column name')
                missing = WIDTHS.keys() - set(header)
                if missing:
                    raise ValueError('missing CSV columns: ' + ', '.join(sorted(missing)))
                continue
            if len(row) != len(header):
                raise ValueError(f'line {line_number}: wrong CSV column count')
            fields = dict(zip(header, row))
            values = {}
            for name, width in WIDTHS.items():
                try:
                    value = int(fields[name], 16)
                except ValueError as exc:
                    raise ValueError(f'line {line_number}: invalid hex {name}={fields[name]!r}') from exc
                if not 0 <= value < (1 << width):
                    raise ValueError(f'line {line_number}: {name} exceeds {width} bits')
                values[name] = value
            current = snapshot(values)
            if not runs or runs[-1]['status'] != current:
                runs.append({'first_sample': sample_count,
                             'last_sample': sample_count, 'status': current})
            else:
                runs[-1]['last_sample'] = sample_count
            if first_time is None:
                first_time = row[0]
            last_time = row[0]
            sample_count += 1
    if not sample_count:
        raise ValueError('no GAO data samples found')
    return {
        'source': str(path.resolve()),
        'sample_count': sample_count,
        'all_signals_constant': len(runs) == 1,
        'csv_time_axis': {
            'header': header[0], 'first_label': first_time, 'last_label': last_time,
            'note': 'Export labels only; do not infer UART timing or elapsed hardware time.',
        },
        'runs': runs,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path)
    parser.add_argument('--output', type=Path, help='write JSON here instead of stdout')
    args = parser.parse_args()
    try:
        result = json.dumps(decode(args.csv), ensure_ascii=False, indent=2) + '\n'
    except (OSError, ValueError) as exc:
        parser.exit(1, f'{args.csv}: {exc}\n')
    if args.output:
        args.output.write_text(result, encoding='utf-8')
    else:
        print(result, end='')


if __name__ == '__main__':
    main()
