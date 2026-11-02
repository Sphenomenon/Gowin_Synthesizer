"""Explicit paired LCD/local-clock policy over actual synthesis primitives.

This certifies static source/clock/pad structure only. No inter-board CDC, IO
voltage, timing exception, PLL physical budget or hardware gate is waived.
"""
from pathlib import Path
import hashlib
import json
import re
import xml.etree.ElementTree as ET

POLICY = 'task3_paired_actual_clock_pad_topology_v1'
TOP = 'workstation_custom_138k_top'
PAD_WIDTHS = dict(lcd_r=5, lcd_g=6, lcd_b=5, lcd_pclk=1, lcd_hsync=1,
    lcd_vsync=1, lcd_de=1, lcd_bl=1, lcd_ctp_rst=1, lcd_ctp_sda=1,
    lcd_ctp_scl=1, lcd_ctp_int=1)
DRIVEN = {
    'M': {*(f'lcd_r[{i}]' for i in range(5)), 'lcd_b[0]', 'lcd_b[1]'},
    'W': {*(f'lcd_g[{i}]' for i in range(6)), 'lcd_b[2]'},
}
RECEIVED = {'M': DRIVEN['W'], 'W': DRIVEN['M']}


def require(ok, message):
    if not ok:
        raise ValueError('paired clock audit: ' + message)


def paired_clock_selection(stage, role):
    require(role in ('M', 'W'), 'explicit role must be M or W')
    stage = Path(stage)
    profile = json.loads((stage.parents[1] / 'workstation_profile.json').read_text())
    from tools.workstation_profile import prepared_specification, PROFILE_REGISTRY
    spec = prepared_specification(profile)
    require(spec.get('paired_board') is True and spec.get('paired_role') == role and
            spec.get('local_panel_enabled') is False and
            spec.get('worker_media', False) is (role == 'W') and
            spec.get('tf_direct_enabled', False) is (role == 'M'),
            'registered paired role/clock configuration changed')
    enabled = [row.get('path') for row in ET.parse(stage / 'Prj1.gprj').find('FileList')
               if row.get('enable') == '1']
    providers = {row['provider'] for row in PROFILE_REGISTRY.values()}
    require([path for path in enabled if path in providers] == [spec['provider']],
            'paired provider selection must be unique')
    from tools import workstation_task3_paired_board as common
    common.verify_selection(stage, stage, profile.get('task3_paired', {}), role)
    if role == 'M':
        from tools import workstation_task3_m_paired_profile as role_policy
    else:
        from tools import workstation_task3_w_paired_profile as role_policy
    selected_top = (stage / common.TOP).read_text()
    role_top = common.inverse_top(stage, selected_top, role)
    parent = role_policy.inverse_top(stage, role_top)
    require(role_policy.digest(parent) == role_policy.PARENT_TOP_SHA256 and
            role_policy.apply_top(stage, parent) == role_top,
            'paired exact common/role source inverse changed')
    return dict(policy=POLICY, paired_role=role, hdmi_enabled=role == 'M',
        local_panel_enabled=False, provider=spec['provider'],
        candidate_identity=profile['candidate_identity'], actual_role_source_verified=True,
        selected_top_sha256=hashlib.sha256(selected_top.encode()).hexdigest(),
        parent_top_sha256=role_policy.PARENT_TOP_SHA256,
        clock_authority='M' if role == 'M' else 'remote_M; W_local_output_muted',
        whole_source_CDC_accepted=False, physical_clock_tree_verified=False)


def audit_paired_lcd_clock_boundary(stage, n, role, base):
    selection = paired_clock_selection(stage, role)
    require(not any(p == 'u_lcd' or p.startswith('u_lcd/') for p in (*n.frames, *n.cells)),
            'paired role retained the original local LCD/PLL')
    pads = {}
    for port, width in PAD_WIDTHS.items():
        require(n.directions[TOP].get(port) == 'inout' and
                n.ranges[TOP].get(port) == ((width - 1, 0) if width > 1 else None),
                'LCD inout width/direction changed: ' + port)
        pads.update({f'{port}[{i}]' if width > 1 else port: [] for i in range(width)})
    ground = {"1'b0"} | {n.pin(p, 'G') for p, c in n.cells.items() if c['kind'] == 'GND'}
    high = {"1'b1"} | {n.pin(p, 'V') for p, c in n.cells.items() if c['kind'] == 'VCC'}
    for path, cell in n.cells.items():
        if cell['kind'] in n.modules:
            continue
        for pin in ('O', 'IO'):
            if pin in cell['ports'] and n.pin(path, pin) in pads:
                pads[n.pin(path, pin)].append((path, cell['kind'], pin))
    received_nets, enables, evidence = set(), set(), {}
    reserved = set(pads) - DRIVEN[role] - RECEIVED[role]
    for pad, buffers in pads.items():
        require(len(buffers) == 1, 'LCD physical buffer missing/duplicate: ' + pad)
        path, kind, pin = buffers[0]
        require(n.scopes[path] == '', 'LCD pad primitive moved behind an unreviewed wrapper: ' + pad)
        if pad in RECEIVED[role]:
            require(kind == 'IOBUF' and pin == 'IO' and n.pin(path, 'I') in ground and
                    n.pin(path, 'OEN') in high, 'LCD receive pad can drive or changed primitive: ' + pad)
            received_nets.add(n.pin(path, 'O'))
            mode = 'input_only'
        else:
            require(kind == 'TBUF' and pin == 'O', 'LCD transmit/reserved primitive changed: ' + pad)
            if pad in reserved:
                require(n.pin(path, 'I') in ground and n.pin(path, 'OEN') in high,
                        'reserved LCD pad is no longer permanently high impedance: ' + pad)
                mode = 'reserved_high_impedance'
            else:
                require(n.pin(path, 'OEN') not in high | ground,
                        'LCD transmit enable is constant: ' + pad)
                require(n.pin(path, 'I') not in high | ground,
                        'LCD transmit payload was swept: ' + pad)
                enables.add(n.pin(path, 'OEN'))
                mode = 'runtime_gated_transmit'
        evidence[pad] = dict(primitive=path, kind=kind, mode=mode)
    require(len(enables) == 1, 'LCD transmit pads do not share the single role enable')
    local50 = base['clocks']['clk_50m']['net']
    cpu50 = base['clocks']['cpu_ram50']['net']
    register_clocks = {}
    clock_pins = re.compile(r'^(?:CLK|CLKIN[0-3]?|HCLKIN|FCLK|PCLK)$')
    for path, cell in n.cells.items():
        if cell['kind'] in n.modules:
            continue
        for pin in cell['ports']:
            if clock_pins.fullmatch(pin):
                require(n.pin(path, pin) not in received_nets | set(pads),
                        'LCD wire used as a clock: ' + path + '/' + pin)
        if path.startswith('u_task3_pair_link/') and cell['kind'].startswith('DFF'):
            clock = n.pin(path, 'CLK')
            # Only the existing CPU-side APB CDC owns the independent CPU50
            # clock. Transport, pins, config application and peer sync use clk50.
            allowed = {local50, cpu50} if path.startswith('u_task3_pair_link/config_cdc/') else {local50}
            require(clock in allowed, 'paired link register has an unreviewed clock: ' + path)
            register_clocks.setdefault(clock, []).append(path)
    require(set(register_clocks) == {local50, cpu50}, 'paired APB/local clock inventory changed')
    return dict(**selection, local_panel_hierarchy_present=False, programmable_pads=len(pads),
        driven_pads=sorted(DRIVEN[role]), received_pads=sorted(RECEIVED[role]),
        reserved_high_impedance_pads=sorted(reserved), pad_primitives=evidence,
        single_transmit_enable=next(iter(enables)),
        register_clocks={clock: dict(registers=len(paths), inventory_sha256=hashlib.sha256(
            '\n'.join(sorted(paths)).encode()).hexdigest()) for clock, paths in register_clocks.items()},
        LCD_wire_used_as_clock=False, runtime_enable_boolean_function_verified=False,
        interboard_CDC_verified=False, physical_electrical_acceptance=False)


def audit_paired_worker_monitor_release(n, *, stage, name, source_clock, root=None):
    """Prove W's six qualified release state updates over all 256 assignments.

    The complete 35-bit actual root startup proof is required first. The
    qualified release proof then covers every state/input assignment and never
    waives physical reset recovery/removal, CDC or clock health gates.
    """
    from tools.workstation_runtime_pcm_cdc import BooleanDiagram, Graph
    from tools.workstation_task3_clock_release_audit import SOURCE, SOURCE_SHA256
    stage = Path(stage)
    paired_clock_selection(stage, 'W')
    require(hashlib.sha256((stage / SOURCE).read_bytes()).hexdigest() == SOURCE_SHA256,
            'qualified worker monitor maintained source changed')
    g = Graph(n)
    scope = 'u_managed/runtime/clocks/' + name
    expected_kind = dict(reference_48_monitor='workstation_audio_clock_monitor',
        reference_44_monitor='workstation_audio_clock_monitor_0',
        selected_monitor='workstation_audio_clock_monitor_1')
    require(name in expected_kind and n.frames.get(scope, {}).get('kind') == expected_kind[name],
            'worker monitor owner changed')
    startup = g.group(scope, 'startup_source', 2)
    pre = g.group(scope, 'source_reset_pre', 3)
    release = g.register(scope, 'source_reset_n')
    registers = startup + pre + [release]
    from tools.workstation_task3_root_reset_audit import audit_root_startup
    root = audit_root_startup(n, stage=stage) if root is None else root
    require(root.get('all_state_assignments_proven') is True and root.get('actual_state_bits') == 35,
            'worker monitor requires the actual complete 35-bit root proof')
    root_started = g.register('u_reset', 'started')
    root_q = n.pin(root_started, 'Q')
    require(root_q == root['root_q'], 'worker monitor root proof is bound to another net')
    require(n.pin('u_reset', 'reset_n') == root_q and root_q not in g.high | g.low,
            'worker common assertion is disconnected from the actual root output')
    control = n.canonical('u_managed/runtime/clocks', 'control_reset_n')
    leaves = [root_q, control, *(n.pin(path, 'Q') for path in registers)]
    require(len(set(leaves)) == 8, 'worker release state/input alias changed')
    bd = BooleanDiagram(leaves)
    inv_clock = n.pin(release, 'CLK')
    inverters = [path for path, cell in n.cells.items() if cell['kind'] == 'INV' and
                 n.pin(path, 'O') == inv_clock and n.pin(path, 'I') == source_clock]
    require(inv_clock != source_clock and len(inverters) == 1,
            'worker opposite-edge release clock changed')
    live = bd.inputs[root_q]
    qualified = bd.both(live, bd.inputs[n.pin(startup[1], 'Q')])
    expected = [bd.both(live, bd.inputs[control]),
        bd.both(live, bd.inputs[n.pin(startup[0], 'Q')]), qualified,
        bd.both(qualified, bd.inputs[n.pin(pre[0], 'Q')]),
        bd.both(qualified, bd.inputs[n.pin(pre[1], 'Q')]),
        bd.both(live, bd.inputs[n.pin(pre[2], 'Q')])]
    rows = []
    for path, wanted in zip(registers, expected):
        cell = n.cells[path]
        require(cell['kind'] == 'DFFCE' and set(cell['ports']) == {'Q', 'D', 'CLK', 'CE', 'CLEAR'} and
                cell['parameters'].get('INIT', "1'b0") == "1'b0",
                'worker release primitive/zero INIT changed: ' + path)
        require(n.pin(path, 'CLK') == (inv_clock if path == release else source_clock) and
                n.pin(path, 'CE') in g.high, 'worker release clock/constant CE changed: ' + path)
        require(g.support(n.pin(path, 'CLEAR')) == {root_q} and
                bd.net(g, n.pin(path, 'CLEAR')) == bd.invert(live),
                'worker async assertion differs from actual root: ' + path)
        actual = bd.choose(bd.net(g, n.pin(path, 'CLEAR')), 0,
            bd.choose(bd.net(g, n.pin(path, 'CE')), bd.net(g, n.pin(path, 'D')),
                      bd.inputs[n.pin(path, 'Q')]))
        require(actual == wanted, 'worker startup-qualified next-Q changed: ' + path)
        rows.append(dict(register=path, exact_reset_inclusive_next_q=True))
    return dict(policy='task3_paired_W_actual_qualified_monitor_release_v1', monitor=name,
        source_clock=source_clock, root_started=root_started, root_q=root_q,
        root_output_connectivity_verified=True, full_root_state_machine_proven=True, root_proof=root,
        arbitrary_state_and_input_assignments=256, exact_next_q=rows,
        opposite_edge_release_register=release, clock_inverter=inverters[0],
        source_sha256={SOURCE: SOURCE_SHA256}, exception_added=False,
        reset_recovery_removal_accepted=False, whole_source_CDC_accepted=False,
        hardware_tested=False)
