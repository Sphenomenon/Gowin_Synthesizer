"""Program one verified USB1 FS SRAM image; no flash operations are available."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
from xml.etree import ElementTree


def verified_artifact(manifest_path):
    project = Path(__file__).resolve().parent
    manifest = json.loads(manifest_path.read_text())
    artifacts = manifest.get('artifacts', [])
    if manifest.get('passed') is not True or len(artifacts) != 1:
        raise ValueError('Need exactly one artifact from a successful build')
    artifact = artifacts[0]
    fs = Path(artifact['path'])
    fs = (fs if fs.is_absolute() else project/fs).resolve()
    fs.relative_to(project/'builds')
    raw = fs.read_bytes()
    if fs.suffix != '.fs' or hashlib.sha256(raw).hexdigest() != artifact['sha256']:
        raise ValueError('Bitstream identity or SHA256 changed')
    header = raw[:2000].decode('ascii')
    security = re.findall(r'^//SecurityBit:\s*([^\r\n]*?)\s*$', header, re.M)
    parts = re.findall(r'^//Part Number:\s*([^\r\n]*?)\s*$', header, re.M)
    if security != ['OFF'] or parts != ['GW5A-LV25MG121NC1/I0']:
        raise ValueError('Bitstream device or readback protection does not match')
    user_codes = re.findall(r'^//UserCode:\s*(0x[0-9a-fA-F]+)\s*$', header, re.M)
    if len(user_codes) != 1:
        raise ValueError('Missing unique bitstream UserCode')
    gao_ids = re.findall(r'^//GAOCRC:\s*([^\r\n]*?)\s*$', header, re.M)
    if '//GAOCRC' in header and len(gao_ids) != 1:
        raise ValueError('Missing unique bitstream GAO identity')
    image = 'gao' if gao_ids else 'ordinary'
    if gao_ids:
        gao = project/'debug'/'usb1_status.gao'
        gao_bytes = gao.read_bytes()
        expected_ids = ElementTree.fromstring(gao_bytes).findall('GAO_ID')
        if (len(expected_ids) != 1 or expected_ids[0].text is None
                or not re.fullmatch(r'[01]{16}', expected_ids[0].text.strip())
                or gao_ids != [expected_ids[0].text.strip()]):
            raise ValueError('Local GAO XML and bitstream GAO identity do not match')
        definitions = manifest.get('gao', [])
        if len(definitions) != 1:
            raise ValueError('Need exactly one recorded GAO build input')
        definition = Path(definitions[0]['definition'])
        definition = (definition if definition.is_absolute() else project/definition).resolve()
        if (definition != gao or gao.resolve() != gao
                or definitions[0]['sha256'] != hashlib.sha256(gao_bytes).hexdigest()):
            raise ValueError('Current local GAO XML differs from the recorded build input')
    elif manifest.get('gao'):
        raise ValueError('Ordinary bitstream has unexpected GAO build inputs')
    reports = list(fs.parent.glob('*.tr'))
    if len(reports) != 1 or reports[0].resolve().parent != fs.parent:
        raise ValueError('Missing unique local timing report')
    timing = reports[0].read_text()
    for analysis in ('Setup', 'Hold'):
        counts = re.findall(r'<Numbers of '+analysis+r' Violated Endpoints>:\s*(\d+)\b', timing)
        if counts != ['0']:
            raise ValueError(analysis+' timing did not pass')
    return {**artifact, 'path': str(fs)}, int(user_codes[0], 16), image


def main():
    project = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    try:
        artifact, expected_user, image = verified_artifact(args.manifest)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ElementTree.ParseError) as error:
        parser.exit(2, 'No programming started: '+str(error)+'\n')
    if args.check_only:
        print(json.dumps({'verified': True, 'image': image, 'artifact': artifact,
                          'user_code': hex(expected_user)}, indent=2))
        return 0
    run = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    reports = project/'reports'
    reports.mkdir(exist_ok=True)
    log = reports/('sram_usb1_'+image+'_'+run+'.log')
    command = ['/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/Programmer/bin/programmer_cli',
               '--device', 'GW5A-25A', '--operation_index', '4',
               '--fsFile', artifact['path'], '--cable-index', '1',
               '--channel', '0', '--frequency', '15MHz']
    result = {'time': datetime.now().astimezone().isoformat(), 'image': image,
              'command': command, 'manifest': str(args.manifest.resolve()),
              'file_sha256': artifact['sha256'], 'passed': False, 'log': str(log)}
    with log.open('x') as output:
        try:
            process = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=60)
            result['returncode'] = process.returncode
        except (subprocess.TimeoutExpired, OSError) as error:
            result['error'] = str(error)
    text = log.read_text(errors='replace')
    user_codes = re.findall(r'User Code is:\s*(0x[0-9a-fA-F]+)', text)
    statuses = re.findall(r'Status Code is:\s*(0x[0-9a-fA-F]+)', text)
    error = bool(re.search(r'\berror\b|\bfailed\b|\bfailure\b', text, re.I))
    passed = (result.get('returncode') == 0 and not error and 'Finished.' in text
              and bool(user_codes) and all(int(value, 16) == expected_user for value in user_codes)
              and bool(statuses) and all(int(value, 16) == 0x70022020 for value in statuses))
    result.update({'user_code': user_codes, 'status_code': statuses, 'error_in_output': error,
                   'finished': 'Finished.' in text, 'passed': passed})
    with log.with_suffix('.json').open('x') as output:
        output.write(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
    if not passed:
        print(text[-2000:])
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
