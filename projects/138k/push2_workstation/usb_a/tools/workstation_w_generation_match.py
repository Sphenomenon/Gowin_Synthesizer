"""Capture W generation comparisons on the existing held-command edge.

Temporary checked adaptation of the native raw-store owner; retire into that
owner after mapped, CDC and physical checks. No command cycle is introduced.
"""
from pathlib import Path
import hashlib

KEY = 'raw_generation_match_policy'
POLICY = 'task3_W_same_edge_captured_generation_match_v1'
SOURCE = 'rtl/memory/workstation_ble_raw_ddr_store.sv'
TOOL = 'tools/workstation_w_generation_match.py'
PARENT_SHA256 = '1fa0b1189971f89541b71b8940ca2a5c508f6e7e61c9d25ae988fc392c2e5e7f'
EDITS = (
    ('memory_command_generation!=memory_generation_successor', '!memory_next_generation_match', 7),
    ('memory_command_generation!=memory_generation ||', '!memory_current_generation_match ||', 4),
    ('    wire memory_command_start;',
     '    wire memory_command_start;\n    wire memory_next_generation_match,memory_current_generation_match;', 1),
    ('        reg valid;',
     '        reg valid;\n        reg next_generation_match,current_generation_match;\n'
     '        assign memory_next_generation_match=next_generation_match;\n'
     '        assign memory_current_generation_match=current_generation_match;', 1),
    ('valid<=0;payload<=0;fetch_end<=0;',
     'valid<=0;payload<=0;fetch_end<=0;next_generation_match<=0;current_generation_match<=0;', 1),
    ('                if(capture)begin',
     '                if(capture)begin\n'
     '                    next_generation_match<=command_generation==memory_generation_successor;\n'
     '                    current_generation_match<=command_generation==memory_generation;', 1),
    ('    end else begin:g_direct_command',
     '    end else begin:g_direct_command\n'
     '        assign memory_next_generation_match=memory_command_generation==memory_generation_successor;\n'
     '        assign memory_current_generation_match=memory_command_generation==memory_generation;', 1),
)
SELECTED_SHA256 = '8e8a72f1fcb2c8167bd24c1a00d98c5f7ceff88ced2acf18ea4bff697702afae'


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError('W generation match: ' + message)


def configured(configuration):
    value = configuration.get(KEY)
    require(value in (None, POLICY), 'unknown policy')
    if value:
        require(configuration.get('demo_role') == 'W' and
                configuration.get('raw_generation_successor_policy') ==
                'task3_W_registered_generation_successor_v1' and
                configuration.get('raw_fetch_range_policy') ==
                'task3_W_captured_end_parallel_byte_fetch_range_v2',
                'requires explicit W successor and captured-end composition')
    return bool(value)


def adapt(text):
    require(digest(text) == PARENT_SHA256, 'composed parent drift')
    for before, after, count in EDITS:
        require(text.count(before) == count, 'forward anchor drift')
        text = text.replace(before, after)
    require(digest(text) == SELECTED_SHA256, 'selected identity drift')
    return text


def restore(text):
    if 'reg next_generation_match,current_generation_match;' not in text:
        return text
    require(digest(text) == SELECTED_SHA256, 'selected identity drift')
    for before, after, count in reversed(EDITS):
        require(text.count(after) == count, 'inverse anchor drift')
        text = text.replace(after, before)
    require(digest(text) == PARENT_SHA256, 'parent inverse drift')
    return text


def select(stage, configuration):
    if not configured(configuration):
        return None
    path = Path(stage) / SOURCE
    path.write_text(adapt(path.read_text()))
    return evidence(stage, configuration)


def evidence(stage, configuration):
    if not configured(configuration):
        return None
    text = (Path(stage) / SOURCE).read_text()
    require(digest(text) == SELECTED_SHA256 and digest(restore(text)) == PARENT_SHA256,
            'selection absent or inverse drift')
    return dict(policy=POLICY, parent_sha256=PARENT_SHA256,
                selected_sha256=SELECTED_SHA256, added_state_bits=2,
                added_command_cycles=0, capture_edge_unchanged=True,
                direct_command_comparison_retained=True,
                routed_timing_verified=False, hardware_tested=False)


def audit(n):
    """Exact mapped comparison/capture and conditional stability induction.

    Existing raw-command audit proves source hold, request/ACK synchronizers,
    valid next-Q and tuple capture. Here the mapped local generation write
    enable must imply business-start; comparison state is needed only at that
    start. All unrelated inputs stay arbitrary; no DDR/RAM output is assumed.
    """
    from tools.workstation_runtime_pcm_cdc import Graph, BooleanDiagram
    from tools.workstation_task3_native_held import zero_ff
    from tools.workstation_task3_m_session_boundary import frontier, KeyDiagram
    from tools.workstation_task3_w_consumer_nextq import Circuit, Expressions, sat_compare
    import z3
    g = Graph(n)
    scope = 'u_task3_media/raw_store'
    reg = lambda stem: g.register(scope, stem)
    q = lambda p: n.pin(p, 'Q')
    controls = [reg(s) for s in ('command_req_sync', 'completion_ready',
                                'memory_command_active', 'g_command_capture.valid')]
    leaves = list(map(q, controls))
    b = BooleanDiagram(leaves)
    req, ack, active, valid = [b.inputs[x] for x in leaves]
    request = b.both(b.different(req, ack), b.invert(active))
    capture = b.both(request, b.invert(valid))
    start = b.both(request, valid)
    generation = g.group(scope, 'memory_generation', 32)
    successor = g.group(scope, 'memory_generation_successor', 32)
    command = g.group(scope, 'command_generation', 32)
    payload = g.group(scope, 'g_command_capture.payload', 89)[55:87]
    # The packed tuple places generation above the 55 low descriptor bits.
    require(all(n.pin(p, 'D') == q(s) for p, s in zip(payload, command)),
            'captured generation bit order changed')
    write = n.pin(generation[0], 'CE')
    require(all(n.pin(p, 'CE') == write for p in generation),
            'generation write bank changed')
    cuts = sorted(set(leaves + frontier(n, g, [write], set(leaves))))
    k = KeyDiagram(cuts)
    kr, ka, kb, kv = [k.inputs[x] for x in leaves]
    ks = k.both(k.both(k.different(kr, ka), k.invert(kb)), kv)
    require(k.both(k.net(g, write), k.invert(ks)) == 0,
            'generation write can occur outside business-start')
    rows = []
    for stem, operand in (('next_generation_match', successor),
                          ('current_generation_match', generation)):
        p = reg('g_command_capture.' + stem)
        zero_ff(n, g, p, 'memory_clk')
        require(n.pin(p, 'CLEAR') == n.pin(controls[3], 'CLEAR') and
                b.net(g, n.pin(p, 'CE')) == capture,
                'comparison capture/reset event changed')
        e = Expressions()
        c = Circuit(n, e)
        expected = 1
        for a, z in zip(command, operand):
            expected = e.choose(e.xor(c.net(q(a)), c.net(q(z))), 0, expected)
        proof = sat_compare(e, c.net(n.pin(p, 'D')), expected)
        rows.append(dict(register=p, comparison_all32_bits=proof,
                         same_tuple_capture_enable=True, same_valid_reset=True))
    # Reset establishes !valid. Writes require START, which clears valid;
    # CAPTURE and START are disjoint. Prove both comparisons while valid.
    valid, request, reset, write = z3.Bools('valid request reset write')
    gen, succ, payload, incoming, newgen = z3.BitVecs('gen succ payload incoming newgen', 32)
    nm, cm = z3.Bools('next_match current_match')
    start = z3.And(request, valid)
    cap = z3.And(request, z3.Not(valid))
    vn = z3.If(reset, False, z3.If(start, False, z3.If(cap, True, valid)))
    gn = z3.If(reset, 0, z3.If(write, newgen, gen))
    pn = z3.If(reset, 0, z3.If(cap, incoming, payload))
    nn = z3.If(reset, False, z3.If(cap, incoming == succ, nm))
    cn = z3.If(reset, False, z3.If(cap, incoming == gen, cm))
    invariant = z3.Implies(valid, z3.And(nm == (payload == succ), cm == (payload == gen)))
    solver = z3.Solver()
    solver.add(succ == gen + 1, z3.Implies(write, start), invariant,
               z3.Not(z3.Implies(vn, z3.And(nn == (pn == gn + 1), cn == (pn == gn)))))
    result = solver.check()
    require(result == z3.unsat, 'conditional captured comparison invariant failed')
    return dict(policy=POLICY, captured_comparisons=rows,
                generation_write_implies_business_start=True,
                conservative_write_enable_cuts=cuts,
                conditional_comparison_stability_induction=str(result),
                successor_relation_requires_separate_mapped_audit=True,
                source_hold_and_valid_require_separate_raw_capture_audit=True,
                added_command_cycles=0, hardware_tested=False)
