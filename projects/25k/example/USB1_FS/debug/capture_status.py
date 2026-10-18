"""Capture an already-loaded USB1 GAO image; never program FPGA or flash."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from program_sram import verified_artifact


def matching_artifacts(manifest_path, gao_id):
    artifact, _user_code, image = verified_artifact(manifest_path)
    if image != 'gao' or gao_id != '1010101001010011':
        raise ValueError('USB1 status capture requires the AA53 GAO image')
    return [artifact]


def main():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=project/'reports/last_build.json')
    parser.add_argument('--location', help='actual FTDI location from the cable scan, if needed')
    parser.add_argument('--timeout', type=int, default=30)
    parser.add_argument('--output-prefix', type=Path, help='new, unused capture prefix')
    args = parser.parse_args()
    if not 1 <= args.timeout <= 120:
        parser.error('timeout must be 1..120 seconds')
    gao = project/'debug/usb1_status.gao'
    try:
        gao_id = ElementTree.parse(gao).findtext('GAO_ID')
        artifacts = matching_artifacts(args.manifest, gao_id)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ElementTree.ParseError) as error:
        parser.exit(2, f'No capture was started: {error}\n')
    prefix = args.output_prefix or project/'reports'/(
        'usb1_status_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    prefix = prefix.resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    if list(prefix.parent.glob(prefix.name + '*')):
        parser.exit(2, 'Capture prefix already exists; choose a new prefix.\n')
    ide = Path(os.environ.get('GW25K_IDE_DIR',
        '/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE'))
    env = dict(os.environ, DYLD_LIBRARY_PATH=str(ide/'lib'),
               DYLD_FRAMEWORK_PATH=str(ide/'lib'))
    command = [str(ide/'bin/gao_sh'), '-gao', str(gao), '-device', 'GW5A-25A',
               '-cable', 'FT2CH', '-out', str(prefix)]
    if args.location:
        command += ['-location', args.location]
    result = {'started_at': datetime.now().astimezone().isoformat(),
              'gao_id': gao_id, 'manifest': str(args.manifest.resolve()),
              'gao_config': str(gao),
              'gao_config_sha256': hashlib.sha256(gao.read_bytes()).hexdigest(),
              'matching_artifacts': artifacts, 'command': command,
              'passed': False,
              'note': 'Local manifest proves file compatibility, not the identity of the loaded FPGA image.'}
    print('Capturing the already-loaded USB GAO image through FT2CH channel 0.', flush=True)
    try:
        process = subprocess.run(command, cwd=project, env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 timeout=args.timeout)
        log = process.stdout.decode(errors='replace')
        result['returncode'] = process.returncode
    except subprocess.TimeoutExpired as error:
        log = (error.stdout or b'').decode(errors='replace') + '\nCAPTURE TIMEOUT\n'
        result['error'] = 'capture timeout; check matching GAO image and running sample clock'
    except OSError as error:
        log = str(error) + '\n'
        result['error'] = str(error)
    log_path = Path(str(prefix) + '.log')
    log_path.write_text(log)
    files = sorted(prefix.parent.glob(prefix.name + '*.csv'))
    result.update({'log': str(log_path), 'csv': [str(p) for p in files],
                   'finished_at': datetime.now().astimezone().isoformat()})
    result['passed'] = result.get('returncode') == 0 and bool(files)
    Path(str(prefix) + '.json').write_text(json.dumps(result, indent=2) + '\n')
    print(log, end='')
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
