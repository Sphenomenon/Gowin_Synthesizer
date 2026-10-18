"""Capture an already-loaded USB2 GAO image; never program FPGA or flash."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
from xml.etree import ElementTree


GAO_ID = '1101001010100110'  # D2A6; distinct from USB1 AA53 and BLE 4C64.
IMAGE_CONFIGS = {
    'probe': ('usb2_status.gao', GAO_ID, 'usb2_status_'),
    'serial': ('usb2_serial_status.gao', '1101001010100111', 'usb2_serial_status_'),
    'activity': ('usb2_activity_status.gao', '1101001010101000', 'usb2_activity_status_'),
    'termination': ('usb2_termination_status.gao', '1101001010101001', 'usb2_termination_status_'),
    'rxcmd': ('usb2_rxcmd_status.gao', '1101001010101010', 'usb2_rxcmd_status_'),
    'reset': ('usb2_reset_status.gao', '1101001010101011', 'usb2_reset_status_'),
    'buscheck': ('usb2_buscheck_status.gao', '1101001010101100', 'usb2_buscheck_status_'),
    'lowpower': ('usb2_lowpower_status.gao', '1101001010101101', 'usb2_lowpower_status_'),
    'lowpower_pd': ('usb2_lowpower_pd_status.gao', '1101001010101110', 'usb2_lowpower_pd_status_'),
    'hs': ('usb2_hs_status.gao', '1101001010110000', 'usb2_hs_status_'),
    'measure': ('usb2_measure_status.gao', '1101001010101111', 'usb2_measure_status_'),
}


def load_capture_config(path, expected_id=GAO_ID):
    if path.suffix != '.gao':
        raise ValueError('USB2 capture requires the post-synthesis .gao definition')
    root = ElementTree.parse(path).getroot()
    core = root.find('AoCore')
    if (root.findtext('GAO_ID') != expected_id or root.findtext('Mode') != 'Standard'
            or core is None or core.get('module_name') != 'usb2_device_top'
            or core.get('sample_clock') != 'clk_50mhz'
            or core.get('storage_depth') != '128'):
        raise ValueError('USB2 GAO identity, module, clock, or capture depth does not match')
    bus = core.find('SignalList/Bus')
    expected = [f'status_50mhz[{bit}]' for bit in range(63, -1, -1)]
    if (bus is None or bus.get('name') != 'status_50mhz[63:0]'
            or [signal.text for signal in bus.findall('Signal')] != expected):
        raise ValueError('USB2 GAO status bus is not the expected 64-bit capture')
    return expected_id


def matching_artifacts(manifest_path, gao_id):
    manifest = json.loads(manifest_path.read_text())
    if not manifest.get('passed'):
        raise ValueError('manifest does not describe a successful build')
    matches = []
    for artifact in manifest.get('artifacts', []):
        path = Path(artifact['path'])
        if path.suffix != '.fs':
            continue
        data = path.read_bytes()
        if ('//GAOCRC: ' + gao_id).encode() not in data[:2000]:
            continue
        digest = hashlib.sha256(data).hexdigest()
        if digest != artifact.get('sha256'):
            raise ValueError('GAO artifact SHA256 does not match the successful manifest: ' + str(path))
        matches.append({'path': str(path), 'sha256': digest})
    if not matches:
        raise ValueError('successful manifest contains no bitstream with this USB GAO_ID')
    return matches


def main():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', choices=tuple(IMAGE_CONFIGS), default='probe',
                        help='GAO image identity to capture (default: probe)')
    parser.add_argument('--manifest', type=Path, default=project/'reports/last_build.json')
    parser.add_argument('--location', help='actual FTDI location from the cable scan, if needed')
    parser.add_argument('--timeout', type=int, default=30)
    parser.add_argument('--output-prefix', type=Path, help='new, unused capture prefix')
    args = parser.parse_args()
    if not 1 <= args.timeout <= 120:
        parser.error('timeout must be 1..120 seconds')
    config_name, expected_id, capture_prefix = IMAGE_CONFIGS[args.image]
    gao = project/'debug'/config_name
    try:
        gao_id = load_capture_config(gao, expected_id)
        artifacts = matching_artifacts(args.manifest, gao_id)
    except (OSError, ValueError, KeyError, ElementTree.ParseError) as error:
        parser.exit(2, f'No capture was started: {error}\n')
    prefix = args.output_prefix or project/'reports'/(
        capture_prefix + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
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
              'image': args.image,
              'gao_id': gao_id, 'manifest': str(args.manifest.resolve()),
              'gao_config': str(gao),
              'gao_config_sha256': hashlib.sha256(gao.read_bytes()).hexdigest(),
              'matching_artifacts': artifacts, 'command': command,
              'passed': False,
              'note': 'Local manifest proves file compatibility, not the identity of the loaded FPGA image.'}
    print(f'Capturing the already-loaded USB2 {args.image} GAO image through FT2CH channel 0.', flush=True)
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
