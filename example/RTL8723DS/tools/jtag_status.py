#!/usr/bin/env python3
"""Capture radio status through Gowin GAO; requires the matching SRAM image."""
import argparse
import csv
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from program_sram import verified_artifact
from status import decode


def read_csv(path):
    rows = list(csv.reader(path.read_text().splitlines()))
    start = next(i for i, row in enumerate(rows) if row == ['Data:'])
    if rows[start+1][1].strip() != 'radio_debug[1087:0]':
        raise ValueError('Unexpected GAO capture layout')
    samples = []
    for row in rows[start+2:]:
        if not row:
            continue
        vector = int(row[1].strip(), 16)
        words = [(vector >> (32*i)) & 0xffffffff for i in range(34)]
        item = decode(('RF13 '+''.join(f'{x:08X}' for x in words[:32])).encode())
        if item is None:
            raise ValueError('GAO data has invalid radio signatures')
        b, u = words[32:34]
        item['board'] = {'restart_n': bool(b & 2), 'resetn': bool(b & 1),
                         'uart_rx_level': bool(b & 4), 'sd_cmd_level': bool(b & 8),
                         'heartbeat': (b >> 8) & 255, 'uart_rx_falling_edges': b >> 16,
                         'raw_uart_bytes': u >> 16, 'raw_uart_errors': (u >> 8) & 255,
                         'raw_uart_last': f'{u & 255:02x}'}
        samples.append(item)
    if len(samples) != 128:
        raise ValueError(f'Expected 128 samples, got {len(samples)}')
    return samples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--location', help='USB location from programmer_cli --scan-cables')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    artifact, _ = verified_artifact(args.manifest, allow_gao=True)
    manifest = json.loads(args.manifest.read_text())
    ide = Path(os.environ.get('GW138K_IDE_DIR', '/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE'))
    programmer = ide.parent/'Programmer/bin/programmer_cli'
    result = {'captured_at': datetime.datetime.now().astimezone().isoformat(),
              'artifact': artifact, 'capture_valid': False, 'passed': False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        location = args.location
        if location is None:
            scan = subprocess.run([str(programmer), '--scan-cables'], text=True,
                                  capture_output=True, timeout=15)
            locations = re.findall(r'Gowin USB Cable\(FT2CH\)/0/[^\n]*\(USB location:(\d+)\)', scan.stdout)
            if scan.returncode or len(locations) != 1:
                raise ValueError('Need one FT2CH channel-0 cable, or specify --location')
            location = locations[0]
        result['usb_location'] = location
        with tempfile.TemporaryDirectory(prefix='radio-gao-', dir='/private/tmp') as tmp:
            folder = Path(tmp)
            definition = folder/'radio.gao'
            shutil.copy2(manifest['gao'][0]['definition'], definition)
            env = dict(os.environ, DYLD_LIBRARY_PATH=str(ide/'lib'), DYLD_FRAMEWORK_PATH=str(ide/'lib'))
            command = [str(ide/'bin/gao_sh'), '-gao', str(definition), '-device', 'GW5AST-138C',
                       '-cable', 'FT2CH', '-location', location, '-out', str(folder/'capture')]
            process = subprocess.run(command, env=env, text=True, capture_output=True, timeout=40)
            result['tool_output'] = process.stdout+process.stderr
            if process.returncode or re.search(r'\berror\b', result['tool_output'], re.I):
                raise ValueError('GAO capture failed; see tool_output')
            capture = folder/'capture_core0_window0.csv'
            saved = args.output.with_suffix('.csv')
            shutil.copy2(capture, saved)
            samples = read_csv(saved)
        result.update(capture_valid=True, sample_count=len(samples), csv=str(saved.resolve()),
                      clock_running=len({x['board']['heartbeat'] for x in samples}) > 1,
                      first=samples[0], last=samples[-1])
        last = samples[-1]
        result['passed'] = (result['clock_running'] and last['board']['resetn'] and
            last['ble']['initialized'] and not last['ble']['failed'] and
            last['wifi']['done'] and last['wifi']['identified'] and not last['wifi']['failed'])
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        result['error'] = str(error)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
