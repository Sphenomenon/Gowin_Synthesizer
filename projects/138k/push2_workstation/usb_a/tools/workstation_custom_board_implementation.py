"""Prepare an explicit physical experiment from an audited native netlist.

This does not change synthesis-only defaults, approve electrical safety, or
program hardware. Physical and deployment results require separate evidence.
"""

from pathlib import Path
from datetime import datetime
import argparse
import json
import re
import shutil

from tools.stage_usb_firmware import sha
from tools.workstation_custom_board_audit import audit as audit_synthesis


BASE = 'custom_138k_integration'
TOP = 'workstation_custom_138k_top'
DEVICE = 'GW5AST-LV138PG484AC2/I1'


def implementation_script(user_code, place_option=2, route_option=0, replicate_resources=False):
    if not re.fullmatch(r'[0-9A-Fa-f]{8}', user_code):
        raise ValueError('a new eight-hex UserCode is required')
    if place_option not in range(5) or route_option not in (0, 1):
        raise ValueError('unsupported physical implementation algorithm')
    return (
        'set root [file normalize [file dirname [info script]]]\n'
        'cd $root\n'
        f'set_device {DEVICE} -device_version C\n'
        'set_option -synthesis_tool gowinsynthesis\n'
        f'set_option -top_module {TOP}\n'
        f'set_option -output_base_name {BASE}\n'
        'set_option -verilog_std sysv2017\n'
        'set_option -use_mspi_as_gpio 1\n'
        'set_option -use_cpu_as_gpio 1\n'
        'add_file -type cst [file join $root physical.cst]\n'
        'add_file -type sdc [file join $root physical.sdc]\n'
        f'add_file -type netlist [file join $root {BASE}.vg]\n'
        f'set_option -user_code {user_code.upper()}\n'
        'set_option -bit_security 0\n'
        'set_option -secure_mode 0\n'
        'set_option -bit_encrypt 0\n'
        'set_option -bit_compress 0\n'
        'set_option -gen_text_timing_rpt 1\n'
        'set_option -gen_sdf 1\n'
        'set_option -gen_verilog_sim_netlist 1\n'
        'set_option -timing_driven 1\n'
        'set_option -correct_hold_violation 1\n'
        f'set_option -place_option {place_option}\n'
        f'set_option -route_option {route_option}\n'
        f'set_option -replicate_resources {int(replicate_resources)}\n'
        'run pnr\n'
    )


def checked_copy(source, destination, expected):
    if sha(source) != expected:
        raise ValueError('physical input changed before copy: ' + str(source))
    shutil.copyfile(source, destination)
    if sha(destination) != expected:
        raise ValueError('physical input changed during copy: ' + str(source))


def prepare(source, output, user_code, acknowledge_electrical_risk=False):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not acknowledge_electrical_risk:
        raise ValueError('explicit acknowledgement of unresolved electrical risk is required')
    if not re.fullmatch(r'[0-9A-Fa-f]{8}', user_code):
        raise ValueError('a new eight-hex UserCode is required')
    if output.exists():
        raise FileExistsError('physical output already exists: ' + str(output))
    if source in output.parents:
        raise ValueError('physical output must not modify the parent candidate')
    audit = audit_synthesis(source)
    if audit['top_module'] != TOP or audit['electrical_blocked'] is not True:
        raise ValueError('unexpected native synthesis/electrical identity')
    manifest = source / 'integration_inputs.json'
    if sha(manifest) != audit['integration_inputs_sha256']:
        raise ValueError('parent manifest changed after synthesis audit')
    metadata = json.loads(manifest.read_text())
    stage = source / 'workstation/Prj1'
    inputs = {
        BASE + '.vg': (stage / f'impl/gwsynthesis/{BASE}.vg', audit['netlist_sha256']),
        'physical.cst': (stage / 'constraints/custom_138k.cst',
                         metadata['staged_input_sha256']['constraints/custom_138k.cst']),
        'physical.sdc': (stage / 'constraints/custom_138k.sdc',
                         metadata['staged_input_sha256']['constraints/custom_138k.sdc']),
        'parent_integration_inputs.json': (manifest, audit['integration_inputs_sha256']),
    }
    for name, (path, expected) in inputs.items():
        if sha(path) != expected:
            raise ValueError('audited physical input changed: ' + name)
    output.mkdir(parents=True)
    for name, (path, expected) in inputs.items():
        checked_copy(path, output / name, expected)
    (output / 'parent_synthesis_audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    script = implementation_script(user_code)
    (output / 'run.tcl').write_text(script)
    for name, (path, expected) in inputs.items():
        if sha(path) != expected or sha(output / name) != expected:
            raise ValueError('physical input changed after preparation: ' + name)
    result = dict(
        schema=1, identity='custom138k-native-physical-' + user_code.upper(),
        prepared_at=datetime.now().astimezone().isoformat(),
        validation_stage='offline_physical_experiment_prepared',
        source_policy='audited_native_synthesis_netlist_with_unchanged_CST_and_SDC',
        parent_candidate=str(source), parent_identity=audit['identity'],
        preparer_sha256=sha(Path(__file__)), user_code='0x' + user_code.upper(),
        top_module=TOP, device=DEVICE, electrical_blocked=True,
        electrical_risk_explicitly_acknowledged=True,
        acknowledgement_scope='physical experiment and requested deployment; not electrical acceptance',
        clocks_or_exceptions_relaxed=False, features_removed=False,
        place_option=2, route_option=0, replicate_resources=False,
        input_sha256={path.name: sha(path) for path in output.iterdir() if path.is_file()},
        timing_closed=False, physical_gates_passed=False, hardware_tested=False,
        deployment_allowed=False, release_ready=False, bitstream_sha256=None,
        sram_programmed=False, flash_programmed=False,
        remaining_gaps=metadata['remaining_gaps'],
    )
    (output / 'physical_inputs.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--user-code', required=True)
    parser.add_argument('--acknowledge-electrical-risk', action='store_true')
    args = parser.parse_args()
    result = prepare(args.source, args.output, args.user_code, args.acknowledge_electrical_risk)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
