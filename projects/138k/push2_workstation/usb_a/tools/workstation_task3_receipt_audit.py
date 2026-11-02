"""DIRECT receipt mailbox: actual held/local boundary and exact next-Q.

The source event-condition and per-bit source data are explicit cuts, not a
proof of physical-tail event/data semantics.  No source selection, candidate,
SDC, EDA or board operation is performed. Full TF CDC remains a separate gate.
"""
import re

from tools.workstation_recording_phase1_cdc import complete_closure
from tools.workstation_runtime_pcm_cdc import BooleanDiagram, Graph
from tools.workstation_task3_root_reset_audit import (
    POLICY as ROOT_POLICY, ROOT_SOURCE, ROOT_SOURCE_SHA256, PAIRED_PROVIDER, M_PHONE_PROVIDER,
    validate_root_publisher)

POLICY = 'task3-direct-receipt-local-mailbox-v1'
SCOPE = 'u_tf_audio'
TAIL = 'u_managed/runtime/g_direct_tf.tail'


def require(condition, message):
    if not condition:
        raise ValueError('task3 receipt audit: ' + message)


def _paired_source_lifecycle(n, g, root, *, ff, next_proof, proofs,
                             payload, request, ack_sync, source_ce):
    """Exact paired source/abort/session proof; no event or payload data cuts.

    Four arithmetic summaries are admitted only after their entire actual NE
    chains match every reviewed registered operand pair. The remaining inputs
    are explicitly inventoried audio-clock FF Qs. Fault producers, blocked's
    state machine and physical-tail event meanings remain external owners;
    abort_queued and all receipt queue/session state are proved here.
    """
    s, r = SCOPE, 'u_managed/runtime'
    ws = r + '/service/workstation'
    fx, ds = ws + '/runtime_effects.effects', ws + '/runtime_effects.effects/delay_stage'
    reg = lambda scope, stem, bit=None: g.register(scope, stem, bit)
    q = lambda p: n.pin(p, 'Q')
    rq = lambda scope, stem, bit=None: q(reg(scope, stem, bit))
    operands = {
        'generation': {frozenset((rq(s, 'compute_status', 36+i),
                                 rq(s+'/frames', 'expected_generation_o', i))) for i in range(32)},
        'panic': {frozenset((rq(ws, 'panic_epoch_o', i),
                            rq(r, 'g_direct_tf.panic_q', i))) for i in range(10)},
        'cancel': {frozenset((rq(r+'/cpu_pcm.owner', 'cancel_epoch_o', i),
                             rq(r, 'g_direct_tf.cancel_q', i))) for i in range(22)},
        'epoch': {frozenset((rq(r, 'compute_epoch', i),
                            rq(r, 'g_direct_tf.epoch_q', i))) for i in range(32)},
    }
    carries = g.carry_frontier(source_ce)
    require(len(carries) == 4, 'paired receipt must have exactly four abort/status NE chains')
    comparisons, comparison_rows = {}, []
    for carry in sorted(carries):
        actual = g.inequality_chain(carry)
        labels = [label for label, pairs in operands.items() if pairs == actual]
        require(len(labels) == 1 and labels[0] not in comparisons,
                'paired abort/status NE operand identity/bit inventory changed')
        label = labels[0]
        comparisons[label] = carry
        comparison_rows.append(dict(id=label, actual_output=carry,
            operand_pairs=sorted(sorted(pair) for pair in actual), width=len(actual),
            exact_NE_chain_all_bits_verified=True, summary_is_unverified_cut=False))
    require(set(comparisons) == set(operands), 'paired receipt comparison inventory incomplete')
    state = dict(root=root['root_register'], compute=reg(s, 'compute_release', 2),
        aq=reg(s, 'abort_queued'), eq=reg(s, 'eos_queued'),
        eos=reg(TAIL, 'physical_eos_o'), req=request, ack=ack_sync[1],
        active=reg(s, 'compute_status', 3), expected=reg(s+'/frames', 'expected_generation_valid_o'),
        blocked=reg(r, 'g_direct_tf.blocked'), rate=reg(r, 'compute_rate'),
        oldrate=reg(r, 'g_direct_tf.rate_q'), context=reg(r, 'compute_context_valid'),
        integration=reg(r, 'integration_fault'), tail=reg(TAIL, 'failed_o'),
        oldtail=reg(r, 'g_direct_tf.tail_failed_q'), configfault=reg(ws, 'runtime_configuration.failed'),
        dmafault=reg(fx, 'dma_fault_sync'), effectfault=reg(fx, 'transaction_fault'),
        overflow=reg(ds, 'overflow_sticky'), peerfault=reg(ds, 'peer_fault'),
        delayfault=reg(ds, 'transaction_fault'), underflow=reg(ds, 'underflow_sticky'))
    state.update({'history'+str(i): reg(r+'/cpu_pcm.owner', 'history_state', i) for i in range(3)})
    leaves = [q(p) for p in state.values()] + list(comparisons.values())
    require(len(leaves) == len(set(leaves)), 'paired receipt state/comparison aliases changed')
    # All remaining Boolean inputs must be these real registered publishers;
    # in particular abort_queued is not an unconstrained event-condition cut.
    require(g.support(source_ce, cuts=carries) == set(leaves) - {root['root_q']},
            'paired source acceptance has an unreviewed state or arithmetic input')
    external = []
    for label, p in state.items():
        if label == 'root':
            continue
        cell = n.cells[p]
        require(cell['kind'] == 'DFFCE' and n.pin(p, 'CLK') == 'audio_clk' and
                cell['parameters'].get('INIT', "1'b0") == "1'b0",
                'paired receipt input is not reviewed audio-clock zero-INIT FF: ' + p)
        external.append(dict(id=label, register=p, q=q(p), clear=n.pin(p, 'CLEAR'),
                             clock='audio_clk', effective_init=0))
    v = lambda b: {name: b.inputs[q(p)] for name, p in state.items()}

    def either(b, values):
        result = 0
        for value in values:
            result = b.either(result, value)
        return result

    def raw_abort(b):
        x = v(b)
        cmp = {name: b.inputs[net] for name, net in comparisons.items()}
        # Maintained PCM owner H_FAULT=4; the mapped state retains three bits.
        hard_fault = b.all([x['history2'], b.invert(x['history1']), b.invert(x['history0'])])
        compute_fault = either(b, [hard_fault, *[x[name] for name in (
            'integration', 'configfault', 'dmafault', 'effectfault',
            'overflow', 'peerfault', 'delayfault', 'underflow')]])
        changed = either(b, [cmp['panic'], cmp['cancel'], cmp['epoch'],
            b.different(x['rate'], x['oldrate']), compute_fault, b.invert(x['context'])])
        active = b.all([x['compute'], x['expected'], b.invert(cmp['generation']), x['active']])
        local_abort = b.all([active, b.invert(x['blocked']), changed])
        failed_edge = b.both(x['tail'], b.invert(x['oldtail']))
        return b.either(local_abort, failed_edge)

    def free_release(b):
        x = v(b)
        return b.both(x['compute'], b.invert(b.different(x['req'], x['ack'])))

    def accepted(b):
        x = v(b)
        return b.both(free_release(b), either(b, [x['aq'], raw_abort(b), x['eq'], x['eos']]))

    def queue_capture(b):
        x = v(b)
        return b.either(raw_abort(b), b.both(x['eos'], b.invert(x['aq'])))

    bd = BooleanDiagram(leaves)
    require(bd.net(g, source_ce) == accepted(bd),
            'paired source CE differs from released/free and real abort-or-EOS event')
    queue = [state['aq'], state['eq'], *g.group(s, 'queued_receipt_session', 32)]
    require({p for p in g.regs if re.fullmatch(re.escape(s) +
            r'/(?:abort_queued|eos_queued|queued_receipt_session_\d+)_s\d+', p)} == set(queue),
            'paired abort/EOS/session queue exact register inventory changed')
    queue_rows = [ff(p, 'audio_clk') for p in queue]
    queue_start = len(proofs)
    next_proof(state['aq'], leaves,
        lambda b: b.all([v(b)['root'], b.invert(free_release(b)), b.either(v(b)['aq'], raw_abort(b))]),
        'root & !released_free & (abort_queued | real_abort); accepted abort clears queue')
    next_proof(state['eq'], leaves,
        lambda b: b.all([v(b)['root'], b.invert(free_release(b)), b.invert(raw_abort(b)),
            b.either(v(b)['eq'], b.both(v(b)['eos'], b.invert(v(b)['aq'])))]),
        'root & !released_free & !real_abort & (eos_queued | (physicalEOS & !abort_queued))')
    for bit, p in enumerate(queue[2:]):
        current = rq(s, 'compute_status', bit+4)
        next_proof(p, [*leaves, current],
            lambda b, p=p, current=current: b.both(v(b)['root'], b.choose(
                queue_capture(b), b.inputs[current], b.inputs[q(p)])),
            'root & choose(real_abort | (physicalEOS & !abort_queued), current session bit, queued session bit)')
    queue_proofs = proofs[queue_start:]
    del proofs[queue_start:]
    # These real one-cycle snapshots give the NE deltas and failed rising edge
    # their declared meaning. Their input owners' business state is separate.
    snapshots = [(reg(r, 'g_direct_tf.'+old, i), reg(owner, new, i))
        for old, owner, new, width in (
            ('panic_q', ws, 'panic_epoch_o', 10),
            ('cancel_q', r+'/cpu_pcm.owner', 'cancel_epoch_o', 22),
            ('epoch_q', r, 'compute_epoch', 32)) for i in range(width)]
    snapshots.extend(((state['oldrate'], state['rate']), (state['oldtail'], state['tail'])))
    snapshot_rows = [ff(p, 'audio_clk') for p, upstream in snapshots]
    snapshot_start = len(proofs)
    for p, upstream in snapshots:
        require(n.pin(p, 'CE') in g.high and n.pin(p, 'D') == q(upstream),
                'paired abort history snapshot input/enable changed: ' + p)
        next_proof(p, [root['root_q'], q(upstream)],
            lambda b, upstream=upstream: b.both(b.inputs[root['root_q']], b.inputs[q(upstream)]),
            'root & exact current-state publisher Q; one-cycle abort history')
    snapshot_proofs = proofs[snapshot_start:]
    del proofs[snapshot_start:]
    next_proof(request, leaves,
        lambda b: b.both(v(b)['root'], b.different(v(b)['req'], accepted(b))),
        'root & (request XOR accepted paired abort/EOS event)')
    for bit, p in enumerate(payload):
        current = rq(s, 'compute_status', bit+2) if bit >= 2 else None
        queued = q(queue[bit]) if bit >= 2 else None

        def expected(b, p=p, bit=bit, current=current, queued=queued):
            x = v(b)
            abort = b.either(x['aq'], raw_abort(b))
            data = (abort if bit == 1 else b.invert(abort) if bit == 0 else
                    b.choose(queue_capture(b), b.inputs[current], b.inputs[queued]))
            return b.both(x['root'], b.choose(accepted(b), data, b.inputs[q(p)]))

        next_proof(p, [*leaves, *([current, queued] if bit >= 2 else [])], expected,
            'root & choose(accepted, abort-priority kind/exact current-or-queued session, held Q)',
            source_data_semantics_proven=True, source_data_is_arbitrary_cut=False)
    require(len(queue_proofs) == 34 and len(snapshot_proofs) == 66,
            'paired abort/session/history next-Q proof incomplete')
    return dict(policy='task3_m_paired_receipt_source_abort_lifecycle_v1',
        exact_inequality_comparisons=comparison_rows, registered_state_inputs=external,
        arbitrary_abort_or_data_cuts=[], source_acceptance_real_cone_proven=True,
        abort_priority_over_EOS_proven=True, busy_preserves_queued_abort_proven=True,
        abort_and_EOS_queue_registers=queue_rows, queue_next_q=queue_proofs,
        history_snapshot_registers=snapshot_rows, history_snapshot_next_q=snapshot_proofs,
        supplementary_next_q_register_count=100,
        fault_producer_and_blocked_state_machine_semantics_proven=False,
        physical_tail_event_semantics_proven=False, full_tf_cdc_proven=False)


def audit_direct_receipt(n, *, root):
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
    # Reject old broad-fanout receipt implementations before inspecting their
    # source gates. An older netlist is not a positive fixture for this policy.
    retained_local = {p for p in g.regs if re.fullmatch(
        re.escape(SCOPE) + r'/receipt_local_\d+_s\d+', p)}
    require(len(retained_local) == 34,
            'missing required receipt_local[33:0] receiver boundary')
    payload = g.group(SCOPE, 'receipt_payload', 34)
    local = g.group(SCOPE, 'receipt_local', 34)
    request = g.register(SCOPE, 'receipt_request')
    seen = g.register(SCOPE, 'receipt_seen')
    capture = g.register(SCOPE, 'receipt_capture')
    dispatch = g.register(SCOPE, 'receipt_dispatch')
    request_sync = g.group(SCOPE, 'receipt_request_sync', 2)
    ack_sync = g.group(SCOPE, 'receipt_ack_sync', 2)
    source = [*payload, request, *ack_sync]
    receiver = [*local, seen, capture, dispatch, *request_sync]
    inventory = set(source + receiver)
    require(len(inventory) == 76 and
            {p for p in g.regs if p.startswith(SCOPE + '/receipt_')} == inventory,
            'exact receipt inventory/merged ACK ownership changed')
    common = n.pin(request, 'CLEAR')
    assertion = BooleanDiagram([root_q])
    require(g.support(common) == {root_q} and
            assertion.net(g, common) == assertion.invert(assertion.inputs[root_q]),
            'receipt common CLEAR is not exact inverse real root')
    ff_rows = []

    def ff(path, clock):
        cell = n.cells[path]
        require(cell['kind'] == 'DFFCE' and
                set(cell['ports']) == {'Q', 'D', 'CLK', 'CE', 'CLEAR'},
                'not reviewed async CLEAR FF: ' + path)
        require(cell['parameters'].get('INIT', "1'b0") == "1'b0" and
                n.pin(path, 'CLK') == clock and n.pin(path, 'CLEAR') == common,
                'receipt FF INIT/clock/common CLEAR changed: ' + path)
        return dict(register=path, primitive=cell['kind'], effective_init=0,
                    **{pin.lower(): n.pin(path, pin) for pin in ('Q', 'D', 'CLK', 'CE', 'CLEAR')})

    ff_rows.extend(ff(p, 'audio_clk') for p in source)
    ff_rows.extend(ff(p, 'clk_50m') for p in receiver)
    q = lambda p: n.pin(p, 'Q')
    rq, sq, cq = q(request), q(seen), q(capture)
    r1, a1 = q(request_sync[1]), q(ack_sync[1])
    proofs = []

    def next_proof(path, leaves, predicate, contract, **extra):
        # Source data cuts may be constants or already named control leaves.
        named = list(dict.fromkeys([*leaves, q(path)]))
        require(not any(net in g.high | g.low for net in named), 'constant named next-Q state/cut')
        bd = BooleanDiagram(named)
        actual = bd.choose(bd.net(g, n.pin(path, 'CLEAR')), 0,
            bd.choose(bd.net(g, n.pin(path, 'CE')), bd.net(g, n.pin(path, 'D')),
                      bd.inputs[q(path)]))
        require(actual == predicate(bd), 'reset-inclusive next-Q changed: ' + path)
        row = dict(register=path, contract=contract, named_inputs=named,
            exhaustive_assignments=1 << len(named), bdd_nodes=len(bd.nodes),
            reset_before_enable=True, reset_inclusive_next_q_exact=True, **extra)
        proofs.append(row)
        return row

    receiver_leaves = [root_q, r1, sq, cq]

    def event(bd):
        return bd.both(bd.inputs[cq], bd.different(bd.inputs[r1], bd.inputs[sq]))

    local_ces = {n.pin(p, 'CE') for p in local}
    require(len(local_ces) == 1, 'receipt_local does not have one common event CE')
    local_ce = next(iter(local_ces))
    bd = BooleanDiagram(receiver_leaves)
    require(bd.net(g, local_ce) == event(bd),
            'local capture CE is not capture && request_sync1!=seen')
    require(all(n.pin(p, 'D') == q(payload[bit]) for bit, p in enumerate(local)),
            'receipt payload-to-local exact bit mapping changed')
    payload_closure = complete_closure(n, g, payload)
    require(payload_closure['ff_endpoints'] == {p + '/D': 'clk_50m' for p in local} and
            not payload_closure['primitive_endpoints'] and not payload_closure['top_output_endpoints'],
            'held receipt payload reaches a consumer outside the 34 local D pins')
    for bit, path in enumerate(local):
        data = q(payload[bit])
        next_proof(path, [*receiver_leaves, data],
            lambda b, path=path, data=data: b.both(b.inputs[root_q],
                b.choose(event(b), b.inputs[data], b.inputs[q(path)])),
            'root & choose(capture && reqsync1!=seen, corresponding held payload Q, local Q)')
    next_proof(dispatch, receiver_leaves,
        lambda b: b.both(b.inputs[root_q], event(b)), 'root & receipt_event')
    next_proof(capture, receiver_leaves,
        lambda b: b.all([b.inputs[root_q], b.different(b.inputs[r1], b.inputs[sq]), b.invert(b.inputs[cq])]),
        'root & (reqsync1!=seen) & !capture')
    next_proof(seen, receiver_leaves,
        lambda b: b.both(b.inputs[root_q], b.choose(event(b), b.inputs[r1], b.inputs[sq])),
        'root & choose(receipt_event, reqsync1, seen); merged ACK publisher')
    chains = []
    for name, producer, sync, clock in (
        ('request', request, request_sync, 'clk_50m'),
        ('ack', seen, ack_sync, 'audio_clk'),
    ):
        first, second = sync
        require(all(n.pin(p, 'CE') in g.high for p in sync) and
                n.pin(first, 'D') == q(producer) and n.pin(second, 'D') == q(first),
                'receipt synchronization chain CE/direct D mapping changed: ' + name)
        closure = complete_closure(n, g, [first])
        require(closure['ff_endpoints'] == {second + '/D': clock} and
                not closure['primitive_endpoints'] and not closure['top_output_endpoints'],
                'receipt first synchronizer has extra consumer: ' + name)
        for path, upstream in ((first, producer), (second, first)):
            next_proof(path, [root_q, q(upstream)],
                lambda b, upstream=upstream: b.both(b.inputs[root_q], b.inputs[q(upstream)]),
                'root & exact prior/source Q')
        producer_closure = complete_closure(n, g, [producer])
        producer_clock = 'audio_clk' if name == 'request' else 'clk_50m'
        remote = {pin: domain for pin, domain in producer_closure['ff_endpoints'].items()
                  if domain != producer_clock}
        require(remote == {first + '/D': clock} and not producer_closure['primitive_endpoints'] and
                not producer_closure['top_output_endpoints'],
                'receipt toggle has extra remote/opaque/top consumer: ' + name)
        chains.append(dict(id=name, source=producer + '/Q', first=first + '/D', second=second + '/D',
                           first_consumer_closure=closure, producer_complete_closure=producer_closure))
    compute_release = g.register(SCOPE, 'compute_release', 2)
    queued_eos = g.register(SCOPE, 'eos_queued')
    physical_eos = g.register(TAIL, 'physical_eos_o')
    boundaries = [ff(p, 'audio_clk') for p in (compute_release, queued_eos, physical_eos)]
    require(q(physical_eos) == n.canonical('', 'tf_physical_eos'),
            'receipt physical EOS source is not actual tail registered publisher')
    condition_cut = n.pin(payload[0], 'D')
    condition_driver = g.drivers[condition_cut]
    require(condition_cut not in g.high | g.low and len(condition_driver) == 1 and
            condition_driver[0][0] not in g.regs and
            re.fullmatch(r'INV|LUT[1-6]', n.cells[condition_driver[0][0]]['kind']),
            'payload0 D is not the reviewed independent combinational event-condition cut')
    source_ce = n.pin(request, 'CE')
    require(all(n.pin(p, 'CE') == source_ce for p in payload),
            'source payload and request do not commit on the same CE')
    paired = root['selected_provider'] in (PAIRED_PROVIDER, M_PHONE_PROVIDER)
    paired_lifecycle = None
    if paired:
        paired_lifecycle = _paired_source_lifecycle(n, g, root, ff=ff, next_proof=next_proof,
            proofs=proofs, payload=payload, request=request, ack_sync=ack_sync, source_ce=source_ce)
    else:
        source_leaves = [root_q, q(compute_release), rq, a1, condition_cut, q(queued_eos), q(physical_eos)]
        require(len(source_leaves) == len(set(source_leaves)), 'source acceptance state/event cuts alias')

        def accepted(b):
            event_present = b.either(b.invert(b.inputs[condition_cut]),
                                    b.either(b.inputs[q(queued_eos)], b.inputs[q(physical_eos)]))
            free = b.invert(b.different(b.inputs[rq], b.inputs[a1]))
            return b.all([b.inputs[q(compute_release)], free, event_present])

        bd = BooleanDiagram(source_leaves)
        require(bd.net(g, source_ce) == accepted(bd),
                'source CE is not compute_release && free && (!payload0.D || queuedEOS || physicalEOS)')
        next_proof(request, source_leaves,
            lambda b: b.both(b.inputs[root_q], b.different(b.inputs[rq], accepted(b))),
            'root & (request XOR accepted); busy forbids source commit')
        for bit, path in enumerate(payload):
            data = n.pin(path, 'D')
            data_leaves = [] if data in g.high | g.low else [data]
            next_proof(path, [*source_leaves, *data_leaves],
                lambda b, path=path, data=data: b.both(b.inputs[root_q],
                    b.choose(accepted(b), b.net(g, data), b.inputs[q(path)])),
                'root & choose(accepted, actual D cut, held Q)',
                actual_source_data_cut=data, source_data_semantics_proven=False)
    require(len(proofs) == 76, 'receipt reset-inclusive proof inventory incomplete')
    return dict(policy=POLICY, root_register=root_register, root_q=root_q, common_clear=common,
        register_count=76, registers=ff_rows, source_pins=[p + '/Q' for p in payload],
        capture_pins=[p + '/D' for p in local], chains=chains,
        capture_state=capture + '/D', dispatch_state=dispatch + '/D', seen_state=seen + '/D',
        payload_complete_closure=payload_closure, source_ce=source_ce, local_capture_ce=local_ce,
        source_acceptance_condition_cut=None if paired else condition_cut,
        source_event_condition_semantics_proven=paired,
        source_data_semantics_proven=paired, paired_source_abort_lifecycle=paired_lifecycle,
        external_registered_boundaries=boundaries,
        physical_eos_publisher=physical_eos, physical_event_semantics_proven=False,
        merged_ack_register=seen, next_q=proofs, all_reset_inclusive_next_q_proven=True,
        busy_prevents_source_overwrite=True, source_commit_and_toggle_same_CE=True,
        source_payload_stable_while_busy_or_cleared_by_root=True,
        earliest_local_capture_receiving_edge_from_source_toggle=4,
        dispatch_next_q_and_local_capture_same_event_proven=True,
        business_policy_consumption_semantics_proven=False,
        source_binding_owned_by_caller=True, full_tf_cdc_proven=False, physical_tail_proven=False,
        routed_timing_verified=False, physical_recovery_removal_verified=False,
        hardware_tested=False, release_ready=False, deployment_allowed=False)
