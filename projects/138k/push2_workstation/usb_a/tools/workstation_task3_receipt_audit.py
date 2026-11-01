"""DIRECT receipt mailbox: actual held/local boundary and exact next-Q.

The source event-condition and per-bit source data are explicit cuts, not a
proof of physical-tail event/data semantics.  No source selection, candidate,
SDC, EDA or board operation is performed. Full TF CDC remains a separate gate.
"""
import re

from tools.workstation_recording_phase1_cdc import complete_closure
from tools.workstation_runtime_pcm_cdc import BooleanDiagram, Graph
from tools.workstation_task3_root_reset_audit import (
    POLICY as ROOT_POLICY, ROOT_SOURCE, ROOT_SOURCE_SHA256)

POLICY = 'task3-direct-receipt-local-mailbox-v1'
SCOPE = 'u_tf_audio'
TAIL = 'u_managed/runtime/g_direct_tf.tail'


def require(condition, message):
    if not condition:
        raise ValueError('task3 receipt audit: ' + message)


def audit_direct_receipt(n, *, root):
    g = Graph(n)
    require(root.get('policy') == ROOT_POLICY and root.get('all_state_assignments_proven') is True
            and root.get('actual_state_bits') == 35 and
            root.get('source_sha256', {}).get(ROOT_SOURCE) == ROOT_SOURCE_SHA256,
            'verified task3 real-root startup proof required')
    root_register = g.register('u_reset', 'started')
    root_q = n.pin(root_register, 'Q')
    require(root.get('root_register') == root_register and root.get('root_q') == root_q
            and n.canonical('', 'reset_n') == root_q,
            'root proof not bound to actual common assertion')
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
        source_acceptance_condition_cut=condition_cut, source_event_condition_semantics_proven=False,
        source_data_semantics_proven=False, external_registered_boundaries=boundaries,
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
