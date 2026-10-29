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
from tools.workstation_pinout import digest, parse_locations


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


def ulpi_bypass_constraints(payload, plan):
    if plan.get('ulpi_bypass') != {'U4': 'not_fitted_short', 'U5': 'not_fitted_short'}:
        raise ValueError('ULPI IO standard requires the reviewed complete bypass declaration')
    electrical = plan.get('electrical_check', {})
    supplies = {entry['part']: entry for entry in electrical.get('translators', [])}
    if (electrical.get('status') != 'no_voltage_domain_conflict_detected' or
            electrical.get('actual_board_measured') is not False or
            electrical.get('full_electrical_acceptance') is not False or electrical.get('findings') != [] or
            len(electrical.get('translators', [])) != 2 or set(supplies) != {'U4', 'U5'} or any(
                entry.get('nominal_mv') != 3300 or entry.get('phy_side') != 'B' or
                entry.get('assembly') != 'not_fitted_short' or entry.get('supply_network') != '3V3_USB3300' or
                entry.get('supply_node') != {'U4': 'U4.19', 'U5': 'U5.14'}[part]
                for part, entry in supplies.items())):
        raise ValueError('ULPI IO standard requires reviewed nominal 3V3 B-side evidence')
    text = payload.decode('utf-8')
    locations = parse_locations(text)
    ports = tuple('usb2_ulpi_data[' + str(index) + ']' for index in range(8)) + (
        'usb2_ulpi_clk', 'usb2_ulpi_dir', 'usb2_ulpi_nxt', 'usb2_ulpi_stp')
    if {port for port in locations if port.startswith('usb2_ulpi_')} != set(ports):
        raise ValueError('ULPI IO location inventory changed')
    for port in ports:
        if plan.get('ports', {}).get(port, {}).get('balls') != locations[port]:
            raise ValueError('ULPI IO location differs from the audited pinout: ' + port)
    if re.search(r'^\s*IO_PORT\s+"usb2_ulpi_', text, re.M):
        raise ValueError('ULPI IO standard already specified; refusing an implicit override')
    suffix = ('' if text.endswith('\n') else '\n') + ''.join(
        'IO_PORT "' + port + '" IO_TYPE=LVCMOS33;\n' for port in ports)
    adapted = payload + suffix.encode('utf-8')
    if parse_locations(adapted.decode('utf-8')) != locations:
        raise ValueError('ULPI IO standard adaptation changed locations')
    evidence = dict(scope='nominal_ULPI_IO_standard_only_not_external_timing_or_electrical_acceptance',
                    before_sha256=digest(payload), after_sha256=digest(adapted), io_type='LVCMOS33',
                    ports={port: locations[port] for port in ports}, locations_unchanged=True,
                    actual_board_measured=False, full_electrical_acceptance=False,
                    external_io_timing_complete=False)
    return adapted, evidence


def prepare(source, output, user_code, acknowledge_electrical_risk=False, ulpi_bypass_lvcmos33=False):
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
    if audit['top_module'] != TOP or not isinstance(audit['electrical_blocked'], bool):
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
    if ulpi_bypass_lvcmos33:
        pinout_identity = metadata.get('pinout_sha256')
        if not isinstance(pinout_identity, str) or not re.fullmatch(r'[0-9a-f]{64}', pinout_identity):
            raise ValueError('ULPI IO standard requires an audited pinout identity')
        inputs['parent_pinout.json'] = (source / 'pinout/pinout.json', pinout_identity)
    for name, (path, expected) in inputs.items():
        if sha(path) != expected:
            raise ValueError('audited physical input changed: ' + name)
    adapted_cst = None
    ulpi_adaptation = None
    if ulpi_bypass_lvcmos33:
        plan = json.loads(inputs['parent_pinout.json'][0].read_bytes())
        adapted_cst, ulpi_adaptation = ulpi_bypass_constraints(inputs['physical.cst'][0].read_bytes(), plan)
    output.mkdir(parents=True)
    for name, (path, expected) in inputs.items():
        checked_copy(path, output / name, expected)
    if adapted_cst is not None:
        (output / 'physical.cst').write_bytes(adapted_cst)
    (output / 'parent_synthesis_audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    script = implementation_script(user_code)
    (output / 'run.tcl').write_text(script)
    for name, (path, expected) in inputs.items():
        copied_expected = ulpi_adaptation['after_sha256'] if name == 'physical.cst' and ulpi_adaptation else expected
        if sha(path) != expected or sha(output / name) != copied_expected:
            raise ValueError('physical input changed after preparation: ' + name)
    result = dict(
        schema=1, identity='custom138k-native-physical-' + user_code.upper(),
        prepared_at=datetime.now().astimezone().isoformat(),
        validation_stage='offline_physical_experiment_prepared',
        source_policy=('audited_native_synthesis_netlist_with_explicit_ULPI_IO_type_only_and_unchanged_SDC'
                       if ulpi_adaptation else 'audited_native_synthesis_netlist_with_unchanged_CST_and_SDC'),
        parent_candidate=str(source), parent_identity=audit['identity'],
        preparer_sha256=sha(Path(__file__)), user_code='0x' + user_code.upper(),
        top_module=TOP, device=DEVICE, electrical_blocked=audit['electrical_blocked'],
        electrical_risk_explicitly_acknowledged=True,
        acknowledgement_scope='offline physical experiment only; not board programming authorization or electrical acceptance',
        board_programming_authorized=False, ulpi_io_type_adaptation=ulpi_adaptation,
        parent_input_sha256={name: expected for name, (_, expected) in inputs.items()},
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
    parser.add_argument('--ulpi-bypass-lvcmos33', action='store_true',
                        help='Add only reviewed bypass ULPI IO standards; no electrical or external timing acceptance')
    args = parser.parse_args()
    result = prepare(args.source, args.output, args.user_code, args.acknowledge_electrical_risk,
                     args.ulpi_bypass_lvcmos33)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
