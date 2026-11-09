"""W same-edge raw-store generation successor; exact checked staging adapter.

Retire into the native raw-store owner after source and mapped invariant checks.
No transaction stage or generation-overflow acceptance rule is added.
"""
from pathlib import Path
import hashlib

KEY = 'raw_generation_successor_policy'
POLICY = 'task3_W_registered_generation_successor_v1'
SOURCE = 'rtl/memory/workstation_ble_raw_ddr_store.sv'
TOOL = 'tools/workstation_w_generation_successor.py'
PARENT_SHA256 = '78b9e102c47e72f3c2675e99ce74ce2b826171c6239fe233f5ded9e037772f96'
SELECTED_SHA256 = '1fa0b1189971f89541b71b8940ca2a5c508f6e7e61c9d25ae988fc392c2e5e7f'
EDITS = (
    ('    wire [1:0] memory_command_kind;',
     '    reg [31:0] memory_generation_successor;\n    wire [1:0] memory_command_kind;', 1),
    ("memory_generation+1'b1", 'memory_generation_successor', 7),
    ('memory_generation<=0;', "memory_generation<=0;memory_generation_successor<=32'd1;", 1),
    ('memory_generation<=memory_command_generation;',
     "memory_generation<=memory_command_generation;memory_generation_successor<=memory_command_generation+1'b1;", 2),
)


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError('W generation successor: ' + message)


def configured(configuration):
    value = configuration.get(KEY)
    require(value in (None, POLICY), 'unknown policy')
    if value:
        require(configuration.get('demo_role') == 'W' and
                configuration.get('raw_fetch_range_policy') ==
                'task3_W_captured_end_parallel_byte_fetch_range_v2',
                'requires W captured-end raw composition')
    return bool(value)


def restore(text):
    if 'reg [31:0] memory_generation_successor;' not in text:
        return text
    require(digest(text) == SELECTED_SHA256, 'selected identity drift')
    # Remove declarations and writes before replacing the seven expression
    # identifiers; the declaration itself contains the same identifier.
    for before, after, count in (EDITS[0], EDITS[3], EDITS[2], EDITS[1]):
        require(text.count(after) == count, 'inverse anchor drift')
        text = text.replace(after, before)
    require(digest(text) == PARENT_SHA256, 'parent inverse drift')
    return text


def select(stage, configuration):
    if not configured(configuration):
        return None
    path = Path(stage) / SOURCE
    text = path.read_text()
    require(digest(text) == PARENT_SHA256, 'composed parent drift')
    for before, after, count in EDITS:
        require(text.count(before) == count, 'forward anchor drift')
        text = text.replace(before, after)
    require(digest(text) == SELECTED_SHA256, 'selected identity drift')
    path.write_text(text)
    return evidence(stage, configuration)


def evidence(stage, configuration):
    if not configured(configuration):
        return None
    text = (Path(stage) / SOURCE).read_text()
    require(digest(text) == SELECTED_SHA256, 'successor selection absent')
    restore(text)
    return dict(policy=POLICY, parent_sha256=PARENT_SHA256,
                selected_sha256=SELECTED_SHA256, added_state_bits=32,
                invariant='successor == generation + 1 modulo 2^32',
                added_cycles=0, overflow_rejection_unchanged=True,
                routed_timing_verified=False, hardware_tested=False)


def audit(n):
    from tools.workstation_task3_w_consumer_nextq import Circuit, Expressions, sat_compare
    e = Expressions()
    c = Circuit(n, e)
    scope = 'u_task3_media/raw_store'
    old = c.g.group(scope, 'memory_generation', 32)
    new = c.g.group(scope, 'memory_generation_successor', 32)
    # Identical physical CE/reset pins are arbitrary independent Booleans.
    # Prove the banks for either value; no DDR controller value is assumed.
    enable = n.pin(old[0], 'CE')
    assertion = n.pin(old[0], 'CLEAR')
    require(all(n.pin(p, 'CE') == enable for p in old + new[1:]),
            'common write enable changed')
    require(n.pin(new[0], 'CE') in c.g.high, 'folded bit0 enable changed')
    require(all(n.pin(p, 'CLEAR') == assertion for p in old + new[1:]) and
            n.pin(new[0], 'PRESET') == assertion, 'common reset assertion changed')
    c.memo[enable] = e.node('state', 'same_actual_write_enable:' + enable)
    c.memo[assertion] = e.node('state', 'same_actual_reset_assertion:' + assertion)
    for i, (a, b) in enumerate(zip(old, new)):
        require(n.pin(a, 'CLK') == n.pin(b, 'CLK') == 'memory_clk', 'clock changed')
        aa, ai, ac = c.next_q(a)
        bb, bi, bc = c.next_q(b)
        require(ai == "1'b0" and bi == "1'b" + str(int(i == 0)), 'INIT relation changed')

    def relation(a, b):
        carry, equal = 1, 1
        for x, y in zip(a, b):
            equal = e.choose(e.xor(e.xor(x, carry), y), 0, equal)
            carry = e.choose(x, carry, 0)
        return equal

    now = relation([c.net(n.pin(p, 'Q')) for p in old],
                   [c.net(n.pin(p, 'Q')) for p in new])
    after = relation([c.next_q(p)[0] for p in old],
                     [c.next_q(p)[0] for p in new])
    proof = sat_compare(e, e.choose(now, after, 1), 1)
    return dict(policy=POLICY, invariant_induction=proof, INIT_relation=True,
                reset_included_in_transition=True, generation_bits=32,
                common_actual_write_enable=enable,
                common_actual_reset_assertion=assertion,
                common_controls_independent_and_arbitrary=True,
                actual_data_and_folded_bit0_enable_fully_expanded=True,
                added_cycles=0, hardware_tested=False)
