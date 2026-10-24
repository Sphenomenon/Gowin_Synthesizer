#!/usr/bin/env python3
"""Capture internal LCD clocks and scan progress; does not measure panel pins."""
from pathlib import Path
from datetime import datetime
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT.parents[1]/'RTL8723DS'))
from program_sram import verified_artifact


def gray_to_binary(value):
    result = value
    while value:
        value >>= 1
        result ^= value
    return result


def decode(path):
    rows = list(csv.reader(path.read_text().splitlines()))
    start = next(i for i, row in enumerate(rows) if row == ['Data:'])
    if rows[start+1][1].strip() != 'lcd_debug[191:0]':
        raise ValueError('Unexpected capture bus')
    samples = []
    for row in rows[start+2:]:
        if not row:
            continue
        value = int(row[1].strip(), 16)
        words = [(value >> (32*i)) & 0xffffffff for i in range(6)]
        if words[0] != 0x4c434431:
            raise ValueError('LCD1 signature mismatch')
        samples.append(dict(heartbeat=words[1], pixel_clocks=gray_to_binary(words[2]),
                            frames=gray_to_binary(words[3]), active_pixels=gray_to_binary(words[4]), flags=words[5]))
    if len(samples) != 128:
        raise ValueError('Expected 128 samples')
    backwards = [i+1 for i in range(len(samples)-1)
                 if ((samples[i+1]['heartbeat']-samples[i]['heartbeat']) & 0xffffffff) > 0x80000000]
    if len(backwards) > 1:
        raise ValueError('Invalid capture chronology')
    if backwards:
        cut = backwards[0]
        samples = samples[cut:]+samples[:cut]
    if any(((b['heartbeat']-a['heartbeat']) & 0xffffffff) != 1
           for a, b in zip(samples, samples[1:])):
        raise ValueError('Reference counter not consecutive')
    return samples


def main():
    manifest_path = PROJECT/'reports/last_build.json'
    artifact, user_code = verified_artifact(manifest_path, allow_gao=True)
    manifest = json.loads(manifest_path.read_text())
    for name, digest in manifest['source_hashes'].items():
        if hashlib.sha256((PROJECT/name).read_bytes()).hexdigest() != digest:
            raise ValueError('Current source differs from build: '+name)
    ide = Path('/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE')
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    out = PROJECT/'reports'/('jtag_lcd_'+stamp+'.json')
    result = dict(time=datetime.now().astimezone().isoformat(), artifact=artifact,
                  user_code=hex(user_code), capture_valid=False, digital_passed=False,
                  physical_clock_measured=False, screen_verified=False)
    try:
        scan = subprocess.run([str(ide.parent/'Programmer/bin/programmer_cli'), '--scan-cables'],
                              capture_output=True, text=True, timeout=15)
        locations = re.findall(r'Gowin USB Cable\(FT2CH\)/0/[^\n]*\(USB location:(\d+)\)', scan.stdout)
        if scan.returncode or len(locations) != 1:
            raise ValueError('Need exactly one FT2CH channel 0 cable: '+scan.stdout)
        result['usb_location'] = locations[0]
        captures = []
        with tempfile.TemporaryDirectory(prefix='lcd-gao-', dir='/private/tmp') as temp:
            folder = Path(temp)
            definition = folder/'lcd.gao'
            shutil.copy2(manifest['gao'][0]['definition'], definition)
            for i in range(2):
                if i:
                    time.sleep(1)
                prefix = folder/f'capture{i}'
                process = subprocess.run([str(ide/'bin/gao_sh'), '-gao', str(definition),
                    '-device', 'GW5AST-138C', '-cable', 'FT2CH', '-location', locations[0],
                    '-out', str(prefix)], capture_output=True, text=True, timeout=40,
                    env=dict(os.environ, DYLD_LIBRARY_PATH=str(ide/'lib'),
                             DYLD_FRAMEWORK_PATH=str(ide/'lib')))
                log = process.stdout+process.stderr
                out.with_suffix(f'.{i}.log').write_text(log)
                if process.returncode or re.search(r'\berror\b', log, re.I):
                    raise ValueError(log)
                saved = out.with_suffix(f'.{i}.csv')
                shutil.copy2(str(prefix)+'_core0_window0.csv', saved)
                samples = decode(saved)
                captures.append(dict(csv=str(saved), first=samples[0], last=samples[-1]))
        first, last = [c['last'] for c in captures]
        delta = {key: (last[key]-first[key]) & 0xffffffff
                 for key in ('heartbeat', 'pixel_clocks', 'frames', 'active_pixels')}
        seconds = delta['heartbeat']/50000000
        if not 0.5 < seconds < 70:
            raise ValueError('Reference interval invalid or counters wrapped')
        pixel_hz = delta['pixel_clocks']/seconds
        frame_hz = delta['frames']/seconds
        active_hz = delta['active_pixels']/seconds
        expected_frame_hz = 31500000/(976*528)
        flags_ok = all(c['last']['flags'] & 255 == 255 for c in captures)
        passed = (abs(pixel_hz/31500000-1) < .01 and
                  abs(frame_hz-expected_frame_hz) < 1.0 and
                  abs(active_hz/(expected_frame_hz*800*480)-1) < .02 and flags_ok)
        result.update(capture_valid=True, digital_passed=passed, captures=captures,
                      counter_deltas=delta, interval_seconds=seconds,
                      measured_internal_pixel_clock_hz=pixel_hz,
                      measured_internal_frame_hz=frame_hz,
                      measured_active_pixels_per_second=active_hz,
                      flags=dict(pll_locked=bool(last['flags'] & 1),
                                 restart_released=bool(last['flags'] & 2),
                                 scan_reset_released=bool(last['flags'] & 4),
                                 backlight_on=bool(last['flags'] & 8),
                                 de_seen=bool(last['flags'] & 16),
                                 hsync_seen=bool(last['flags'] & 32),
                                 vsync_seen=bool(last['flags'] & 64),
                                 white_data_seen=bool(last['flags'] & 128)))
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        result['error'] = str(error)
    result['limitation'] = ('Counters and sticky observations verify internal FPGA logic relative to the nominal '
        '50MHz reference. They do not measure physical IO waveforms, cable continuity, panel voltages or visible luminance.')
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')
    (PROJECT/'reports/last_capture.json').write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result['digital_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
