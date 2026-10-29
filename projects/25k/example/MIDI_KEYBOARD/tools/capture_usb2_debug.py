#!/usr/bin/env python3
"""Read an already-loaded MIDI USB2 debug image; never program SRAM or Flash."""
import argparse
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from decode_usb2_debug import GAO_ID, PROBE_ID, decode, load_config


PROJECT = Path(__file__).resolve().parents[1]
GAO_BINARY_SHA256 = '4717a2afa56893861de161207bc2c4f094f53227099763ebfa2f0025ab72515b'


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_manifest(path, config):
    manifest = json.loads(path.read_text())
    if not manifest.get('passed') or not manifest.get('timing', {}).get('passed'):
        raise ValueError('A successful routed build manifest is required')
    probe = manifest.get('configuration', {}).get('usb2_probe', False)
    if not manifest.get('configuration', {}).get('usb2_debug') and not probe:
        raise ValueError('Manifest does not select --usb2-debug')
    name = 'usb2_probe.gao' if probe else 'usb2_debug.gao'
    if manifest.get('sha256', {}).get('config/'+name) != sha256(config):
        raise ValueError('Capture configuration differs from the build input')
    load_config(config, probe=probe)
    user_code = manifest['user_code'].upper()
    if not re.fullmatch(r'0X[0-9A-F]{8}', user_code):
        raise ValueError('Invalid candidate UserCode')
    artifacts = manifest.get('artifacts', [])
    if len(artifacts) != 1:
        raise ValueError('Expected one debug bitstream')
    artifact = artifacts[0]
    bitstream = Path(artifact['path'])
    if bitstream.suffix != '.fs' or sha256(bitstream) != artifact['sha256']:
        raise ValueError('Bitstream identity differs from the successful manifest')
    header = bitstream.read_text()[:2000]
    code = re.search(r'//UserCode:\s*(0x[0-9a-fA-F]{8})\b', header)
    if code is None or code.group(1).upper() != user_code:
        raise ValueError('Bitstream UserCode differs from the candidate')
    for value in ('//Part Number: GW5A-LV25MG121NC1/I0', '//GAOCRC: ' + (PROBE_ID if probe else GAO_ID),
                  '//SecurityBit: OFF', '//CRCCheck: ON'):
        if value not in header:
            raise ValueError('Bitstream header does not match: ' + value)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--location', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--probe', action='store_true')
    parser.add_argument('--gao-sh', type=Path, default=Path(os.environ.get(
        'GW25K_IDE_DIR', str(Path.home()/'.local/opt/gowin-1.9.12.03/IDE')))/'bin/gao_sh')
    args = parser.parse_args()
    config = PROJECT/'config'/('usb2_probe.gao' if args.probe else 'usb2_debug.gao')
    try:
        manifest = validate_manifest(args.manifest, config)
        if bool(manifest['configuration'].get('usb2_probe')) != args.probe:
            raise ValueError('Capture profile does not match the manifest')
        if sys.platform != 'linux' or sha256(args.gao_sh) != GAO_BINARY_SHA256:
            raise ValueError('This WINUSB capture recipe requires the verified Linux 1.9.12.03 gao_sh')
    except (OSError, ValueError, KeyError) as error:
        parser.exit(2, f'No capture started: {error}\n')
    args.output.mkdir(parents=True, exist_ok=False)
    record = {'started_at': datetime.now().astimezone().isoformat(), 'passed': False,
              'operation': 'read_only_GAO', 'sram_programmed': False, 'flash_programmed': False,
              'user_code': manifest['user_code'], 'manifest_sha256': sha256(args.manifest),
              'config_sha256': sha256(config), 'binary_sha256': sha256(args.gao_sh),
              'recipe_sha256': sha256(PROJECT/'tools/usb2_debug_winusb.gdb')}
    identity_command = ['gowin-programmer-cli', '--device', 'GW5A-25A', '--cable-index', '5',
                        '--location', args.location, '--frequency', '0.9MHz', '--operation_index', '0']
    try:
        with open('/tmp/gw138k_20261025.lock', 'a') as lock, tempfile.TemporaryDirectory(prefix='midi-gao-') as temporary:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            environment = dict(os.environ, TMPDIR=temporary, QT_QPA_PLATFORM='offscreen', QT_OPENGL='software',
                               LD_LIBRARY_PATH=str(args.gao_sh.parent.parent/'lib'),
                               LD_PRELOAD='/usr/lib64/libstdc++.so.6:/usr/lib64/libz.so.1:/usr/lib64/libfreetype.so.6')
            for phase in ('before', 'after'):
                identity = subprocess.run(identity_command, env=environment, text=True, capture_output=True, timeout=30)
                text = identity.stdout + identity.stderr
                (args.output/f'identity_{phase}.log').write_text(text)
                if (identity.returncode or 'Finished.' not in text or '0x0001281B' not in text
                        or manifest['user_code'].upper() not in text.upper()):
                    raise ValueError('Board identity mismatch: ' + text[-1000:])
                if phase == 'before':
                    command = ['timeout', '--kill-after=5s', '60s', 'gdb', '-nx', '-q', '-batch',
                               '-x', str(PROJECT/'tools/usb2_debug_winusb.gdb'), '--args', str(args.gao_sh),
                               '-local', '-gao', str(config), '-out', str(args.output/'capture'),
                               '-cable', 'FT2CH', '-location', args.location]
                    with (args.output/'gdb.log').open('w') as log:
                        result = subprocess.run(command, env=environment, stdin=subprocess.DEVNULL,
                                                stdout=log, stderr=subprocess.STDOUT, timeout=75)
                    record.update(command=command, returncode=result.returncode)
                    files = list(args.output.glob('capture_core*_window*.csv'))
                    if result.returncode or len(files) != 1:
                        raise ValueError('GAO capture failed; see gdb.log')
                    decoded = decode(files[0], probe=args.probe)
                    (args.output/'decoded.json').write_text(json.dumps(decoded, indent=2) + '\n')
                    record.update(csv_sha256=sha256(files[0]), decoded_sha256=sha256(args.output/'decoded.json'))
            record['passed'] = True
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        record['error'] = str(error)
    finally:
        record['finished_at'] = datetime.now().astimezone().isoformat()
        (args.output/'capture.json').write_text(json.dumps(record, indent=2) + '\n')
    if not record['passed']:
        parser.exit(1, record['error'] + '\n')
    print(json.dumps({'directory': str(args.output), 'latest': decoded['latest']}, indent=2))


if __name__ == '__main__':
    main()
