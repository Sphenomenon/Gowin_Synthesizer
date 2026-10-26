"""Offline prototype-deployment preflight. This program never accesses hardware."""

from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.workstation_custom_board_audit import audit


def sha(source):
    return hashlib.sha256(Path(source).read_bytes()).hexdigest()


def header(text, user_code):
    fields = dict(re.findall(r'^//([^:\n]+):\s*([^\n]+)', text, re.M))
    expected = {'Device': 'GW5AST-138', 'Device Version': 'C', 'Part Number': 'GW5AST-LV138PG484AC2/I1',
                'CRCCheck': 'ON', 'Compress': 'OFF', 'Encryption': 'OFF', 'SecurityBit': 'OFF', 'SecureMode': 'OFF',
                'JTAGAsRegularIO': 'OFF', 'BackgroundProgramming': 'OFF'}
    if any(fields.get(key, '').strip() != value for key, value in expected.items()):
        raise ValueError('bitstream device, CRC, protection or configuration mode is not the audited prototype policy')
    if fields.get('UserCode', '').strip().lower() != user_code.lower():
        raise ValueError('bitstream UserCode differs from this physical candidate')
    return {**expected, 'UserCode': user_code}


def verify_timing_authorization(authorization, physical, inputs):
    authorization = Path(authorization).resolve()
    record = json.loads(authorization.read_text())
    expected = dict(physical_identity=inputs['identity'], user_code=inputs['user_code'],
                    physical_inputs_sha256=sha(physical / 'physical_inputs.json'),
                    timing_audit_sha256=sha(physical / 'timing-audit.json'),
                    bitstream_sha256=sha(physical / 'impl/pnr/custom_138k_integration.fs'),
                    sram_and_flash_authorized=True, setup_only_exception=True)
    if any(record.get(key) != value for key, value in expected.items()):
        raise ValueError('experimental timing authorization does not bind this exact candidate')
    timing = json.loads((physical / 'timing-audit.json').read_text())
    worst = timing['global_worst_ns']
    if (not record.get('user_statement') or not record.get('deployment_request') or
            worst['setup'] < -0.568 or
            any(worst[name] < 0 for name in ('hold', 'recovery', 'removal')) or
            timing['pulse_width_violations']):
        raise ValueError('experimental authorization only permits the acknowledged setup violation')
    return dict(path=str(authorization), sha256=sha(authorization), **record)


def prepare(physical, output, timing_authorization=None):
    physical, output = Path(physical).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError('do not replace existing deployment evidence')
    inputs = json.loads((physical / 'physical_inputs.json').read_text())
    if not inputs['electrical_risk_explicitly_acknowledged'] or inputs.get('hold_diagnostic_only'):
        raise ValueError('candidate lacks explicit prototype risk acknowledgement or is diagnostic-only')
    if inputs['clocks_or_exceptions_relaxed'] or inputs['features_removed']:
        raise ValueError('candidate removed features or relaxed timing')
    for name, expected in inputs['input_sha256'].items():
        if sha(physical / name) != expected:
            raise ValueError('physical input drifted: ' + name)
    source = audit(Path(inputs['parent_candidate']))
    parent = json.loads((physical / 'parent_synthesis_audit.json').read_text())
    for key in ('identity', 'integration_inputs_sha256', 'netlist_sha256'):
        if source[key] != parent[key]:
            raise ValueError('physical source no longer matches independent synthesis audit: ' + key)
    checks = {}
    waiver = None
    timing_closed = False
    for checker, report, field in [('check_timing', 'timing-audit.json', 'timing_closed'),
                                   ('check_common_cdc', 'common-cdc-audit.json', 'passed'),
                                   ('check_pll', 'pll-audit.json', 'passed'),
                                   ('check_routes', 'native-routes-audit.json', 'passed')]:
        execution = subprocess.run([sys.executable, str(Path(__file__).with_name(checker + '.py')), str(physical)])
        result = json.loads((physical / report).read_text())
        if checker == 'check_timing':
            timing_closed = result[field] is True
        if checker == 'check_timing' and execution.returncode == 1 and not timing_closed and timing_authorization:
            waiver = verify_timing_authorization(timing_authorization, physical, inputs)
        elif execution.returncode or result[field] is not True:
            raise ValueError('physical gate rejected candidate: ' + checker)
        checks[report] = sha(physical / report)
    pnr = physical / 'impl/pnr/custom_138k_integration'
    bitstream = pnr.with_suffix('.fs')
    fields = header(bitstream.read_text(), inputs['user_code'])
    output.mkdir(parents=True)
    copied = output / 'bitstream.fs'
    shutil.copyfile(bitstream, copied)
    if sha(copied) != sha(bitstream):
        raise ValueError('bitstream copy differs')
    conversion = subprocess.run(['gowin-programmer-cli', '--filestransform', '1', '--files', str(copied)],
                                capture_output=True, text=True, timeout=120)
    (output / 'offline_conversion.log').write_text(conversion.stdout + conversion.stderr)
    conversion.check_returncode()
    binary = output / 'merged.bin'
    if binary.read_bytes() != pnr.with_suffix('.bin').read_bytes():
        raise ValueError('independent official FS conversion differs from the implementation BIN')
    erase_end = (binary.stat().st_size + 65535) & ~65535
    if not binary.stat().st_size or erase_end > 0x600000:
        raise ValueError('configuration erase span overlaps the reserved model partition')
    result = dict(physical_identity=inputs['identity'], source_identity=source['identity'],
                  user_code=inputs['user_code'], device=inputs['device'], header=fields,
                  physical_inputs_sha256=sha(physical / 'physical_inputs.json'), checks_sha256=checks,
                  bitstream=str(bitstream), bitstream_sha256=sha(bitstream),
                  binary=str(binary), binary_sha256=sha(binary), binary_bytes=binary.stat().st_size,
                  configuration_erase_end=erase_end, model_byte_address=0x600000,
                  experimental_physical_gates_passed=timing_closed, timing_closed=timing_closed,
                  experimental_timing_authorization=waiver, electrical_accepted=False, release_ready=False,
                  hardware_accepted=False, sram_programmed=False, flash_programmed=False,
                  hardware_requirements=['re-identify target', 'matching full Flash backups before erase',
                                         'preserve/validate model and all other partitions',
                                         'independent SRAM/Flash verify and reload identity', 'retain rollback backup'])
    (output / 'deployment_preflight.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--physical', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--timing-authorization', type=Path)
    options = parser.parse_args()
    prepare(options.physical, options.output, options.timing_authorization)
