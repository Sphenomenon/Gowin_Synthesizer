#!/usr/bin/env python3
"""Read-only runtime clock/DCS source-netlist audit; never STA acceptance."""

from collections import defaultdict
from pathlib import Path
import argparse
import hashlib
import json
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.workstation_custom_clocks import audit_clocks, clock_bundle
from tools.workstation_synthesis_netlist import SynthesisNetlist


TOP = 'workstation_custom_138k_top'
SELECTOR = 'u_managed/runtime/clocks/selector'
SERIALIZER = 'u_managed/runtime/serializer/'
VG_RELATIVE = 'impl/gwsynthesis/custom_138k_integration.vg'
PLL_PATHS = {
    'u_audio_clock/g_hardware.u_pll/PLL_inst', 'u_usb_pll/PLL_inst',
    'u_lcd/u_pll/PLL_inst', 'u_memory/u_pll/u_pll_0/PLL_inst',
    'u_video/u_clock/g_hardware.u_pll/u_reference/PLL_inst',
    'u_video/u_clock/g_hardware.u_pll/u_tmds/PLL_inst', 'u_cpu_pll/PLL_inst',
}
DIVIDER_PATH = 'u_video/u_clock/g_hardware.u_pll/u_pixel_div'
RUNTIME_CLOCK_SDC = (
    'create_clock -name dac_ref16m9344 -period 59.051398337 [get_ports {clk_16m9344}]',
    'create_generated_clock -name selected48 -source [get_ports {clk_12m288}] '
    '-master_clock dac_ref12m288 -divide_by 1 [get_pins {' + SELECTOR + '/CLKOUT}]',
    'create_generated_clock -name selected44 -source [get_ports {clk_16m9344}] '
    '-master_clock dac_ref16m9344 -divide_by 1 -add [get_pins {' + SELECTOR + '/CLKOUT}]',
)
MODE_EXCLUSIONS = (
    'set_false_path -from [get_clocks {selected48}] -to [get_clocks {selected44}]',
    'set_false_path -from [get_clocks {selected44}] -to [get_clocks {selected48}]',
)
AUDIT_SOURCES = (
    'tools/workstation_runtime_clock_audit.py', 'tools/workstation_custom_clocks.py',
    'tools/workstation_synthesis_netlist.py', 'tools/stage_usb_firmware.py',
    'tools/workstation_baselines.py', 'tools/audit_clk50_timing.py',
    'boards/custom_138k/clocks.json', 'sim/test_workstation_runtime_clocks.py',
    'tools/workstation_profile.py', 'tools/workstation_board_peripherals.py',
    'tools/workstation_ae350_rtc.py', 'tools/workstation_ae350_clock_placement.py',
    'rtl/clock/workstation_ae350_rtc.sv',
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    return digest(Path(path).read_bytes())


def require(condition, message):
    if not condition:
        raise ValueError('runtime clock audit: ' + message)


def prepared_local_panel_enabled(stage):
    """Select the registered clock policy without changing historical inputs."""
    profile_path = Path(stage).parents[1] / 'workstation_profile.json'
    if not profile_path.is_file():
        return True  # Legacy preparations predate named workstation profiles.
    from tools.workstation_profile import specification
    prepared = json.loads(profile_path.read_text())
    require(isinstance(prepared, dict) and isinstance(prepared.get('profile'), str),
            'prepared profile identity is missing or malformed')
    spec = specification(prepared['profile'])  # Unknown names must fail closed.
    profile_sha = prepared.get('profile_sha256')
    require(prepared.get('configuration') == spec['configuration'] and
            prepared.get('profile_source') == spec['config'] and
            isinstance(profile_sha, str) and re.fullmatch(r'[0-9a-f]{64}', profile_sha) is not None,
            'registered profile configuration or source identity changed')
    panel_enabled = spec.get('local_panel_enabled', True)
    require(type(panel_enabled) is bool, 'registered local-panel selection is malformed')
    return panel_enabled


def audit_runtime_clocks(root, stage, netlist_text):
    """Check static clock declarations/connectivity, leaving physical gates false.

    The selected base-clock declaration prefix includes the conservative RTC bound.
    Passing the actual remaining SDC as extra_sdc only establishes prefix
    identity; it does not audit all exceptions or Tcl object resolution.
    """
    root, stage = Path(root), Path(stage)
    local_panel_enabled = prepared_local_panel_enabled(stage)
    sdc = (stage / 'constraints/custom_138k.sdc').read_text()
    bundle = clock_bundle(root, local_panel_enabled=local_panel_enabled)
    require(sdc.startswith(bundle['sdc']), 'selected base-clock SDC prefix changed')
    extra = sdc[len(bundle['sdc']):]
    extra_lines = extra.splitlines()
    declarations = [line for line in extra_lines if line.startswith('create_')]
    require(declarations == list(RUNTIME_CLOCK_SDC), 'runtime clock declarations changed')
    require(all(extra_lines.count(line) == 1 for line in MODE_EXCLUSIONS),
            'selected-mode exclusion declarations changed')
    base = audit_clocks(root, stage, netlist_text, extra_sdc=extra, local_panel_enabled=local_panel_enabled)
    from tools.workstation_board_peripherals import audit_local_panel
    panel = audit_local_panel(netlist_text, local_panel_enabled=local_panel_enabled)
    n = SynthesisNetlist(netlist_text, TOP)
    require(all(n.directions[TOP].get(port) == 'input' for port in
                ('clk_50m', 'usb2_ulpi_clk', 'clk_12m288', 'clk_16m9344')),
            'primary clock top input inventory changed')
    primitives = {kind: sorted(p for p, c in n.cells.items() if c['kind'] == kind)
                  for kind in ('PLL', 'CLKDIV', 'DCS')}
    expected_plls = PLL_PATHS if local_panel_enabled else PLL_PATHS - {'u_lcd/u_pll/PLL_inst'}
    require(set(primitives['PLL']) == expected_plls, 'visible selected PLL inventory changed')
    require(primitives['CLKDIV'] == [DIVIDER_PATH], 'visible CLKDIV inventory changed')
    require(primitives['DCS'] == [SELECTOR], 'single DCS inventory changed')
    dcs = n.cells[SELECTOR]
    require(dcs['parameters'].get('DCS_MODE') == '"FALLING"', 'DCS mode changed')
    require(n.pin(SELECTOR, 'CLKIN0') == 'clk_12m288' and
            n.pin(SELECTOR, 'CLKIN1') == 'clk_16m9344', 'DCS reference wiring changed')
    zero_nets = {"1'b0"} | {n.pin(p, 'G') for p, c in n.cells.items() if c['kind'] == 'GND'}
    one_nets = {"1'b1"} | {n.pin(p, 'V') for p, c in n.cells.items() if c['kind'] == 'VCC'}
    require(all(n.pin(SELECTOR, pin) in zero_nets for pin in ('CLKIN2', 'CLKIN3', 'SELFORCE')),
            'DCS unused inputs or SELFORCE are not constant zero')
    scope = n.scopes[SELECTOR]
    select_binding = dcs['ports']['CLKSEL']
    require(select_binding.startswith('{') and select_binding.endswith('}'), 'DCS select binding changed')
    select_bits = [n.canonical(scope, bit) for bit in n.concatenation_bits(scope, select_binding)]
    require(len(select_bits) == 4 and all(bit in zero_nets for bit in select_bits[2:]),
            'DCS select upper bits are not zero')
    registers = {p: c for p, c in n.cells.items() if c['kind'].startswith('DFF')}
    q_drivers = defaultdict(list)
    for p in registers:
        q_drivers[n.pin(p, 'Q')].append(p)
    select_drivers = []
    for bit, net in enumerate(select_bits[:2]):
        drivers = q_drivers[net]
        require(len(drivers) == 1, 'DCS select bit is not a direct unique register Q')
        p = drivers[0]
        require(re.fullmatch(r'u_managed/runtime/clocks/transaction/clock_select_o_' +
                             str(bit) + r'_s\d+', p) is not None and n.pin(p, 'CLK') == 'clk_50m',
                'DCS select register owner or 50MHz clock changed')
        select_drivers.append(dict(bit=bit, register=p, q_net=net, clock=n.pin(p, 'CLK')))
    selected = n.pin(SELECTOR, 'CLKOUT')
    serializer_registers = sorted(p for p in registers if p.startswith(SERIALIZER))
    require(serializer_registers and all(n.pin(p, 'CLK') == selected for p in serializer_registers),
            'serializer consumer clock differs from selected MCLK')
    monitor_groups = {}
    for name, source in (('reference_48_monitor', 'clk_12m288'),
                         ('reference_44_monitor', 'clk_16m9344'), ('selected_monitor', selected)):
        prefix = 'u_managed/runtime/clocks/' + name + '/'
        source_regs = sorted(p for p in registers if p.startswith((prefix + 'source_', prefix + 'startup_source_')))
        control_regs = sorted(p for p in registers if p.startswith(prefix) and p not in source_regs)
        pre = {}
        release = [p for p in source_regs if re.fullmatch(re.escape(prefix) + r'source_reset_n_s\d+', p)]
        for p in source_regs:
            match = re.fullmatch(re.escape(prefix) + r'source_reset_pre_(\d+)_s\d+', p)
            if match:
                require(int(match[1]) not in pre, 'duplicate monitor release pre stage: ' + name)
                pre[int(match[1])] = p
        negative_release = []
        release_evidence = dict(policy='legacy_rising_edge_release')
        if 2 in pre:
            # Gowin maps the maintained negedge release to a positive-edge
            # FF with one explicit INV on its clock. Accept only that one
            # release FF; all counters, Gray and startup FFs remain positive.
            require(set(pre) == {0, 1, 2} and len(release) == 1,
                    'opposite-edge monitor release inventory changed: ' + name)
            p = release[0]
            inverted = n.pin(p, 'CLK')
            inverters = [q for q, c in n.cells.items() if c['kind'] == 'INV' and
                         n.pin(q, 'O') == inverted]
            require(len(inverters) == 1 and n.pin(inverters[0], 'I') == source and inverted != source,
                    'opposite-edge monitor release clock changed: ' + name)
            require(registers[p]['kind'] in ('DFFCE', 'DFFRE') and
                    n.pin(p, 'CE') in one_nets and n.pin(p, 'D') == n.pin(pre[2], 'Q') and
                    all(n.pin(pre[i], 'CE') in one_nets for i in range(3)) and
                    all(n.pin(pre[i], 'D') == n.pin(pre[i-1], 'Q') for i in (1, 2)),
                    'opposite-edge monitor release data chain changed: ' + name)
            negative_release = release
            release_evidence = dict(policy='three_positive_pre_stages_then_single_inverted_clock_release',
                register=p, clock_inverter=inverters[0], inverted_clock=inverted,
                pre_registers=[pre[i] for i in range(3)], no_clock_exception_added=True)
        require(source_regs and control_regs and
                all(n.pin(p, 'CLK') == source for p in source_regs if p not in negative_release) and
                all(n.pin(p, 'CLK') == 'clk_50m' for p in control_regs),
                'monitor source/control clock changed: ' + name)
        monitor_groups[name] = dict(source_clock=source, source_registers=source_regs,
                                   control_clock='clk_50m', control_registers=control_regs,
                                   reset_release=release_evidence)
    outputs = {}
    for port, label in (('dac_mclk', None), ('hp_bck', 'bck_o'),
                        ('hp_ws', 'lrck_o'), ('hp_din', 'data_o')):
        buffers = [p for p, c in n.cells.items() if c['kind'] == 'OBUF' and
                   n.pin(p, 'O') == port]
        require(len(buffers) == 1, 'audio output OBUF is not unique: ' + port)
        p = buffers[0]
        net = n.pin(p, 'I')
        if label is None:
            require(net == selected, 'DAC MCLK is not directly driven by DCS output')
            outputs[port] = dict(buffer=p, input_net=net, source=SELECTOR + '/CLKOUT')
        else:
            drivers = q_drivers[net]
            require(len(drivers) == 1 and re.fullmatch(re.escape(SERIALIZER + label) + r'_s\d+',
                    drivers[0]) is not None and n.pin(drivers[0], 'CLK') == selected,
                    'I2S output is not a direct selected-clock serializer register: ' + port)
            outputs[port] = dict(buffer=p, input_net=net, register=drivers[0], clock=selected)
    return dict(schema=1, scope='static_source_netlist_clock_and_DCS_topology',
        base_clock_audit=base,
        local_panel_enabled=local_panel_enabled, local_panel=panel, visible_clock_primitives=primitives,
        declaration_scope=dict(base_clock_prefix_count=len(bundle['plan']['primary']) + len(bundle['plan']['generated']) + len(bundle['plan']['fabric_generated']), runtime_reference_count=1,
            selected_mode_count=2, clock_declarations_checked=len(bundle['plan']['primary']) + len(bundle['plan']['generated']) + len(bundle['plan']['fabric_generated']) + 3, sdc_sha256=digest(sdc.encode()),
            suffix_sha256=digest(extra.encode()), selected_mode_exclusions=list(MODE_EXCLUSIONS),
            remaining_suffix_lines_not_audited=len(extra_lines) - 5,
            gowin_sta_command_resolution_verified=False,
            suffix_exceptions_or_object_resolution_verified=False),
        dcs=dict(path=SELECTOR, mode='FALLING', reference_inputs=dict(CLKIN0='clk_12m288',
            CLKIN1='clk_16m9344'), zero_inputs=['CLKIN2', 'CLKIN3', 'SELFORCE'],
            select_bits_lsb_first=select_bits, select_registers=select_drivers, output_net=selected,
            modes=dict(selected48=dict(frequency_hz=12288000, master='dac_ref12m288'),
                       selected44=dict(frequency_hz=16934400, master='dac_ref16m9344'))),
        serializer_registers=serializer_registers, monitor_groups=monitor_groups, audio_outputs=outputs,
        runtime_audio_topology_verified=True, whole_source_clock_topology_verified=False,
        opaque_ddr_clock_verified=False, physical_clock_tree_verified=False, sta_verified=False,
        routed_timing_verified=False, constraints_complete=False, dynamic_dcs_behavior_verified=False,
        hardware_tested=False, release_ready=False, deployment_allowed=False)


def verify_synthesis_identity(stage, evidence):
    """Independently hash every input recorded by the completed synthesis run."""
    stage, evidence = Path(stage).resolve(), Path(evidence).resolve()
    process = json.loads(evidence.read_text())
    require(process.get('completed') is True and process.get('exit_code') == 0 and
            process.get('inputs_unchanged') is True and process.get('stage') == 'synthesis_only',
            'synthesis completion/source seal evidence is not valid')
    require(Path(process.get('cwd', '')).resolve() == stage, 'synthesis project identity differs')
    inputs = process.get('input_sha256', {})
    require(bool(inputs), 'staged input identity is empty')
    profile_path = stage.parents[1] / 'workstation_profile.json'
    profile = json.loads(profile_path.read_text())
    require(bool(profile.get('candidate_identity')) and
            process.get('candidate_identity') == profile['candidate_identity'],
            'synthesis candidate identity differs from prepared profile')
    require(inputs == profile.get('staged_input_sha256'),
            'staged input closure differs from prepared profile')
    for relative, expected in inputs.items():
        p = Path(relative)
        require(not p.is_absolute() and '..' not in p.parts and
                (stage / p).resolve().is_relative_to(stage), 'invalid staged input path')
        require(re.fullmatch(r'[0-9a-f]{64}', expected) is not None and
                file_sha(stage / p) == expected, 'staged input changed: ' + relative)
    expected_vg = process.get('output_sha256', {}).get(VG_RELATIVE)
    require(expected_vg is not None and file_sha(stage / VG_RELATIVE) == expected_vg,
            'synthesis VG output identity changed')
    return dict(process_evidence=str(evidence), process_sha256=file_sha(evidence),
                prepared_profile=str(profile_path), prepared_profile_sha256=file_sha(profile_path),
                prepared_profile_input_closure_equal=True,
                candidate_identity=process.get('candidate_identity'), stage=str(stage),
                full_staged_input_count=len(inputs), full_staged_input_sha256=inputs,
                vg=str(stage / VG_RELATIVE), vg_sha256=expected_vg,
                validation_stage='synthesis_only', inputs_independently_hashed=True)


def run_audit(root, stage, evidence):
    root, stage = Path(root), Path(stage)
    before = verify_synthesis_identity(stage, evidence)
    audit_sources = {relative: file_sha(root / relative) for relative in AUDIT_SOURCES}
    result = audit_runtime_clocks(root, stage, (stage / VG_RELATIVE).read_text())
    after = verify_synthesis_identity(stage, evidence)
    require(before == after and audit_sources == {p: file_sha(root / p) for p in AUDIT_SOURCES},
            'inputs or audit sources changed during audit')
    identity = digest(json.dumps(dict(synthesis=before, audit_sources=audit_sources),
                                 sort_keys=True, separators=(',', ':')).encode())
    result.update(identity='runtime-clock-source-audit-v1-' + identity[:16],
                  source_set_sha256=identity, synthesis=before, audit_source_sha256=audit_sources,
                  source_seal_before_and_after=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--synthesis-evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run_audit(ROOT, args.project, args.synthesis_evidence)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(identity=result['identity'], vg_sha256=result['synthesis']['vg_sha256'],
                         staged_inputs=result['synthesis']['full_staged_input_count'],
                         runtime_audio_topology_verified=True, sta_verified=False,
                         dynamic_dcs_behavior_verified=False, output=str(args.output)), indent=2))


if __name__ == '__main__':
    main()
