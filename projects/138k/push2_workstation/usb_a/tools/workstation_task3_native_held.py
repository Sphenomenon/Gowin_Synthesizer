"""Explicit task3 DIRECT held/reset proof; old DEMO gates remain unchanged.

Actual register aliases are resolved from functional CLEAR cones. Gowin may
merge identical per-domain release chains across owners; a local name is not
evidence of their absence or of reset equivalence.
"""
import hashlib
import json
from pathlib import Path
import re

from tools.workstation_runtime_pcm_cdc import BooleanDiagram, Graph
from tools.workstation_recording_phase1_cdc import complete_closure
from tools.workstation_task3_root_reset_audit import (
    POLICY as ROOT_POLICY, ROOT_SOURCE, ROOT_SOURCE_SHA256,
    PAIRED_PROVIDER, M_PHONE_PROVIDER, M_PHONE_BATCH_PROVIDER, M_SYNC_PROVIDER,
    validate_root_publisher)

PROFILE = 'm-task3-direct'
POLICY = 'task3-direct-real-root-held-v1'


def require(condition, message):
    if not condition:
        raise ValueError('task3 native held audit: ' + message)


def clock(n, p):
    return n.canonical('', n.pin(p, 'CLK'))


def zero_ff(n, g, p, domain):
    require(n.cells[p]['kind'] == 'DFFCE' and clock(n, p) == domain and
            n.cells[p]['parameters'].get('INIT', "1'b0") == "1'b0",
            'clock/async-clear primitive/INIT changed: ' + p)


def inverse(g, clear, release_q, label):
    return g.equivalent(label, [clear, release_q], lambda x: x[0] == 1 - x[1],
                        cuts=(release_q,))


def release_from_clear(n, g, clear, root_q, domain, *, paired=False, batch=False):
    require(not batch or paired, 'batch release mapping requires explicit paired role')
    support = g.support(clear)
    require(len(support) == 1, 'owner CLEAR is not one registered release')
    last_q = next(iter(support))
    inverse(g, clear, last_q, 'functional CLEAR inverse final local release')
    reverse = []
    q = last_q
    for index in range(3):
        ds = g.drivers[q]
        require(len(ds) == 1 and ds[0][0] in g.regs and ds[0][1] == 'Q',
                'release producer missing/ambiguous')
        p = ds[0][0]
        zero_ff(n, g, p, domain)
        require(n.pin(p, 'CE') in g.high, 'local release CE is not unconditional')
        reverse.append(p)
        if index < 2:
            prior = g.support(n.pin(p, 'D'))
            require(len(prior) == 1, 'release shift predecessor missing')
            prior_q = next(iter(prior))
            g.equivalent('release direct predecessor', [n.pin(p, 'D'), prior_q],
                         lambda x: x[0] == x[1], cuts=(prior_q,))
            q = prior_q
        else:
            require(n.pin(p, 'D') in g.high, 'release first stage is not fill-one')
    rows = list(reversed(reverse))
    require(len({n.pin(p, 'CLEAR') for p in rows}) == 1,
            'local release assertion differs between stages')
    assertion = inverse(g, n.pin(rows[0], 'CLEAR'), root_q, 'local release common root assertion')
    early_closures = []
    final_control = ('u_task3_m_final_tap/destination_release_2_s0' if batch else
                     'u_task3_m_pcm_commands/p_release_2_s0' if paired else
                     'u_managed/midi_bytes/source_release_2_s0')
    merged_clk50 = rows == ['u_usb_pll/u_pll_init/enable_r_0_s0',
                           'u_usb_pll/u_pll_init/enable_r_1_s0',
                           final_control] and domain == 'clk_50m'
    for bit in (0, 1):
        closure = complete_closure(n, g, [rows[bit]])
        expected = {rows[bit+1] + '/D': domain}
        # This exact synthesis merge also owns the PLL initializer and the
        # TF first-source-edge flag. Inventory every consumer; a permissive
        # fanout waiver would conceal a bypass into functional reset/data.
        if merged_clk50 and bit == 0:
            expected['u_tf_audio/frames/source_alive_sync_0_s0/D'] = 'audio_clk'
        if merged_clk50 and bit == 1:
            for pll in ('u_cpu_pll', 'u_usb_pll'):
                expected[pll + '/pll_control_9_s0/D'] = domain
                for stem, bits, pin, suffix in (
                        ('RomAddr', range(4), 'CLEAR', 's1'),
                        ('RomDreg', (0, 1, 8, 9, 10, 12), 'CLEAR', 's0'),
                        ('locksig', range(6), 'RESET', 's0'),
                        ('state', range(3), 'CLEAR', 's0')):
                    for index in bits:
                        expected[f'{pll}/u_pll_init/{stem}_{index}_{suffix}/{pin}'] = domain
                expected[pll + '/u_pll_init/laststep_s0/CLEAR'] = domain
        require(closure['ff_endpoints'] == expected and
                not closure['primitive_endpoints'] and not closure['top_output_endpoints'],
                'local release early-stage extra consumer/bypass')
        early_closures.append(closure)
    return dict(stages=rows, final_q=last_q, common_assertion=assertion,
                domain=domain, release_edges=3, merged_register_aliases_resolved=True,
                exact_early_consumer_closures=early_closures,
                reviewed_pll_initializer_and_tf_first_edge_merge=merged_clk50,
                batch_observer_release_separation=batch)


def next_q(n, g, p, bd):
    zero_ff(n, g, p, clock(n, p))
    return bd.choose(bd.net(g, n.pin(p, 'CLEAR')), 0,
                     bd.choose(bd.net(g, n.pin(p, 'CE')),
                               bd.net(g, n.pin(p, 'D')), bd.inputs[n.pin(p, 'Q')]))


def next_proof(n, g, p, leaves, expected, label):
    leaves = list(dict.fromkeys([*leaves, n.pin(p, 'Q')]))
    bd = BooleanDiagram(leaves)
    actual = next_q(n, g, p, bd)
    require(actual == expected(bd), 'reset-inclusive next-Q changed: ' + label)
    return dict(register=p, inputs=leaves, boolean_assignments=1 << len(leaves),
                reset_inclusive_next_q_equal=True)


def audit_direct_held_boundaries(n, result, *, root):
    require(result.get('profile') == PROFILE, 'explicit DIRECT native profile required')
    require(root.get('policy') == ROOT_POLICY and root.get('actual_state_bits') == 35 and
            root.get('all_state_assignments_proven') is True and
            root.get('source_sha256', {}).get(ROOT_SOURCE) == ROOT_SOURCE_SHA256,
            'verified actual root startup/source proof required')
    g = Graph(n)
    root_reg = g.register('u_reset', 'started')
    root_q = n.pin(root_reg, 'Q')
    validate_root_publisher(n, g, root)
    paired = root['selected_provider'] in (PAIRED_PROVIDER, M_PHONE_PROVIDER,
                                          M_PHONE_BATCH_PROVIDER, M_SYNC_PROVIDER)
    batch = root['selected_provider'] in (M_PHONE_BATCH_PROVIDER, M_SYNC_PROVIDER)
    if batch:
        require(root.get('batch_mapped_structure', {}).get('mapped_structure_verified') is True and
                root['batch_mapped_structure'].get('policy') == 'task3_m_batch_mapped_command_snapshot_v1',
                'verified actual M batch mapped boundary required')
    scope = 'u_managed/pc_bytes'
    pc = next(row for row in result['mailboxes'] if row['scope'] == scope)
    held, captured = (g.group(scope, stem, 8) for stem in ('held_data', 'destination_data'))
    closure = complete_closure(n, g, held)
    require(closure['ff_endpoints'] == {p + '/D': 'audio_clk' for p in captured} and
            not closure['primitive_endpoints'] and not closure['top_output_endpoints'],
            'PC held payload exact consumer closure changed')
    source = [g.register(scope, s) for s in ('ack_meta', 'ack_sync', 'request_toggle')]
    source += held + g.group(scope, 'drop_count', 32)
    destination = [g.register(scope, s) for s in (
        'req_meta', 'req_sync', 'req_settled', 'acknowledge_toggle', 'destination_valid')]
    destination += captured
    require(set(source + destination) == {p for p in g.regs if p.startswith(scope + '/')},
            'DIRECT PC exact functional register inventory changed')
    pc_releases = {}
    for side, owners, domain in (('source', source, 'clk_50m'),
                                  ('destination', destination, 'audio_clk')):
        for p in owners:
            zero_ff(n, g, p, domain)
        clears = {n.pin(p, 'CLEAR') for p in owners}
        require(len(clears) == 1, 'PC shared local reset changed')
        clear = next(iter(clears))
        release = release_from_clear(n, g, clear, root_q, domain, paired=paired, batch=batch)
        pc_releases[side] = dict(release, owners=owners, reset_asserted_value=0)
    source_q = pc_releases['source']['final_q']
    dest_q = pc_releases['destination']['final_q']
    cq = lambda stem: n.pin(g.register(scope, stem), 'Q')
    controls = []
    for stem, previous, local_q in (
            ('ack_meta', 'acknowledge_toggle', source_q), ('ack_sync', 'ack_meta', source_q),
            ('req_meta', 'request_toggle', dest_q), ('req_sync', 'req_meta', dest_q),
            ('req_settled', 'req_sync', dest_q)):
        p = g.register(scope, stem)
        controls.append(next_proof(n, g, p, [local_q, cq(previous)],
            lambda b, r=local_q, v=cq(previous): b.both(b.inputs[r], b.inputs[v]), stem))
    capture_ce = n.pin(captured[0], 'CE')
    for p, h in zip(captured, held):
        leaves = [dest_q, cq('req_settled'), cq('acknowledge_toggle'), n.pin(h, 'Q')]
        controls.append(next_proof(n, g, p, leaves,
            lambda b, p=p, h=h: b.both(b.inputs[dest_q], b.choose(
                b.different(b.inputs[cq('req_settled')], b.inputs[cq('acknowledge_toggle')]),
                b.inputs[n.pin(h, 'Q')], b.inputs[n.pin(p, 'Q')])),'PC payload'))
    chains = []
    for name in ('request', 'acknowledge'):
        row = pc[name]
        first, second = (row[key].rsplit('/', 1)[0] for key in ('first', 'second'))
        c = complete_closure(n, g, [first])
        require(c['ff_endpoints'] == {second + '/D': n.pin(second, 'CLK')} and
                not c['primitive_endpoints'] and not c['top_output_endpoints'],
                'PC first-stage complete consumer closure changed')
        chains.append(dict(row, closure=c))
    apb = 'u_managed/control_cdc'
    apb_resets = {}
    for side, stem, domain, names, groups in (
            ('source', 'p_release', 'ram_clk',
             ('request_toggle', 'state_0', 'state_1', 'ack_meta', 'ack_sync', 'ack_settled'),
             (('request_held', 49), ('response_local', 33))),
            ('destination', 'a_release', 'audio_clk',
             ('acknowledge_toggle', 'req_meta', 'req_sync', 'req_settled', 'request_decoded'),
             (('request_local', 49), ('response_held', 33)))):
        release_scope = 'u_task3_pair_link/config_cdc' if paired and side == 'source' else apb
        releases = g.group(release_scope, stem, 3)
        owners = [g.register(apb, name) for name in names]
        owners += [p for name, width in groups for p in g.group(apb, name, width)]
        for p in releases + owners:
            zero_ff(n, g, p, domain)
        require(all(n.pin(p, 'CE') in g.high for p in releases) and
                n.pin(releases[0], 'D') in g.high and
                all(n.pin(releases[i], 'D') == n.pin(releases[i-1], 'Q') for i in (1, 2)),
                'APB three-stage local release changed')
        require(len({n.pin(p, 'CLEAR') for p in releases}) == 1 and
                len({n.pin(p, 'CLEAR') for p in owners}) == 1,
                'APB shared payload/control/release assertion changed')
        proof = inverse(g, n.pin(owners[0], 'CLEAR'), n.pin(releases[2], 'Q'),
                        'APB functional reset inverse local final release')
        apb_resets[side] = dict(release=releases, shared_assertion=n.pin(releases[0], 'CLEAR'),
                                affected_registers=len(owners), proof=proof)
    require(apb_resets['source']['shared_assertion'] == apb_resets['destination']['shared_assertion'],
            'APB common assertion differs across domains')
    preset = n.canonical('', 'preset_n')
    apb_resets['common_assertion_proof'] = g.equivalent('DIRECT APB exact root AND CPU assertion',
        [apb_resets['source']['shared_assertion'], root_q, preset],
        lambda x: x[0] == 1 - (x[1] & x[2]), cuts=(root_q, preset))
    return dict(pc_source_pins=[p + '/Q' for p in held], pc_capture_pins=[p + '/D' for p in captured],
        pc_payload_closure=closure, pc_chains=chains, pc_actual_reset=dict(
            mode='explicit_direct_root_three_edge_release', runtime_reset_supported=False,
            root_power_up_assertion_supported=True, releases=pc_releases,
            reset_inclusive_next_q=controls, reusable_reset_simulation=False),
        apb_request_source_pins=[p + '/Q' for p in g.group(apb, 'request_held', 49)],
        apb_request_capture_pins=[p + '/D' for p in g.group(apb, 'request_local', 49)],
        apb_resets=apb_resets, new_chains=[chains[0], *result['timing_boundaries']['apb_response']['chains']],
        max_delay_ns=13.020, pc_minimum_receiving_capture_edge=4,
        apb_request_minimum_receiving_capture_edge=3, physical_timing_verified=False, hardware_tested=False)


def audit_direct_tf_owner(n):
    """Strict scope/inventory and real 68-to-67 status held mailbox proof.

    Bit zero is used by source-side change detection and has no compute sink.
    The receipt owner is separately identified; full receipt consumer closure
    and the new TF SDC inventory remain separate mandatory integration gates.
    """
    g = Graph(n)
    scope = 'u_tf_audio'
    held = g.group(scope, 'held_status', 68)
    captured = {bit: g.register(scope, 'compute_status', bit) for bit in range(1, 68)}
    require(not any(re.search(r'/compute_status_0_s\d+$', p) for p in g.regs),
            'DIRECT status consumed-bit inventory changed')
    require(not any(re.search(r'/(held_control|compute_control|memory_quiet_sync)_', p)
                    for p in n.cells if p.startswith(scope + '/')),
            'DIRECT owner retained legacy TF mailbox')
    for p in held:
        zero_ff(n, g, p, 'clk_50m')
    for p in captured.values():
        zero_ff(n, g, p, 'audio_clk')
    require(all(n.pin(p, 'D') == n.pin(held[bit], 'Q') for bit, p in captured.items()),
            'DIRECT status exact held/capture bit mapping changed')
    source_ces = {n.pin(p, 'CE') for p in held}
    capture_ces = {n.pin(p, 'CE') for p in captured.values()}
    require(len(source_ces) == len(capture_ces) == 1, 'DIRECT status common capture CE changed')
    request = g.register(scope, 'status_request')
    ack = g.register(scope, 'status_ack')
    zero_ff(n, g, request, 'clk_50m')
    zero_ff(n, g, ack, 'audio_clk')
    zero_ff(n, g, g.register(scope, 'status_capture'), 'audio_clk')
    root_q = n.pin(g.register('u_reset', 'started'), 'Q')
    q = lambda stem, bit=None: n.pin(g.register(scope, stem, bit), 'Q')
    source_q, compute_q = q('source_release', 2), q('compute_release', 2)
    common_clear = n.pin(request, 'CLEAR')
    all_status = [*held, *captured.values(), request, ack, g.register(scope, 'status_capture')]
    stages = []
    for stem, producer, domain in (('status_request_sync', request, 'audio_clk'),
                                    ('status_ack_sync', ack, 'clk_50m')):
        first, second = g.group(scope, stem, 2)
        for p in (first, second):
            zero_ff(n, g, p, domain)
            require(n.pin(p, 'CE') in g.high, 'DIRECT status synchronizer CE changed')
        require(n.pin(first, 'D') == n.pin(producer, 'Q') and
                n.pin(second, 'D') == n.pin(first, 'Q'), 'DIRECT status synchronizer bypass')
        c = complete_closure(n, g, [first])
        require(c['ff_endpoints'] == {second + '/D': domain} and not c['primitive_endpoints'] and
                not c['top_output_endpoints'], 'DIRECT status meta-stage extra consumer')
        stages.append(dict(source=producer + '/Q', first=first + '/D', second=second + '/D'))
        all_status.extend((first, second))
    closure = complete_closure(n, g, held)
    remote = {p: domain for p, domain in closure['ff_endpoints'].items() if domain != 'clk_50m'}
    require(remote == {p + '/D': 'audio_clk' for p in captured.values()} and
            not closure['primitive_endpoints'] and not closure['top_output_endpoints'],
            'DIRECT status exact remote consumer closure changed')
    require(all(n.pin(p, 'CLEAR') == common_clear for p in all_status),
            'DIRECT status common root assertion changed')
    root_assertion = inverse(g, common_clear, root_q, 'DIRECT status root assertion')
    source_enable = next(iter(source_ces))
    gate, output = g.drivers[source_enable][0]
    require(n.cells[gate]['kind'] == 'LUT4' and output == 'F',
            'DIRECT status acceptance gate changed')
    gate_inputs = [n.pin(gate, 'I' + str(i)) for i in range(4)]
    request_q, ack_sync_q = q('status_request'), q('status_ack_sync', 1)
    known = {request_q, ack_sync_q, source_q}
    require(known.issubset(gate_inputs) and len(set(gate_inputs)) == 4,
            'DIRECT status acceptance request/ACK/release inputs changed')
    changed = next(value for value in gate_inputs if value not in known)
    require(g.inequality_chain(changed) == {
            frozenset((n.pin(p, 'Q'), n.pin(p, 'D'))) for p in held},
            'DIRECT status comparison must cover every exact held/desired bit')
    bd = BooleanDiagram(gate_inputs)
    accepted = bd.all((bd.inputs[source_q], bd.inputs[changed],
                      bd.invert(bd.different(bd.inputs[request_q], bd.inputs[ack_sync_q]))))
    require(bd.net(g, source_enable) == accepted, 'DIRECT status overwrite before ACK')
    updates = []
    # The complete 68-bit NE carry is checked above. Treat that proven result
    # as a named input when checking individual FF reset/CE priorities.
    accept_leaves = [root_q, *gate_inputs]
    def acceptance(b):
        return b.all((b.inputs[source_q], b.inputs[changed],
                      b.invert(b.different(b.inputs[request_q], b.inputs[ack_sync_q]))))
    updates.append(next_proof(n, g, request, accept_leaves,
        lambda b: b.both(b.inputs[root_q], b.different(b.inputs[request_q], acceptance(b))),
        'DIRECT status request exact capture toggle'))
    for p in held:
        data = n.pin(p, 'D')
        updates.append(next_proof(n, g, p, [*accept_leaves, data],
            lambda b, p=p, data=data: b.both(b.inputs[root_q], b.choose(
                acceptance(b), b.inputs[data], b.inputs[n.pin(p, 'Q')])),
            'DIRECT held status bit'))
    capture_q, ack_q, sync_q = q('status_capture'), q('status_ack'), q('status_request_sync', 1)
    dest_leaves = [root_q, compute_q, capture_q, ack_q, sync_q]
    updates.append(next_proof(n, g, g.register(scope, 'status_capture'), dest_leaves,
        lambda b: b.both(b.inputs[root_q], b.both(
            b.invert(b.both(b.inputs[compute_q], b.inputs[capture_q])),
            b.different(b.inputs[sync_q], b.inputs[ack_q]))),
        'DIRECT status capture settled request with priority clear'))
    for p, data in [(ack, sync_q), *[(p, n.pin(held[bit], 'Q')) for bit, p in captured.items()]]:
        updates.append(next_proof(n, g, p, [*dest_leaves, data],
            lambda b, p=p, data=data: b.both(b.inputs[root_q], b.choose(
                b.both(b.inputs[compute_q], b.inputs[capture_q]),
                b.inputs[data], b.inputs[n.pin(p, 'Q')])),
            'DIRECT status ACK/payload shared capture'))
    receipt_held = g.group(scope, 'receipt_payload', 34)
    receipt_closure = complete_closure(n, g, receipt_held)
    # A broad physical consumer graph is measured, not replaced by the short
    # logical sink list in the current SDC. Until those actual D/CE/WRE/CEB
    # endpoints have finite setup bounds this owner cannot pass the full gate.
    endpoint_bytes = json.dumps(receipt_closure, sort_keys=True).encode()
    return dict(policy='direct-status-root-next-q-v2', held_bits=68, consumed_bits=67,
        source_pins=[p + '/Q' for p in held], capture_pins=[p + '/D' for p in captured.values()],
        source_enable=next(iter(source_ces)), capture_enable=next(iter(capture_ces)), chains=stages,
        exact_remote_payload_closure=True, root_assertion=root_assertion,
        held_desired_comparison_all_68_bits=True, reset_inclusive_state_updates=updates,
        full_status_acceptance_next_q_proven=True,
        receipt_complete_closure=receipt_closure,
        receipt_complete_closure_sha256=hashlib.sha256(endpoint_bytes).hexdigest(),
        receipt_measured_ff_endpoints=len(receipt_closure['ff_endpoints']),
        receipt_measured_primitive_endpoints=len(receipt_closure['primitive_endpoints']),
        receipt_consumer_closure_proven=False, full_direct_tf_cdc_accepted=False,
        gate_pending=['receipt source/acceptance and all actual remote consumer finite bounds',
                      'DIRECT TF startup release and physical-tail CDC complete proof'])
