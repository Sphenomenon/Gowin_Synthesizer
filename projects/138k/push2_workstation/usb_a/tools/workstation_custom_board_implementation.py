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
from tools.workstation_synthesis_netlist import SynthesisNetlist


BASE = 'custom_138k_integration'
TOP = 'workstation_custom_138k_top'
DEVICE = 'GW5AST-LV138PG484AC2/I1'
DDR_PHY = 'u_memory/u_ddr3/gw3_top/u_ddr_phy_top'
DDR_LAUNCH = DDR_PHY + '/ddr_init_internal_r_s0'
DDR_CAPTURE = DDR_PHY + '/wloadn_3_s0'
DDR_CAPTURE_REGION = 'R[40:50]C[70:90]'
DDR_CAPTURE_CONSTRAINT = f'INS_LOC "{DDR_CAPTURE}" {DDR_CAPTURE_REGION};'
DDR_MINIMUM = f'set_min_delay 0.800 -from [get_pins {{{DDR_LAUNCH}/Q}}] -to [get_pins {{{DDR_CAPTURE}/D}}]'
# DQS hard sites may use border row111; ordinary logic ends at row110.
DDR_DQS_HOLD_REGIONS = tuple(f'R[{104-10*lane}:{min(110,118-10*lane)}]C[2:30]' for lane in range(4))


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


def ddr_capture_region_constraints(payload, sdc, routed_netlist):
    """Check the observed encrypted-DDR boundary, then append one placement.

    The synthesis VG contains encrypted DDR. Its hash-bound previous route VO
    supplies structural evidence; this does not claim that a new route passes.
    """
    text = payload.decode('utf-8')
    if DDR_CAPTURE in text:
        raise ValueError('DDR capture target already appears in the parent CST')
    required = (
        'INS_LOC "u_memory/u_pll/u_pll_0/PLL_inst" PLL_L[0];',
        f'INS_LOC "{DDR_PHY}/u_dll" DDRDLLM_BL;',
        f'INS_LOC "{DDR_PHY}/fclkdiv" LEFTSIDE[4];')
    if any(text.splitlines().count(line) != 1 for line in required):
        raise ValueError('DDR hard-resource locations changed')
    related = [line for line in sdc.decode('utf-8').splitlines()
               if re.match(r'\s*set_min_delay\b', line) and
               (DDR_LAUNCH in line or DDR_CAPTURE in line)]
    if related != [DDR_MINIMUM]:
        raise ValueError('DDR capture requires the unique exact 0.800ns minimum-delay constraint')
    netlist = SynthesisNetlist(routed_netlist, TOP)
    required_cells = (DDR_LAUNCH, DDR_CAPTURE, DDR_PHY + '/fclkdiv', 'clk_50m_ibuf')
    if any(name not in netlist.cells for name in required_cells):
        raise ValueError('DDR capture observed routed boundary is missing')
    launch, capture, divider, ibuf = (netlist.cells[name] for name in required_cells)
    if any(cell['kind'] != 'DFFCE' or cell['parameters'].get('INIT') != "1'b0" or
           set(cell['ports']) != {'D', 'Q', 'CLK', 'CE', 'CLEAR'} for cell in (launch, capture)):
        raise ValueError('DDR capture observed FF type/INIT/pins changed')
    power = {netlist.pin(name, 'V') for name, cell in netlist.cells.items() if cell['kind'] == 'VCC'}
    if (netlist.pin(DDR_LAUNCH, 'Q') != netlist.pin(DDR_CAPTURE, 'D') or
            netlist.pin(DDR_LAUNCH, 'CLEAR') != netlist.pin(DDR_CAPTURE, 'CLEAR') or
            any(netlist.pin(name, 'CE') not in power for name in (DDR_LAUNCH, DDR_CAPTURE))):
        raise ValueError('DDR capture observed direct data/reset/enable topology changed')
    if (divider['kind'] != 'CLKDIV' or divider['parameters'].get('DIV_MODE') != '"4"' or
            launch['ports']['CLK'] != divider['ports'].get('CLKOUT') or
            ibuf['kind'] != 'IBUF' or ibuf['ports'].get('I') != 'clk_50m' or
            capture['ports']['CLK'] != ibuf['ports'].get('O')):
        raise ValueError('DDR capture observed UI divide4/direct50MHz clock boundary changed')
    adapted = payload + ('\n' + DDR_CAPTURE_CONSTRAINT + '\n').encode('utf-8')
    if not adapted.startswith(payload) or parse_locations(adapted.decode('utf-8')) != parse_locations(text):
        raise ValueError('DDR capture placement unexpectedly changed parent constraints or IO locations')
    return adapted, dict(
        instance=DDR_CAPTURE, region=DDR_CAPTURE_REGION, constraint=DDR_CAPTURE_CONSTRAINT,
        before_sha256=digest(payload), after_sha256=digest(adapted),
        exact_appended_bytes_hex=adapted[len(payload):].hex(),
        parent_bytes_preserved=True, io_locations_unchanged=True, hard_locations_unchanged=True,
        minimum_delay_ns=0.8, minimum_delay_constraint=DDR_MINIMUM, sdc_unchanged=True,
        observed_topology=dict(launch=DDR_LAUNCH, capture=DDR_CAPTURE,
                               launch_clock=launch['ports']['CLK'], capture_clock=capture['ports']['CLK'],
                               launch_clock_divide=4, capture_clock_mhz=50, direct_Q_to_D=True),
        topology_evidence_scope='hash_bound_previous_route_VO_of_same_encrypted_synthesis_VG',
        new_route_verified=False, new_hold_slack_ns=None)


def ddr_dqs_hold_region_constraints(payload, sdc, routed_netlist, *, lut_only=False):
    """Keep the vendor logic intact and place four observed HOLD boundaries.

    This follows the exact previous-route FF -> LUT2 -> DQS topology. It
    neither declares these paths static nor changes their timing exceptions.
    """
    text = payload.decode('utf-8')
    if text.splitlines().count(DDR_CAPTURE_CONSTRAINT) != 1:
        raise ValueError('DQS HOLD experiment requires the original capture-region constraint')
    # Reuse the complete hard-resource/min-delay/clock boundary check without
    # appending another capture constraint or changing the original payload.
    ddr_capture_region_constraints(text.replace(DDR_CAPTURE_CONSTRAINT, '').encode(), sdc, routed_netlist)
    netlist = SynthesisNetlist(routed_netlist, TOP)
    power = {netlist.pin(name, 'V') for name, cell in netlist.cells.items() if cell['kind'] == 'VCC'}
    lanes, constraints = [], []
    for lane, region in enumerate(DDR_DQS_HOLD_REGIONS):
        config = f'{DDR_PHY}/u_ddr_init/read_rclksel_conf_{lane}_s0'
        gate = f'{DDR_PHY}/u_ddr_init/hold_Z_{lane}_s'
        dqs = f'{DDR_PHY}/u_ddr_phy_wds/data_lane_gen[{lane}].u_ddr_phy_data_lane/u_ddr_phy_data_io/u_dqs'
        if any(name in text for name in (config, gate)):
            raise ValueError('DQS HOLD target already appears in the parent CST')
        if any(name not in netlist.cells for name in (config, gate, dqs)):
            raise ValueError('DQS HOLD observed boundary is missing')
        register, lut, hard = (netlist.cells[name] for name in (config, gate, dqs))
        if (register['kind'] != 'DFFCE' or register['parameters'].get('INIT') != "1'b0" or
                set(register['ports']) != {'D', 'Q', 'CLK', 'CE', 'CLEAR'} or
                netlist.pin(config, 'D') not in power or
                lut['kind'] != 'LUT2' or lut['parameters'].get('INIT') != "4'h4" or
                set(lut['ports']) != {'I0', 'I1', 'F'} or hard['kind'] != 'DQS' or
                hard['parameters'].get('DQS_MODE') != '"X4"'):
            raise ValueError('DQS HOLD observed FF/LUT/DQS type or configuration changed')
        if (netlist.pin(config, 'Q') != netlist.pin(gate, 'I0') or
                netlist.pin(gate, 'F') != netlist.pin(dqs, 'HOLD') or
                netlist.pin(config, 'CLEAR') != netlist.pin(dqs, 'RESET') or
                netlist.pin(config, 'CLK') != netlist.pin(dqs, 'PCLK') or
                netlist.pin(config, 'CLK') != netlist.pin(DDR_PHY + '/fclkdiv', 'CLKOUT')):
            raise ValueError('DQS HOLD observed data/reset/UI clock topology changed')
        constraints += [f'INS_LOC "{name}" {region};' for name in ((gate,) if lut_only else (config, gate))]
        lanes.append(dict(lane=lane, register=config, gate=gate, dqs=dqs, region=region,
                          clock=netlist.pin(config, 'CLK'), observed_FF_LUT_DQS=True,
                          register_constrained=not lut_only, gate_constrained=True))
    adapted = payload + ('\n' + '\n'.join(constraints) + '\n').encode()
    if parse_locations(adapted.decode()) != parse_locations(text):
        raise ValueError('DQS HOLD placement unexpectedly changed IO locations')
    return adapted, dict(lanes=lanes, constraints=constraints,
        mode='LUT_only' if lut_only else 'FF_and_LUT',
        unconstrained_config_registers=[lane['register'] for lane in lanes] if lut_only else [],
        before_sha256=digest(payload), after_sha256=digest(adapted),
        exact_appended_bytes_hex=adapted[len(payload):].hex(), parent_bytes_preserved=True,
        io_locations_unchanged=True, hard_locations_unchanged=True, sdc_unchanged=True,
        vendor_logic_unchanged=True, timing_exceptions_unchanged=True,
        topology_evidence_scope='hash_bound_previous_route_VO_of_same_encrypted_synthesis_VG',
        new_route_verified=False)


def derive_ddr_capture_region(source, output, user_code, parent_evidence,
                              expected_parent_evidence_sha256, acknowledge_electrical_risk=False,
                              *, dqs_hold_regions=False, dqs_hold_lut_only=False):
    """Prepare only a hash-locked physical child; never audit mutable current RTL."""
    if dqs_hold_regions and dqs_hold_lut_only:
        raise ValueError('DQS HOLD FF/LUT and LUT-only modes are mutually exclusive')
    dqs_regions = dqs_hold_regions or dqs_hold_lut_only
    source, output, parent_evidence = (Path(path).resolve() for path in (source, output, parent_evidence))
    script = implementation_script(user_code)
    if not acknowledge_electrical_risk:
        raise ValueError('explicit acknowledgement of unresolved electrical risk is required')
    if output.exists() or source in output.parents or output in source.parents:
        raise ValueError('a new independent physical output is required')
    if (not re.fullmatch(r'[0-9a-f]{64}', expected_parent_evidence_sha256 or '') or
            sha(parent_evidence) != expected_parent_evidence_sha256):
        raise ValueError('parent physical evidence identity changed')
    evidence = json.loads(parent_evidence.read_bytes())
    previous = json.loads((source / 'physical_inputs.json').read_bytes())
    if (previous['user_code'].lower() == ('0x' + user_code).lower() or
            previous['identity'] != evidence['physical_identity'] or
            previous != evidence['preparation']):
        raise ValueError('a new UserCode and matching original parent preparation evidence are required')
    if (previous.get('top_module') != TOP or previous.get('device') != DEVICE or
            previous.get('place_option') != 2 or previous.get('route_option') != 0 or
            previous.get('replicate_resources') is not False or
            previous.get('electrical_risk_explicitly_acknowledged') is not True or
            not isinstance(previous.get('electrical_blocked'), bool)):
        raise ValueError('parent physical options/electrical identity changed')
    verified_evidence = {}
    for relative, identity in evidence['evidence'].items():
        path = source / relative
        if (Path(relative).is_absolute() or '..' in Path(relative).parts or
                not path.is_file() or path.stat().st_size != identity['bytes'] or
                sha(path) != identity['sha256']):
            raise ValueError('parent physical evidence drifted: ' + relative)
        verified_evidence[relative] = identity['sha256']
    inputs = previous['input_sha256']
    required = {BASE + '.vg', 'physical.cst', 'physical.sdc', 'run.tcl',
                'parent_synthesis_audit.json', 'parent_integration_inputs.json'}
    if not required.issubset(inputs) or 'physical_inputs.json' not in verified_evidence:
        raise ValueError('parent physical input inventory changed')
    for name, expected in inputs.items():
        if Path(name).name != name or sha(source / name) != expected:
            raise ValueError('parent physical input drifted: ' + name)
        if name in verified_evidence and verified_evidence[name] != expected:
            raise ValueError('parent physical evidence/input hash disagreement: ' + name)
    if (source / 'run.tcl').read_text() != implementation_script(previous['user_code'].removeprefix('0x')):
        raise ValueError('parent physical script changed from automatic hold repair and fixed algorithms')
    audit = json.loads((source / 'parent_synthesis_audit.json').read_bytes())
    if (sha(source / 'parent_integration_inputs.json') != audit['integration_inputs_sha256'] or
            sha(source / (BASE + '.vg')) != audit['netlist_sha256']):
        raise ValueError('parent synthesis manifest/netlist binding changed')
    routed_name = f'impl/pnr/{BASE}.vo'
    if routed_name not in verified_evidence:
        raise ValueError('parent route VO needs original hash-bound physical evidence')
    arguments = ((source / 'physical.cst').read_bytes(), (source / 'physical.sdc').read_bytes(),
                 (source / routed_name).read_text())
    if dqs_regions:
        adapted, placement = ddr_dqs_hold_region_constraints(*arguments, lut_only=dqs_hold_lut_only)
    else:
        adapted, placement = ddr_capture_region_constraints(*arguments)
    placement['observed_route_vo_sha256'] = verified_evidence[routed_name]
    output.mkdir(parents=True)
    for name, expected in inputs.items():
        if name != 'run.tcl':
            checked_copy(source / name, output / name, expected)
    # A child may itself carry an older parent's snapshot. Keep every byte of
    # that closure instead of overwriting it with the immediate parent's file.
    snapshot_prefix = ('parent_' + previous['user_code'].removeprefix('0x')
                       if 'parent_physical_inputs.json' in inputs else 'parent_physical')
    parent_manifest_copy = snapshot_prefix + '_inputs.json'
    parent_evidence_copy = snapshot_prefix + '_evidence.json'
    if any(name in inputs for name in (parent_manifest_copy, parent_evidence_copy)):
        raise ValueError('physical ancestor snapshot name collides with an existing input')
    checked_copy(source / 'physical_inputs.json', output / parent_manifest_copy,
                 verified_evidence['physical_inputs.json'])
    checked_copy(parent_evidence, output / parent_evidence_copy, expected_parent_evidence_sha256)
    (output / 'physical.cst').write_bytes(adapted)
    (output / 'run.tcl').write_text(script)
    for name, expected in inputs.items():
        copied_expected = (placement['after_sha256'] if name == 'physical.cst' else
                           digest(script.encode()) if name == 'run.tcl' else expected)
        if sha(source / name) != expected or sha(output / name) != copied_expected:
            raise ValueError('physical input changed during floorplan preparation: ' + name)
    if (sha(parent_evidence) != expected_parent_evidence_sha256 or
            sha(source / 'physical_inputs.json') != verified_evidence['physical_inputs.json'] or
            sha(source / routed_name) != verified_evidence[routed_name]):
        raise ValueError('parent evidence changed during floorplan preparation')
    result = dict(previous)
    result.update(
        identity='custom138k-native-physical-' + user_code.upper(), user_code='0x' + user_code.upper(),
        prepared_at=datetime.now().astimezone().isoformat(),
        validation_stage='offline_physical_variant_prepared_no_EDA',
        source_policy=('hash_locked_previous_physical_VG_and_SDC_with_only_explicit_DDR_DQS_HOLD_LUT_only_regions_CST_append'
                       if dqs_hold_lut_only else
                       'hash_locked_previous_physical_VG_and_SDC_with_only_explicit_DDR_DQS_HOLD_regions_CST_append'
                       if dqs_hold_regions else
                       'hash_locked_previous_physical_VG_and_SDC_with_only_explicit_DDR_capture_region_CST_append'),
        parent_physical_identity=previous['identity'], parent_physical_directory=str(source),
        parent_physical_manifest_sha256=verified_evidence['physical_inputs.json'],
        parent_physical_evidence_sha256=expected_parent_evidence_sha256,
        parent_physical_manifest_copy=parent_manifest_copy,
        parent_physical_evidence_copy=parent_evidence_copy,
        parent_physical_evidence_verified_sha256=verified_evidence,
        synthesis_parent_identity=audit['identity'],
        synthesis_source_identity={key: evidence[key] for key in ('source_commit', 'profile_revision', 'profile_identity')},
        current_working_tree_RTL_used=False, new_synthesis_run=False, EDA_started=False,
        preparer_sha256=sha(Path(__file__)), parent_input_sha256=dict(inputs),
        automatic_hold_repair=True,
        full_timing_gates_required=True,
        parent_failed_physical_status=evidence['status'],
        input_sha256={path.name: sha(path) for path in output.iterdir() if path.is_file()},
        physical_gates_passed=False, timing_closed=False, deployment_allowed=False, release_ready=False,
        hardware_tested=False, board_programming_authorized=False, bitstream_sha256=None,
        sram_programmed=False, flash_programmed=False)
    result['ddr_dqs_hold_regions_adaptation' if dqs_regions else 'ddr_capture_region_adaptation'] = placement
    (output / 'physical_inputs.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


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
    parser.add_argument('--ddr-capture-region-parent-evidence', '--ddr-floorplan-parent-evidence', type=Path,
                        help='Derive from the hash-bound original physical evidence, keeping the previous VG and SDC')
    dqs_mode = parser.add_mutually_exclusive_group()
    dqs_mode.add_argument('--ddr-dqs-hold-regions', action='store_true',
                        help='Append only the reviewed four-lane FF/LUT placement regions to a capture-region parent')
    dqs_mode.add_argument('--ddr-dqs-hold-lut-only', action='store_true',
                          help='Constrain only the four reviewed HOLD LUTs; leave config registers free')
    parser.add_argument('--expected-parent-evidence-sha256',
                        help='Required explicit identity when deriving the DDR capture-region experiment')
    args = parser.parse_args()
    if args.ddr_capture_region_parent_evidence:
        if args.ulpi_bypass_lvcmos33:
            parser.error('the derived parent already fixes ULPI; a second adaptation is not allowed')
        result = derive_ddr_capture_region(args.source, args.output, args.user_code,
                                          args.ddr_capture_region_parent_evidence,
                                          args.expected_parent_evidence_sha256,
                                          args.acknowledge_electrical_risk,
                                          dqs_hold_regions=args.ddr_dqs_hold_regions,
                                          dqs_hold_lut_only=args.ddr_dqs_hold_lut_only)
    else:
        if args.ddr_dqs_hold_regions or args.ddr_dqs_hold_lut_only:
            parser.error('DQS HOLD placement modes require an explicit floorplan parent evidence')
        if args.expected_parent_evidence_sha256:
            parser.error('--expected-parent-evidence-sha256 requires the explicit DDR derivation')
        result = prepare(args.source, args.output, args.user_code, args.acknowledge_electrical_risk,
                         args.ulpi_bypass_lvcmos33)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
