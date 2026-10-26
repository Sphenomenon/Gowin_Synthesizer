"""Derive a dated P&R search variant without changing audited RTL or SDC."""

from pathlib import Path
from datetime import datetime
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools import workstation_custom_board_implementation as implementation
from tools.stage_usb_firmware import sha


def derive(source, output, user_code, place_option, route_option, replicate_resources, disable_auto_hold_repair=False,
           ddr_hold_floorplan=False):
    source, output = Path(source).resolve(), Path(output).resolve()
    script = implementation.implementation_script(user_code, place_option, route_option, replicate_resources)
    if disable_auto_hold_repair:
        anchor = 'set_option -correct_hold_violation 1\n'
        if script.count(anchor) != 1:
            raise ValueError('automatic hold-repair diagnostic anchor drifted')
        script = script.replace(anchor, 'set_option -correct_hold_violation 0\n')
    if output.exists() or source in output.parents:
        raise ValueError('a new independent physical output is required')
    previous = json.loads((source / 'physical_inputs.json').read_text())
    if previous['user_code'].lower() == ('0x' + user_code).lower():
        raise ValueError('a new physical UserCode is required')
    for name, expected in previous['input_sha256'].items():
        if Path(name).name != name or sha(source / name) != expected:
            raise ValueError('parent physical input drifted: ' + name)
    audit = json.loads((source / 'parent_synthesis_audit.json').read_text())
    if audit['identity'] not in ('custom138k-native-integration-20261025-a18',
                               'custom138k-native-integration-20261025-a19',
                               'custom138k-native-integration-20261025-a23') or not previous['electrical_risk_explicitly_acknowledged']:
        raise ValueError('only an acknowledged audited dated a18/a19/a23 experiment can be derived')
    placement = None
    if ddr_hold_floorplan:
        if not audit['identity'].endswith('-a23') or disable_auto_hold_repair:
            raise ValueError('DDR hold floorplan needs the audited a23 minimum-delay policy and automatic repair')
        instance = 'u_memory/u_ddr3/gw3_top/u_ddr_phy_top/wloadn_3_s0'
        minimum = f'set_min_delay 0.800 -from [get_pins {{u_memory/u_ddr3/gw3_top/u_ddr_phy_top/ddr_init_internal_r_s0/Q}}] -to [get_pins {{{instance}/D}}]'
        if minimum not in (source / 'physical.sdc').read_text().splitlines() or instance in (source / 'physical.cst').read_text():
            raise ValueError('DDR hold floorplan source policy drifted')
        placement = dict(instance=instance, region='R[40:50]C[70:90]',
                         constraint=f'INS_LOC "{instance}" R[40:50]C[70:90];',
                         reason='separate launch/capture placement to satisfy the existing physical minimum delay')
    if sha(source / 'parent_integration_inputs.json') != audit['integration_inputs_sha256']:
        raise ValueError('parent synthesis manifest binding changed')
    netlists = [name for name in previous['input_sha256'] if name.endswith('.vg')]
    if len(netlists) != 1 or sha(source / netlists[0]) != audit['netlist_sha256']:
        raise ValueError('audited synthesis netlist binding changed')
    output.mkdir(parents=True)
    names = ('physical.cst', 'physical.sdc', 'parent_synthesis_audit.json', 'parent_integration_inputs.json')
    for name in names:
        implementation.checked_copy(source / name, output / name, previous['input_sha256'][name])
    if placement:
        physical_cst = output / 'physical.cst'
        physical_cst.write_text(physical_cst.read_text() + '\n' + placement['constraint'] + '\n')
    implementation.checked_copy(source / netlists[0], output / (implementation.BASE + '.vg'), audit['netlist_sha256'])
    implementation.checked_copy(source / 'physical_inputs.json', output / 'parent_physical_inputs.json',
                                sha(source / 'physical_inputs.json'))
    (output / 'run.tcl').write_text(script)
    result = dict(previous)
    result.update(identity='custom138k-native-physical-' + user_code.upper(),
                  user_code='0x' + user_code.upper(),
                  prepared_at=datetime.now().astimezone().isoformat(),
                  parent_physical_identity=previous['identity'], parent_physical_directory=str(source),
                  place_option=place_option, route_option=route_option, replicate_resources=replicate_resources,
                  automatic_hold_repair=not disable_auto_hold_repair,
                  ddr_hold_floorplan=placement,
                  hold_diagnostic_only=disable_auto_hold_repair, full_timing_gates_required=True,
                  bit_security=False, secure_mode=False, encrypted=False, compressed=False,
                  netlist_sha256=audit['netlist_sha256'],
                  validation_stage='offline_physical_variant_prepared',
                  preparer_sha256=sha(Path(__file__)), implementation_tool_sha256=sha(Path(implementation.__file__)),
                  input_sha256={path.name: sha(path) for path in output.iterdir() if path.is_file()},
                  physical_gates_passed=False, timing_closed=False, deployment_allowed=False,
                  release_ready=False, hardware_tested=False, bitstream_sha256=None,
                  sram_programmed=False, flash_programmed=False)
    (output / 'physical_inputs.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--user-code', required=True)
    parser.add_argument('--place-option', type=int, choices=range(5), required=True)
    parser.add_argument('--route-option', type=int, choices=(0, 1), required=True)
    parser.add_argument('--replicate-resources', action='store_true')
    parser.add_argument('--disable-auto-hold-repair', action='store_true')
    parser.add_argument('--ddr-hold-floorplan', action='store_true')
    args = parser.parse_args()
    print(json.dumps(derive(args.source, args.output, args.user_code, args.place_option,
                            args.route_option, args.replicate_resources, args.disable_auto_hold_repair,
                            args.ddr_hold_floorplan), indent=2))
