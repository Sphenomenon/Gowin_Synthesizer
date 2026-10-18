"""Program one verified USB2 SRAM image. This tool has no flash operations."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
from xml.etree import ElementTree


def verified_artifact(manifest_path, image):
    project = Path(__file__).resolve().parent
    manifest = json.loads(manifest_path.read_text())
    if not manifest.get('passed') or len(manifest.get('artifacts', [])) != 1:
        raise ValueError('Need exactly one artifact from a successful build')
    artifact = manifest['artifacts'][0]
    fs = Path(artifact['path'])
    if not fs.is_absolute():
        fs = project/fs
    fs = fs.resolve()
    fs.relative_to(project/'builds')
    raw = fs.read_bytes()
    if fs.suffix != '.fs' or hashlib.sha256(raw).hexdigest() != artifact['sha256']:
        raise ValueError('Bitstream identity or SHA256 changed')
    header = raw[:2000].decode()
    gao_name = {'probe': 'usb2_status.gao', 'serial': 'usb2_serial_status.gao',
                'activity': 'usb2_activity_status.gao',
                'termination': 'usb2_termination_status.gao',
                'rxcmd': 'usb2_rxcmd_status.gao',
                'reset': 'usb2_reset_status.gao',
                'buscheck': 'usb2_buscheck_status.gao',
                'lowpower': 'usb2_lowpower_status.gao',
                'lowpower_pd': 'usb2_lowpower_pd_status.gao',
                'measure': 'usb2_measure_status.gao',
                'hs': 'usb2_hs_status.gao'}[image]
    gao = project/'debug'/gao_name
    expected_id = ElementTree.parse(gao).getroot().findtext('GAO_ID')
    required = ('//SecurityBit: OFF', '//Part Number: GW5A-LV25MG121NC1/I0',
                '//GAOCRC: '+expected_id)
    if not all(token in header for token in required):
        raise ValueError('Bitstream device, readback protection or GAO identity does not match')
    if not any(entry['sha256'] == hashlib.sha256(gao.read_bytes()).hexdigest()
               for entry in manifest.get('gao', [])):
        raise ValueError('Current GAO XML differs from the actual build input')
    reports = list(fs.parent.glob('*.tr'))
    if len(reports) != 1:
        raise ValueError('Missing unique timing report')
    timing = reports[0].read_text()
    for analysis in ('Setup', 'Hold'):
        if not re.search(r'<Numbers of '+analysis+r' Violated Endpoints>:0\b', timing):
            raise ValueError(analysis+' timing did not pass')
    user_code = int(re.search(r'//UserCode: (0x[0-9a-fA-F]+)', header).group(1), 16)
    return {**artifact, 'path': str(fs)}, user_code


def main():
    project = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--image', choices=('hs',), default='hs')
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    try:
        artifact, expected_user = verified_artifact(args.manifest, args.image)
    except (OSError, ValueError, KeyError, AttributeError) as error:
        parser.exit(2, 'No programming started: '+str(error)+'\n')
    if args.check_only:
        print(json.dumps({'verified': True, 'artifact': artifact,
                          'user_code': hex(expected_user)}, indent=2))
        return 0
    run = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    log = project/'reports'/('sram_usb2_'+args.image+'_'+run+'.log')
    command = ['/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/Programmer/bin/programmer_cli',
               '--device', 'GW5A-25A', '--operation_index', '4',
               '--fsFile', artifact['path'], '--cable-index', '1',
               '--channel', '0', '--frequency', '15MHz']
    result = {'time': datetime.now().astimezone().isoformat(), 'image': args.image,
              'command': command, 'manifest': str(args.manifest.resolve()),
              'file_sha256': artifact['sha256'], 'passed': False, 'log': str(log)}
    with log.open('w') as output:
        try:
            process = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=60)
            result['returncode'] = process.returncode
        except subprocess.TimeoutExpired:
            result['error'] = 'Programmer timed out; no successful programming claimed'
    text = log.read_text(errors='replace')
    uc = re.findall(r'User Code is:\s*(0x[0-9a-fA-F]+)', text)
    status = re.findall(r'Status Code is:\s*(0x[0-9a-fA-F]+)', text)
    error = bool(re.search(r'Error:|Verify failed|failed to|Error \(', text, re.I))
    passed = (result.get('returncode') == 0 and not error and 'Finished.' in text
              and bool(uc) and int(uc[-1], 16) == expected_user
              and bool(status) and int(status[-1], 16) == 0x70022020)
    result.update({'user_code': uc, 'status_code': status, 'error_in_output': error,
                   'finished': 'Finished.' in text, 'passed': passed})
    log.with_suffix('.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
    if not passed:
        print(text[-2000:])
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
