#!/usr/bin/env python3
"""Read completed hardware frequency gates; host/JTAG timing is not the timebase."""
import argparse
import csv
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent/'RTL8723DS'))
from program_sram import verified_artifact


def decode(path):
    rows = list(csv.reader(path.read_text().splitlines()))
    start = next(i for i, row in enumerate(rows) if row == ['Data:'])
    if rows[start+1][1].strip() != 'frequency_debug[255:0]':
        raise ValueError('Unexpected GAO capture layout')
    samples = []
    for row in rows[start+2:]:
        if not row:
            continue
        value = int(row[1].strip(), 16)
        words = [(value >> (32*i)) & 0xffffffff for i in range(8)]
        if words[0] != 0x46524551 or words[4] != 500000000:
            raise ValueError('Invalid FREQ signature or hardware gate length')
        samples.append(dict(window_id=words[1], count_a=words[2], count_b=words[3],
                            reference_cycles=words[4], heartbeat=words[5],
                            endpoint_a=words[6], endpoint_b=words[7]))
    if len(samples) != 128:
        raise ValueError('Need 128 GAO samples')
    # Result fields are atomically registered in the reference domain. Circular
    # GAO row ordering does not matter for the highest completed gate number.
    return max(samples, key=lambda s: (s['window_id'], s['heartbeat']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT/'reports/last_build.json')
    parser.add_argument('--windows', type=int, default=6)
    parser.add_argument('--reference-hz', type=float, default=50000000)
    parser.add_argument('--output', type=Path, default=ROOT/'reports/measurement.json')
    args = parser.parse_args()
    if not 2 <= args.windows <= 20 or args.reference_hz <= 0:
        parser.error('Use 2..20 windows and a positive reference frequency')
    artifact, expected_code = verified_artifact(args.manifest, allow_gao=True)
    manifest = json.loads(args.manifest.read_text())
    ide = Path(os.environ.get('GW138K_IDE_DIR', '/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE'))
    cli = str(ide.parent/'Programmer/bin/programmer_cli')
    result = dict(started_at=datetime.now().astimezone().isoformat(), passed=False,
                  artifact=artifact, expected_user_code=hex(expected_code),
                  reference=dict(pin='V22', assumed_frequency_hz=args.reference_hz,
                                 externally_calibrated=False, absolute_accuracy_ppm=None),
                  gate_reference_cycles=500000000, requested_windows=args.windows,
                  flash_written=False, windows=[])
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')

    try:
        scan = subprocess.run([cli, '--scan-cables'], capture_output=True, text=True, timeout=15)
        locations = re.findall(r'Gowin USB Cable\(FT2CH\)/0/[^\n]*\(USB location:(\d+)\)', scan.stdout)
        if scan.returncode or len(locations) != 1:
            raise ValueError('Need exactly one connected channel-0 Gowin FT2CH cable')
        result['usb_location'] = locations[0]
        identity = subprocess.run([cli, '--device', 'GW5AST-138C', '--cable-index', '1',
                                  '--location', locations[0], '--channel', '0', '--frequency', '2.5MHz',
                                  '--operation_index', '0'], capture_output=True, text=True, timeout=15)
        device_log = args.output.with_suffix('.device.log')
        device_log.write_text(identity.stdout+identity.stderr)
        codes = re.findall(r'User Code is:\s*(0x[0-9a-fA-F]+)', identity.stdout)
        statuses = re.findall(r'Status Code is:\s*(0x[0-9a-fA-F]+)', identity.stdout)
        if (identity.returncode or not codes or any(int(c,16) != expected_code for c in codes)
                or not statuses or any(not int(c,16)&0x2000 for c in statuses)):
            raise ValueError('Live device identity/configuration does not match measurement image')
        result['device_log'] = str(device_log.resolve())
        deadline = time.monotonic()+args.windows*500000000/args.reference_hz+40
        env = dict(os.environ, DYLD_LIBRARY_PATH=str(ide/'lib'), DYLD_FRAMEWORK_PATH=str(ide/'lib'))
        with tempfile.TemporaryDirectory(prefix='freq-gao-', dir='/private/tmp') as tmp:
            folder = Path(tmp)
            definition = folder/'frequency.gao'
            shutil.copy2(manifest['gao'][0]['definition'], definition)
            attempt = 0
            while len(result['windows']) < args.windows:
                if time.monotonic() > deadline:
                    raise TimeoutError('Not enough completed measurement gates; check reset and reference clock')
                prefix = folder/'capture'
                capture = subprocess.run([str(ide/'bin/gao_sh'), '-gao', str(definition),
                                          '-device', 'GW5AST-138C', '-cable', 'FT2CH',
                                          '-location', locations[0], '-out', str(prefix)],
                                         env=env, capture_output=True, text=True, timeout=40)
                if capture.returncode or re.search(r'\berror\b', capture.stdout+capture.stderr, re.I):
                    raise ValueError('GAO capture failed: '+capture.stdout+capture.stderr)
                source = Path(str(prefix)+'_core0_window0.csv')
                sample = decode(source)
                if sample['window_id'] and (not result['windows'] or sample['window_id'] > result['windows'][-1]['window_id']):
                    saved = args.output.with_suffix(f'.gate{sample["window_id"]}.csv')
                    shutil.copy2(source, saved)
                    sample['csv'] = str(saved.resolve())
                    seconds = sample['reference_cycles']/args.reference_hz
                    sample.update(frequency_a_hz=sample['count_a']/seconds,
                                  frequency_b_hz=sample['count_b']/seconds)
                    if result['windows'] and sample['window_id'] != result['windows'][-1]['window_id']+1:
                        raise ValueError('Missed gate; refusing to average nonconsecutive counts')
                    result['windows'].append(sample)
                    save()
                    print(f'Gate {sample["window_id"]}: K18={sample["frequency_a_hz"]:.3f} Hz, '
                          f'J19={sample["frequency_b_hz"]:.3f} Hz', flush=True)
                attempt += 1
                if len(result['windows']) < args.windows:
                    time.sleep(2)
        windows = result['windows']
        total_ref = sum(s['reference_cycles'] for s in windows)
        result['total_reference_cycles'] = total_ref
        result['nominal_observation_seconds'] = total_ref/args.reference_hz
        result['oscillators'] = []
        for label, pin, nominal in [('a','K18',12288000), ('b','J19',16934400)]:
            count = sum(s['count_'+label] for s in windows)
            hz = count*args.reference_hz/total_ref
            values = [s['frequency_'+label+'_hz'] for s in windows]
            result['oscillators'].append(dict(pin=pin, nominal_frequency_hz=nominal,
                total_edges=count, measured_frequency_hz=hz, ratio_to_reference=count/total_ref,
                deviation_hz=hz-nominal, deviation_ppm=(hz/nominal-1)*1e6,
                minimum_window_hz=min(values), maximum_window_hz=max(values),
                window_stddev_hz=statistics.pstdev(values), running=all(x>0 for x in values)))
        result['aggregate_one_edge_resolution_hz'] = args.reference_hz/total_ref
        result['limitation'] = ('Frequencies assume the stated board reference frequency. Reference oscillator error '
                                'scales both results; Gray CDC/gate quantization and short-term variation remain. '
                                'This is a frequency ratio measurement, not externally calibrated absolute frequency or jitter.')
        result['passed'] = all(s['running'] for s in result['oscillators'])
    except (OSError, ValueError, KeyError, StopIteration, TimeoutError, subprocess.TimeoutExpired) as error:
        result['error'] = str(error)
    result['finished_at'] = datetime.now().astimezone().isoformat()
    save()
    print(json.dumps({k:v for k,v in result.items() if k != 'windows'}, ensure_ascii=False, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
