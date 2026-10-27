from collections import Counter
from pathlib import Path
import argparse
import csv
import fcntl
import json
import os
import runpy
import stat
import subprocess
import time


ROOT = Path(__file__).resolve().parents[2]
HELPER = runpy.run_path(str(ROOT / 'reports/hdmi_usb3_20261025/capture_ddr_jtag.py'))
TRACE = runpy.run_path(str(Path(__file__).with_name('scan_trace.py')))


def decode(values):
    if len(values) != 64 or any(value not in (0, 1) for value in values):
        raise ValueError('expected 64 binary probe values')
    word = int(''.join(map(str, values[1:])), 2)
    sample = HELPER['snapshot'](dict(zip(HELPER['WORKSTATION_SIGNALS'], values[:1] + values[-15:])),
                                'workstation-memory-video-16-v1')
    sample.update(underrun_lines=(word >> 31) & 0xffffffff,
                  rendered_frames_mod256=(word >> 23) & 255, video_frames_mod256=(word >> 15) & 255)
    return sample


def capture(candidate, output):
    manifest = json.loads((candidate / 'inputs.json').read_text())
    expected = ['reset_n'] + [f'debug_status[{bit}]' for bit in reversed(range(63))]
    trace = manifest['signal_schema'] == TRACE['SCHEMA']
    if trace:
        expected += TRACE['TRACE_SIGNALS']
    if (manifest['signal_schema'] not in ('hdmi-isolation-memory-video-counters-64-v1', TRACE['SCHEMA']) or
            manifest['signals'] != expected or manifest['full_workstation'] is not False):
        raise ValueError('expected explicit HDMI isolation observer')
    configuration = candidate / 'display.gao'
    if HELPER['digest'](configuration) != manifest['input_sha256']['display.gao']:
        raise ValueError('GAO input changed')
    if HELPER['digest'](HELPER['BINARY']) != '4717a2afa56893861de161207bc2c4f094f53227099763ebfa2f0025ab72515b':
        raise ValueError('GAO host binary changed')
    if HELPER['digest'](HELPER['RECIPE']) != '901f1c40d4679c54e1246226c33c2d33850c2a55bbebed496ed9c69f4b87de66':
        raise ValueError('WINUSB runtime recipe changed')
    output.mkdir(parents=True)
    HELPER['identity'](output / 'identity_before.log', manifest['user_code'])
    socket = HELPER['TEMPORARY'] / 'gao1'
    if socket.exists():
        listeners = subprocess.run(['ss', '-xlpn'], capture_output=True, text=True, check=True).stdout
        if (not stat.S_ISSOCK(socket.lstat().st_mode) or socket.lstat().st_uid != os.getuid() or
                str(socket) in listeners):
            raise ValueError('GAO socket is foreign or active')
        socket.unlink()
    environment = os.environ.copy()
    environment.update(QT_QPA_PLATFORM='offscreen', QT_OPENGL='software',
                       LD_LIBRARY_PATH=str(HELPER['BINARY'].parents[1] / 'lib'),
                       LD_PRELOAD='/usr/lib64/libstdc++.so.6:/usr/lib64/libz.so.1:/usr/lib64/libfreetype.so.6',
                       TMPDIR=str(HELPER['TEMPORARY']))
    command = ['timeout', '--kill-after=5s', '60s', 'gdb', '-nx', '-q', '-batch', '-x',
               str(HELPER['RECIPE']), '--args', str(HELPER['BINARY']), '-local', '-gao',
               str(configuration), '-out', str(output / 'capture'), '-cable', 'FT2CH', '-location', '54']
    started = HELPER['timestamp']()
    with (output / 'gdb.log').open('xb') as logfile:
        result = subprocess.run(command, env=environment, stdin=subprocess.DEVNULL,
                                stdout=logfile, stderr=subprocess.STDOUT, timeout=75)
    if result.returncode:
        raise RuntimeError('GAO capture failed: ' + str(result.returncode))
    files = list(output.glob('capture_core*_window*.csv'))
    if len(files) != 1:
        raise ValueError('expected one capture window')
    rows = [[value.strip() for value in row if value.strip()]
            for row in csv.reader(files[0].read_text().splitlines(), skipinitialspace=True)]
    header = next(index for index, row in enumerate(rows) if row and row[0].startswith('time unit:'))
    if rows[header][1:] != expected:
        raise ValueError('capture signal order changed')
    samples = []
    for row in rows[header + 1:]:
        if not row:
            continue
        if len(row) != len(expected) + 1 or int(row[0]) != len(samples) or any(value not in ('0', '1') for value in row[1:]):
            raise ValueError('invalid sample row')
        values = list(map(int, row[1:]))
        sample = decode(values[:64])
        if trace:
            sample['scan'] = TRACE['decode_trace'](values[64:])
        samples.append(sample)
    if len(samples) != manifest['storage_depth']:
        raise ValueError('incomplete window')
    HELPER['identity'](output / 'identity_after.log', manifest['user_code'])
    result = dict(started_at=started, finished_at=HELPER['timestamp'](), user_code=manifest['user_code'],
                  first=samples[0], last=samples[-1], samples=len(samples),
                  csv_sha256=HELPER['digest'](files[0]), gao_sha256=HELPER['digest'](configuration),
                  states=dict(Counter(json.dumps(sample, sort_keys=True) for sample in samples)),
                  sram_programmed=False, flash_accessed=False, visual_acceptance=False)
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(output=str(output), first=result['first'], last=result['last'])), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description='Read-only HDMI isolation counters; no programming.')
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--count', type=int, default=3, choices=range(1, 4))
    arguments = parser.parse_args()
    if arguments.output.exists():
        parser.error('capture output must be new')
    captures = []
    with Path('/tmp/gw138k_20261025.lock').open('a') as capture_lock, \
            Path('/tmp/gw138k_2025030317.lock').open('a') as board_lock:
        fcntl.flock(capture_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(board_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for sequence in range(arguments.count):
            captures.append(capture(arguments.candidate.resolve(), arguments.output.resolve() / str(sequence + 1)))
            time.sleep(0.43)
    (arguments.output / 'result.json').write_text(json.dumps(captures, indent=2) + '\n')


if __name__ == '__main__':
    main()
