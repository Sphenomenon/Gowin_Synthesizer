#!/usr/bin/env python3
"""Read-only candidate/input/USB inventory; never program or reset a device."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).resolve().parents[1]
WORKSPACE = PROJECT.parents[1]
DEFAULT_BUILD = PROJECT / 'results/build_20260909_222148_268152'
EXPECTED_SHA = '0edbf86df9fd8984bdb4abb73283d9f36c651df4c228444a55c32aef0033a509'
EXPECTED_PART = 'GW5AST-LV138PG484AC2/I1'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(args):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=20)
        return {'argv': args, 'exit_code': p.returncode,
                'stdout': p.stdout, 'stderr': p.stderr}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {'argv': args, 'error': str(error)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--build', type=Path, default=DEFAULT_BUILD)
    parser.add_argument('--expected-sha', help='explicit SHA-256 required for any non-default candidate')
    args = parser.parse_args()
    build = args.build.resolve()
    if build != DEFAULT_BUILD.resolve() and not args.expected_sha:
        parser.error('--expected-sha is required with a new --build')
    expected_sha = args.expected_sha or EXPECTED_SHA
    out = (args.output or PROJECT / 'results' /
           datetime.now().strftime('board_preflight_%Y%m%d_%H%M%S_%f')).resolve()
    out.mkdir(parents=True, exist_ok=False)
    stage = build / 'Prj1'
    manifest = json.loads((build / 'migration_inputs.json').read_text())
    evidence = json.loads((stage / 'build/build_evidence.json').read_text())
    audio = json.loads((build / 'audio_routed_audit.json').read_text())
    mismatches = []
    for relative, digest in manifest['staged_sha256'].items():
        path = stage / relative
        if not path.is_file() or sha(path) != digest:
            mismatches.append(relative)
    rtl_mismatches = []
    frozen_rtl = list((stage / 'src/migration').iterdir())
    for frozen in frozen_rtl:
        path = PROJECT / 'rtl' / frozen.name
        if not path.is_file() or sha(path) != sha(frozen):
            rtl_mismatches.append(frozen.name)
    additional_rtl = sorted(p.name for p in (PROJECT / 'rtl').iterdir()
                            if p.suffix in ('.v', '.sv') and not (stage / 'src/migration' / p.name).exists())
    artifact_mismatches = []
    for name, key in [('Prj1.fs', 'bitstream_sha256'),
                      ('Prj1.tr', 'timing_report_sha256'),
                      ('Prj1.sdf', 'sdf_sha256'),
                      ('Prj1.vo', 'routed_netlist_sha256')]:
        if sha(stage / 'impl/pnr' / name) != evidence[key]:
            artifact_mismatches.append(name)
    device = ET.parse(stage / 'Prj1.gprj').find('Device').attrib
    bit_sha = sha(stage / 'impl/pnr/Prj1.fs')
    checks = {
        'candidate_sha_matches': bit_sha == expected_sha,
        'build_evidence_artifacts_match': not artifact_mismatches,
        'frozen_inputs_match': not mismatches,
        'current_migration_rtl_matches_candidate': not rtl_mismatches,
        'target_part_matches': device['pn'] == EXPECTED_PART and device['name'] == 'GW5AST-138C',
        'setup_hold_zero': evidence['setup_violated_endpoints'] == 0 and evidence['hold_violated_endpoints'] == 0,
        'audio_routed_audit_passed': audio['passed'] and audio['bitstream_sha256'] == bit_sha,
    }
    usb = []
    for path in sorted(Path('/sys/bus/usb/devices').glob('*')):
        if (path / 'idVendor').is_file():
            row = {'sysfs': path.name}
            for key in ['idVendor', 'idProduct', 'manufacturer', 'product', 'serial']:
                if (path / key).is_file():
                    row[key] = (path / key).read_text().strip()
            usb.append(row)
    probes = command(['openFPGALoader', '--scan-usb'])
    serial = sorted(str(p) for glob in ('ttyUSB*', 'ttyACM*') for p in Path('/dev').glob(glob))
    report = {
        'created_at': datetime.now().astimezone().isoformat(),
        'candidate': str(stage / 'impl/pnr/Prj1.fs'), 'bitstream_sha256': bit_sha,
        'configured_target': device, 'checks': checks,
        'candidate_evidence_passed': all(checks.values()),
        'frozen_input_count': len(manifest['staged_sha256']),
        'frozen_input_mismatches': mismatches, 'current_rtl_mismatches': rtl_mismatches,
        'additional_rtl_not_in_this_bitstream': additional_rtl,
        'artifact_mismatches': artifact_mismatches,
        'usb_devices': usb, 'serial_devices': serial, 'probe_scan': probes,
        'hardware_identity_confirmed': False, 'programmed': False, 'hardware_tested': False,
        'note': 'USB enumeration does not confirm FPGA identity, package, revision or wiring. JTAG scan and physical confirmation remain required.',
    }
    (out / 'preflight.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    status = command(['git', '-C', str(WORKSPACE / 'Mega_138K/Dev'), 'status', '--porcelain=v1', '-uall'])
    (out / 'git_status.txt').write_text(status.get('stdout', '') + status.get('stderr', ''))
    print(json.dumps({'output': str(out), 'candidate_evidence_passed': all(checks.values()),
                      'frozen_input_count': len(manifest['staged_sha256']),
                      'serial_devices': serial, 'probe_scan': probes,
                      'programmed': False, 'hardware_tested': False}, ensure_ascii=False, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
