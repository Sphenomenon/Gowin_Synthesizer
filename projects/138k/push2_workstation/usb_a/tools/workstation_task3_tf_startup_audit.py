"""Actual DIRECT TF root/startup/release next-Q proof, without EDA or SDC.

This local audit covers the ten u_tf_audio startup/release FFs and the exact
early-stage consumer inventory. The caller owns TF source binding, candidate
identity, full TF CDC, physical-tail closure and physical timing acceptance.
"""
import re

from tools.workstation_recording_phase1_cdc import complete_closure
from tools.workstation_runtime_pcm_cdc import BooleanDiagram, Graph
from tools.workstation_task3_root_reset_audit import (
    POLICY as ROOT_POLICY, ROOT_SOURCE, ROOT_SOURCE_SHA256, validate_root_publisher)

POLICY = 'task3-direct-tf-real-startup-release-v1'
SCOPE = 'u_tf_audio'


def require(condition, message):
    if not condition:
        raise ValueError('task3 TF startup audit: ' + message)


def audit_tf_startup_releases(n, *, root):
    g = Graph(n)
    require(root.get('policy') == ROOT_POLICY and root.get('all_state_assignments_proven') is True
            and root.get('actual_state_bits') == 35 and
            root.get('source_sha256', {}).get(ROOT_SOURCE) == ROOT_SOURCE_SHA256,
            'verified task3 real-root startup proof required')
    root_register = g.register('u_reset', 'started')
    root_q = n.pin(root_register, 'Q')
    validate_root_publisher(n, g, root)
    require(n.frames.get(SCOPE, {}).get('kind') == 'workstation_tf_direct_runtime_service',
            'actual TF owner is not DIRECT runtime service')
    guard_register = g.register('u_runtime_memory_guard', 'started_o')
    guard_q = n.pin(guard_register, 'Q')
    require(guard_q == n.canonical('', 'memory_guard_started') and
            n.cells[guard_register]['kind'] == 'DFFCE' and
            n.cells[guard_register]['parameters'].get('INIT', "1'b0") == "1'b0" and
            n.pin(guard_register, 'CLK') == 'clk_50m',
            'memory guard readiness boundary/publisher changed')
    runtime = n.canonical('', 'runtime_reset_n')
    common_rows, chains, all_registers = [], [], []
    for role, clock in (('source', 'clk_50m'), ('compute', 'audio_clk')):
        startup = g.group(SCOPE, 'startup_' + role, 2)
        release = g.group(SCOPE, role + '_release', 3)
        registers = startup + release
        all_registers.extend(registers)
        common = n.pin(startup[0], 'CLEAR')
        named = [root_q, guard_q, *(n.pin(path, 'Q') for path in registers)]
        require(len(named) == len(set(named)) == 7, 'TF startup state/reset sources alias')
        bd = BooleanDiagram(named)
        require(g.support(common) == {root_q} and
                bd.net(g, common) == bd.invert(bd.inputs[root_q]),
                'TF asynchronous common CLEAR is not exact inverse real root')
        require(g.support(runtime) == {root_q, guard_q} and
                bd.net(g, runtime) == bd.both(bd.inputs[root_q], bd.inputs[guard_q]),
                'runtime_reset_n is not exact root AND real guard readiness Q')
        require(n.pin(startup[0], 'D') == runtime and
                n.pin(startup[1], 'D') == n.pin(startup[0], 'Q'),
                'actual runtime reset sampling path bypassed/changed')
        rows = []
        for path in registers:
            cell = n.cells[path]
            require(cell['kind'] == 'DFFCE' and
                    set(cell['ports']) == {'Q', 'D', 'CLK', 'CE', 'CLEAR'},
                    'TF startup/release is not reviewed async CLEAR FF: ' + path)
            require(cell['parameters'].get('INIT', "1'b0") == "1'b0",
                    'TF startup/release effective INIT is not zero: ' + path)
            require(n.pin(path, 'CLK') == clock and n.pin(path, 'CLEAR') == common and
                    n.pin(path, 'CE') in g.high,
                    'TF startup/release clock, root CLEAR or constant CE changed: ' + path)
            rows.append(dict(register=path, primitive=cell['kind'], effective_init=0,
                **{pin.lower(): n.pin(path, pin) for pin in ('Q', 'D', 'CLK', 'CE', 'CLEAR')}))

        def prove(path, expected, contract):
            actual = bd.choose(bd.net(g, n.pin(path, 'CLEAR')), 0,
                bd.choose(bd.net(g, n.pin(path, 'CE')), bd.net(g, n.pin(path, 'D')),
                          bd.inputs[n.pin(path, 'Q')]))
            require(actual == expected, 'TF reset-inclusive next-Q changed: ' + path)
            next(row for row in rows if row['register'] == path).update(
                reset_before_enable=True, reset_inclusive_next_q_exact=True,
                contract=contract)

        live = bd.inputs[root_q]
        s0, s1 = (bd.inputs[n.pin(path, 'Q')] for path in startup)
        prove(startup[0], bd.both(live, bd.net(g, runtime)), 'root & runtime_reset_n')
        prove(startup[1], bd.both(live, s0), 'root & startup[0]')
        for bit, path in enumerate(release):
            previous = 1 if bit == 0 else bd.inputs[n.pin(release[bit-1], 'Q')]
            prove(path, bd.all([live, s1, previous]),
                  'root & startup[1]' + ('' if bit == 0 else ' & release[%d]' % (bit-1)))
        # The second startup stage synchronously clears *all* release stages;
        # it must therefore have exactly the three D consumers, not only r0.
        expected = (
            {startup[1] + '/D': clock},
            {path + '/D': clock for path in release},
            {release[1] + '/D': clock},
            {release[2] + '/D': clock},
        )
        closures = []
        for path, endpoints in zip((*startup, *release[:2]), expected):
            closure = complete_closure(n, g, [path])
            require(closure['ff_endpoints'] == endpoints and
                    not closure['primitive_endpoints'] and not closure['top_output_endpoints'],
                    'TF early startup/release consumer inventory changed: ' + path)
            closures.append(dict(source_register=path, **closure))
        chains.append(dict(id=role, clock=clock, startup_registers=startup,
            release_registers=release, registers=registers, common_clear=common,
            final_release_q=n.pin(release[2], 'Q'), named_inputs=named,
            next_q=rows, bdd_nodes=len(bd.nodes), all_state_assignments_proven=True,
            reset_and_state_assignment_count=128, early_consumer_closures=closures,
            root_assertion_asynchronous=True, startup_low_clears_all_release_stages_synchronously=True,
            first_release_rise_edge_from_zero_with_runtime_high=5,
            all_release_bits_clear_edge_after_runtime_low_from_fully_released=3,
            final_release_consumer_closure_proven=False))
        common_rows.append(common)
    expected_registers = {path for path in g.regs if re.fullmatch(
        re.escape(SCOPE) + r'/(startup_(source|compute)|(source|compute)_release)_\d+_s\d+', path)}
    require(set(all_registers) == expected_registers and len(set(all_registers)) == 10,
            'TF startup/release exact ten-register inventory changed')
    require(len(set(common_rows)) == 1, 'source/compute do not share the actual common assertion')
    return dict(policy=POLICY, root_register=root_register, root_q=root_q,
        root_source_sha256=root['source_sha256'], runtime_reset_n=runtime,
        readiness_publisher=guard_register, readiness_q=guard_q,
        readiness_state_transition_logic_proven=False,
        common_clear=common_rows[0], register_count=10, chains=chains,
        tf_source_binding_owned_by_caller=True, final_release_consumer_closure_proven=False,
        full_tf_cdc_proven=False, physical_tail_proven=False,
        routed_timing_verified=False, physical_recovery_removal_verified=False,
        hardware_tested=False, release_ready=False, deployment_allowed=False)
