"""Exact DIRECT clock-monitor startup-qualified release next-Q proof.

This accepts the maintained startup qualification only for the explicit real
root candidate. It does not waive reset timing or prove clock health/STA.
"""
import hashlib
from pathlib import Path

from tools.workstation_runtime_pcm_cdc import BooleanDiagram, Graph
from tools.workstation_task3_root_reset_audit import audit_root_startup

SOURCE = 'rtl/audio/workstation_audio_clock_monitor.sv'
SOURCE_SHA256 = 'be488070d2fc9da40951bbcd785d75439415dc998c854ead0cc7c1f9a4d4c6d5'


def require(condition, message):
    if not condition:
        raise ValueError('task3 clock release audit: ' + message)


def audit_clock_monitor_release(n, *, stage, name, source_clock, root=None):
    stage = Path(stage)
    require(hashlib.sha256((stage / SOURCE).read_bytes()).hexdigest() == SOURCE_SHA256,
            'maintained monitor source changed')
    root = audit_root_startup(n, stage=stage) if root is None else root
    require(root.get('all_state_assignments_proven') is True and root.get('actual_state_bits') == 35,
            'actual real-root proof required')
    g = Graph(n)
    scope = 'u_managed/runtime/clocks/' + name
    kinds = dict(reference_48_monitor='workstation_audio_clock_monitor',
                 reference_44_monitor='workstation_audio_clock_monitor_0',
                 selected_monitor='workstation_audio_clock_monitor_1')
    require(name in kinds and n.frames.get(scope, {}).get('kind') == kinds[name],
            'actual monitor owner changed')
    startup = g.group(scope, 'startup_source', 2)
    pre = g.group(scope, 'source_reset_pre', 3)
    release = g.register(scope, 'source_reset_n')
    registers = startup + pre + [release]
    root_q = root['root_q']
    control = n.canonical('u_managed/runtime/clocks', 'control_reset_n')
    leaves = [root_q, control, *(n.pin(p, 'Q') for p in registers)]
    require(len(leaves) == len(set(leaves)) == 8, 'release state/input alias')
    bd = BooleanDiagram(leaves)
    inv_clock = n.pin(release, 'CLK')
    inverters = [p for p, c in n.cells.items() if c['kind'] == 'INV' and
                 n.pin(p, 'O') == inv_clock and n.pin(p, 'I') == source_clock]
    require(inv_clock != source_clock and len(inverters) == 1,
            'single opposite-edge release clock changed')
    live = bd.inputs[root_q]
    qualified = bd.both(live, bd.inputs[n.pin(startup[1], 'Q')])
    expected = [bd.both(live, bd.inputs[control]),
                bd.both(live, bd.inputs[n.pin(startup[0], 'Q')]),
                qualified,
                bd.both(qualified, bd.inputs[n.pin(pre[0], 'Q')]),
                bd.both(qualified, bd.inputs[n.pin(pre[1], 'Q')]),
                bd.both(live, bd.inputs[n.pin(pre[2], 'Q')])]
    rows = []
    for p, value in zip(registers, expected):
        c = n.cells[p]
        require(c['kind'] == 'DFFCE' and set(c['ports']) == {'Q', 'D', 'CLK', 'CE', 'CLEAR'} and
                c['parameters'].get('INIT', "1'b0") == "1'b0",
                'release async primitive/INIT changed: ' + p)
        require(n.pin(p, 'CLK') == (inv_clock if p == release else source_clock) and
                n.pin(p, 'CE') in g.high, 'release clock or constant CE changed: ' + p)
        require(g.support(n.pin(p, 'CLEAR')) == {root_q} and
                bd.net(g, n.pin(p, 'CLEAR')) == bd.invert(live),
                'asynchronous assertion differs from actual root: ' + p)
        actual = bd.choose(bd.net(g, n.pin(p, 'CLEAR')), 0,
                           bd.choose(bd.net(g, n.pin(p, 'CE')), bd.net(g, n.pin(p, 'D')),
                                     bd.inputs[n.pin(p, 'Q')]))
        require(actual == value, 'startup-qualified next-Q changed: ' + p)
        rows.append(dict(register=p, clock=n.pin(p, 'CLK'),
                         reset_inclusive_next_q_exact=True, reset_before_enable=True))
    return dict(policy='task3-real-root-startup-qualified-monitor-release-v1',
                monitor=name, source_clock=source_clock, root_q=root_q,
                root_proof=root, source_sha256={SOURCE: SOURCE_SHA256},
                reset_before_enable=True, arbitrary_state_assignments=256,
                positive_startup_stages=2, positive_pre_stages=3,
                opposite_edge_release_register=release, clock_inverter=inverters[0],
                exact_next_q=rows, exception_added=False,
                reset_recovery_removal_accepted=False, clock_health_accepted=False,
                full_CDC_accepted=False, hardware_tested=False)
