"""Narrow mapped W batch binding; source admission is deliberately separate.

This checks actual registers, exact payload equations, six full-width equality
chains, reply data capture, and local window flush/watermark equations. The
transport check proves bit-specific local data influence with independent
boundary cuts. It does not prove arbitration, the complete batch state machine,
root startup, physical CDC, or hardware functionality. No root auditor is called
here: the root auditor invokes this guard after its own source admission.
"""
from pathlib import Path
import hashlib
import re
import xml.etree.ElementTree as ET

from tools.workstation_runtime_pcm_cdc import BooleanDiagram, COMB, Graph

POLICY = 'task3-w-phone-batch-mapped-local-binding-v1'
PROVIDER = 'rtl/workstation/workstation_profile_task3_w_paired_phone_batch.sv'
E = 'u_task3_bus_endpoint'
B = E + '/g_phone_batch.batch_w'
W = E + '/g_phone_window.window_tx'
BOARD = 'rtl/workstation/workstation_task3_w_paired_board.svh'
CNN_STREAM = 'rtl/music/workstation_task3_cnn_stream_w.sv'
# Exact consumed source identities, independently reviewed for this new path.
# Existing providers/review files are neither replaced nor re-admitted here.
SOURCE_SHA256 = {
    CNN_STREAM: 'ba67f7d71b08d3ccf22a766b79bc1fa312d73c219758b45bac046d687eac94b0',
    'rtl/music/workstation_cnn_task_service.sv': 'f9fd9b1a07bb500dbd45ed49bfca588d28ed8324c89f37ebed3e6e7e328492fa',
    'rtl/music/basic_pitch_workstation_link.sv': '56c78719204d93f18cad2e2906ec7c65c56806c251f6a3b24a2b79c6ad2fa7ca',
    PROVIDER: '74fa5e601734d495e73119fa98d22c4e3143ee34df9486f8426940e0a8212da4',
    'rtl/workstation/workstation_profile_task3_w_paired.sv': 'a13cd5e6285e7d288a7e1eafe2179831dd339be7f8f8d98b243559124d322dac',
    'rtl/workstation/workstation_profile_task3_w_media.sv': '2b18d6349c509ce8227e389618b96dffb58739b3efe9c2b04388a80f585e1920',
    'rtl/workstation/workstation_task3_w_paired_board.svh': '0a58c9de4c8c47ce541918ad0b2b385b61accb7993d54b32eaee2b9a8d264d82',
    'rtl/workstation/workstation_task3_w_bus_endpoint.sv': '6be589f8299ac6b0754833b2269a62691e638cb09b3730607c36dd2dba650ecb',
    'rtl/workstation/workstation_task3_phone_batch_w.sv': '34dca8f4100d86cd4678df09c1345bbf42e3e05f671e1042783edb7072744761',
    'rtl/workstation/workstation_task3_phone_window_tx.sv': 'dad7e5da287f9fea61a962ee9016fdbb2fa280ad99a8b132a9b5b61fab91cdfc',
    'rtl/workstation/task3_paired_channels.vh': 'aa1ec82c2a4a368fabce7e3c75ecbe166433d773ba2793c036946b35e390b73d',
    'rtl/workstation/gw138k_push_workstation_top.v': '3b0bf4be813b7f87a01bba1c5d5253683375714145cbb8dcc770d4035cd374a6',
}
GROUPS = dict(reply=256, request_payload=238, held_data=32,
    completion_data=32, token=32, local_boot=32, peer_boot=32, session=32,
    next_sequence=32, intent_controller=32, intent_generation=32,
    intent_stream=32, last_capture=32, intent_physical=32, intent_sequence=32,
    age=16, held_address=12, intent_frames=8, held_strobes=4, state=3,
    intent_slot=2)
SCALARS = ('held_write', 'completion_error', 'context_valid', 'ever_context',
           'reply_valid', 'fault_o', 'allow_context')
RATE_BITS = (2, 6, 7, 8, 9, 10, 12)


def require(condition, message):
    if not condition:
        raise ValueError('task3 W batch mapped audit: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fault_source_inverse(stage, path):
    """Admit only the exact fault fixes; preserve the historical source seal."""
    text = (stage / path).read_text()
    if path == CNN_STREAM and '.DOMAIN_RESET_RELEASE(1\'b1)' in text:
        from tools.workstation_task3_cnn_reset import inverse, source_evidence
        source_evidence(stage)
        text = inverse(path,text)
    if path == BOARD:
        selected = '''        // Native DDR dispatch fences immediately in its own domain. Its sticky
        // fault withdraws client readiness through ready_control's two flops;
        // do not bypass them with the memory-domain combinational fault cone.
        .record_transport_fault_i(!recording_channel_ready50 || raw_channel_fault),'''
        parent = '        .record_transport_fault_i(!recording_channel_ready50 || raw_channel_fault || task3_memory_transport_fault),'
        require(text.count(selected) == 1, 'recording fault fix anchor changed')
        inverse = text.replace(selected, parent, 1)
    elif path == CNN_STREAM:
        selected = '''    // Native DDR quarantine is immediate in task_service.broker. Only its
    // sticky fault crosses here: cancellation and result publication belong
    // to clk_i and must not consume the native combinational fault cone.
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] transport_fault_control;
    always @(posedge clk_i or negedge reset_ni)
        if(!reset_ni)transport_fault_control<=0;
        else transport_fault_control<={transport_fault_control[0],transport_fault_i};
'''
        new = 'wire live=reset_ni && link_ready_i && !transport_fault_control[1] && !panic_i;'
        old = 'wire live=reset_ni && link_ready_i && !transport_fault_i && !panic_i;'
        require(text.count(selected) == text.count(new) == 1, 'CNN fault fix anchor changed')
        inverse = text.replace(selected, '', 1).replace(new, old, 1)
    else:
        raise ValueError('unreviewed source adaptation: ' + path)
    parent_sha = hashlib.sha256(inverse.encode()).hexdigest()
    require(parent_sha == SOURCE_SHA256[path], 'bytes outside exact fault fix changed: ' + path)
    return dict(path=path, selected_sha256=sha(stage/path), parent_sha256=parent_sha,
                exact_inverse_verified=True, full_CDC_or_root_acceptance=False)


def source_binding(stage):
    stage = Path(stage)
    project = stage / 'Prj1.gprj'
    selected = [row.get('path') for row in ET.parse(project).find('FileList')
                if row.get('enable') == '1']
    providers = [p for p in selected if p and
                 (p.startswith('rtl/workstation/workstation_profile_') or
                  p == 'rtl/workstation/workstation_custom_138k_top.sv')]
    from tools.workstation_task3_w_banked96 import PROVIDER as BANKED96_PROVIDER
    require(providers in ([PROVIDER],[BANKED96_PROVIDER]), 'exact new W provider not uniquely selected')
    banked96=providers==[BANKED96_PROVIDER]
    if banked96:
        from tools.workstation_task3_w_paired_profile import verify_batch_provider
        verify_batch_provider(stage,BANKED96_PROVIDER)
    included = [p for p in SOURCE_SHA256 if 'workstation_profile_' in p or
                p.endswith(('gw138k_push_workstation_top.v', '.svh', '.vh'))]
    require(not any(p in selected for p in included if p != providers[0]),
            'included composition also compiled as a standalone source')
    adaptations = []
    for p in SOURCE_SHA256:
        require((stage/p).is_file(), 'reviewed consumed source missing: ' + p)
        if sha(stage/p) != SOURCE_SHA256[p]:
            if p in ('rtl/music/workstation_cnn_task_service.sv','rtl/music/basic_pitch_workstation_link.sv'):
                from tools.workstation_task3_cnn_reset import source_evidence
                reset = source_evidence(stage)
                adaptations.append(next(row for row in reset['sources'] if row['path']==p))
            else:
                require(p in (BOARD, CNN_STREAM), 'reviewed consumed source changed: ' + p)
                adaptations.append(fault_source_inverse(stage, p))
    for p in ('rtl/workstation/workstation_task3_w_bus_endpoint.sv',
              'rtl/workstation/workstation_task3_phone_batch_w.sv',
              'rtl/workstation/workstation_task3_phone_window_tx.sv', CNN_STREAM):
        require(selected.count(p) == 1, 'required executor source not uniquely compiled: ' + p)
    return dict(selected_provider=providers[0],
                source_sha256={**{p:sha(stage/p) for p in SOURCE_SHA256},
                    **({BANKED96_PROVIDER:sha(stage/BANKED96_PROVIDER)} if banked96 else {}), 'Prj1.gprj': sha(project)},
                fault_source_adaptations=adaptations)


def _local_transport_influence(n, g, register, sources, *, scope=E):
    """Bit-specific LUT influence, with non-data subtrees independent cuts.

    Only combinational cells belonging to the actual endpoint are traversed.
    External control cones and other state are independent boundary inputs.
    Thus this is explicitly a local wiring proof, not a realizable-arbitration
    witness. Every cut and the actual data path are retained in the evidence.
    """
    memo, cuts, used, active = {}, set(), set(), set()

    def walk(net):
        if net in memo:
            return memo[net]
        if net in sources:
            used.add(net)
            memo[net] = True
            return True
        if net in g.high | g.low:
            memo[net] = False
            return False
        require(net not in active, 'transport combinational cycle')
        ds = g.drivers[net]
        # A boundary is always an explicit cut; no Boolean value is invented.
        if len(ds) != 1:
            memo[net] = False
            return False
        path, output = ds[0]
        cell = n.cells[path]
        if n.scopes[path] != scope or path in g.regs or cell['kind'] not in ('INV', 'LUT1', 'LUT2', 'LUT3', 'LUT4', 'LUT5', 'LUT6'):
            memo[net] = False
            return False
        active.add(net)
        inputs = [n.pin(path, p) for p in cell['ports'] if p not in COMB[cell['kind']]]
        dependent = [walk(x) for x in inputs]
        active.remove(net)
        result = any(dependent)
        if result:
            cuts.update(x for x, dep in zip(inputs, dependent) if not dep and x not in g.high | g.low)
        memo[net] = result
        return result

    data = n.pin(register, 'D')
    walk(data)
    require(len(used) == 1, 'transport data path missing or mixes request bits: ' + register)
    target = next(iter(used))
    diagram = BooleanDiagram([target, *sorted(cuts)])
    value = diagram.net(g, data)
    # target is variable zero. Its distinct Shannon cofactors prove a live
    # Boolean dependency, rather than a dead structural path through a LUT.
    require(value > 1 and diagram.nodes[value][0] == 0 and
            diagram.nodes[value][1] != diagram.nodes[value][2],
            'transport request bit is Boolean-dead: ' + register)
    return dict(register=register, source=target, cuts=sorted(cuts),
                bdd_nodes=len(diagram.nodes), bit_specific_local_influence_proven=True)


def audit(n, *, stage):
    source = source_binding(stage)
    fault_proof = None
    if source['fault_source_adaptations']:
        from tools.workstation_task3_w_fault_cdc import audit as audit_fault
        changed = {row['path'] for row in source['fault_source_adaptations']}
        require(BOARD in changed, 'CNN fault fix requires the reviewed recording fault boundary')
        fault_proof = audit_fault(n, cnn_control=CNN_STREAM in changed)
    require(n.frames.get('', {}).get('kind') == 'workstation_custom_138k_top', 'wrong mapped top')
    require([p for p, c in n.frames.items() if c['kind'] == 'workstation_task3_phone_batch_w'] == [B],
            'actual batch W executor missing/duplicate')
    require(n.frames.get(E, {}).get('kind') == 'workstation_task3_w_bus_endpoint' and
            n.frames.get(W, {}).get('kind') == 'workstation_task3_phone_window_tx',
            'actual paired endpoint/window missing')
    g = Graph(n)
    regs = {stem: g.group(B, stem, width) for stem, width in GROUPS.items()}
    regs.update({stem: g.group(B, stem) for stem in SCALARS})
    regs['intent_rate'] = [g.register(B, 'intent_rate', bit) for bit in RATE_BITS]
    inventory = {p for row in regs.values() for p in row}
    require({p for p in g.regs if n.scopes[p] == B} == inventory,
            'batch register inventory changed')
    root_q = n.pin(g.register('u_reset', 'started'), 'Q')
    require(root_q == n.canonical('', 'reset_n'), 'batch root positive publisher disconnected')
    clear = n.pin(regs['state'][0], 'CLEAR')
    checked = inventory | {p for p in g.regs if n.scopes[p] == W}
    preset = {regs['allow_context'][0], *(g.register(B,'intent_rate',bit) for bit in (7,8,9,12))}
    def check_ff(p, kind, pin):
        cell = n.cells[p]
        expected_init = "1'b1" if kind == 'DFFPE' else "1'b0"
        require(cell['kind'] == kind and
                set(cell['ports']) == {'Q','D','CLK','CE',pin} and
                set(cell['parameters']) <= {'INIT'} and
                cell['parameters'].get('INIT', "1'b0") == expected_init,
                'actual register primitive/INIT/port inventory changed: ' + p)
        require(n.pin(p,'Q') not in g.high | g.low and
                g.drivers[n.pin(p,'Q')] == [(p,'Q')],
                'actual register Q constant or ambiguous: ' + p)
        require(n.pin(p,'CLK') == n.canonical('','clk_50m') and
                n.pin(p,pin) == clear, 'actual executor/window clock/reset changed: ' + p)
    for p in checked:
        kind, pin = ('DFFPE','PRESET') if p in preset else ('DFFCE','CLEAR')
        check_ff(p,kind,pin)
    require(len({n.pin(p,'Q') for p in checked}) == len(checked),
            'actual batch/window state Qs aliased')
    proofs = [g.equivalent('common asynchronous clear is inverse of positive root',
                           [clear, root_q], lambda v: v[0] == 1-v[1], cuts={root_q})]
    q = lambda stem, bit=0: n.pin(regs[stem][bit], 'Q')
    local = lambda tail: n.canonical(B, tail)
    endpoint = lambda tail: n.canonical(E, tail)
    window = lambda tail: n.canonical(W, tail)
    key_ce = n.pin(regs['token'][0], 'CE')
    key_comparisons = []
    for stem, input_name, carry in (
            ('token', 'task3_pair_generation', 'n44_3'),
            ('local_boot', 'task3_pair_local_boot', 'n77_3'),
            ('peer_boot', 'task3_pair_peer_boot', 'n111_3'),
            ('session', 'task3_pair_session', 'n145_3')):
        for bit, p in enumerate(regs[stem]):
            require(n.pin(p, 'D') == n.canonical('', input_name + f'[{bit}]') and
                    n.pin(p, 'CE') == key_ce, 'full key capture disconnected: ' + p)
        actual = g.inequality_chain(local(carry))
        wanted = {frozenset((q(stem, bit), n.canonical('', input_name + f'[{bit}]'))) for bit in range(32)}
        require(actual == wanted, 'full key comparison operands changed: ' + stem)
        key_comparisons.append(local(carry))
    same = endpoint('n737_9')
    proofs.append(g.equivalent('full key equality includes all four stored words',
        [same, *key_comparisons], lambda v: v[0] == int(not any(v[1:])), cuts=set(key_comparisons)))
    active = endpoint('n10383_32')
    qual, live = endpoint('n737_12'), n.canonical('', 'live')
    active_inputs = [active, root_q, live, qual, endpoint('phone_proxy_armed'),
        endpoint('phone_proxy_fault'), q('context_valid'), q('fault_o'), *key_comparisons]
    proofs.append(g.equivalent('mapped batch active rejects every full-key mismatch', active_inputs,
        lambda v: v[0] == int(all(v[1:5]) and not v[5] and v[6] and not v[7] and not any(v[8:])),
        cuts={root_q, live, qual, *key_comparisons}))
    payload = regs['request_payload']
    payload_ce = n.pin(payload[0], 'CE')
    require(payload_ce not in g.high | g.low and
            all(n.pin(p, 'CE') == payload_ce for p in payload), 'request shared capture enable changed')
    require(set(key_comparisons) <= g.carry_frontier(payload_ce),
            'request capture lost a full-key comparator')
    for word, stem in enumerate(('token', 'next_sequence', 'intent_controller',
                                'intent_generation', 'intent_stream', 'intent_physical')):
        for bit in range(32):
            require(n.pin(payload[word*32+bit], 'D') == q(stem, bit),
                    'request word data binding changed: ' + stem)
    command = [endpoint(f'mux_data[{bit}]') for bit in range(32)]
    for bit in range(224, 227):
        require(n.pin(payload[bit], 'D') == command[bit-224], 'request opcode data disconnected')
    bdd_checks = 0
    for lo, count, stem in ((192,32,'intent_sequence'), (228,2,'intent_slot'), (230,8,'intent_frames')):
        for bit in range(count):
            data = n.pin(payload[lo+bit], 'D')
            inputs = [*command, q(stem, bit)]
            diagram = BooleanDiagram(inputs)
            is_two = diagram.all(diagram.inputs[x] if j == 1 else diagram.invert(diagram.inputs[x]) for j,x in enumerate(command))
            require(diagram.net(g, data) == diagram.both(is_two, diagram.inputs[q(stem,bit)]),
                    'request conditional intent data changed: ' + str(lo+bit))
            bdd_checks += 1
    rate = {bit:n.pin(p,'Q') for bit,p in zip(RATE_BITS, regs['intent_rate'])}
    diagram = BooleanDiagram(list(rate.values()))
    wanted = diagram.all(diagram.inputs[net] if (44100 >> bit)&1 else diagram.invert(diagram.inputs[net]) for bit,net in rate.items())
    require(diagram.net(g,n.pin(payload[227],'D')) == wanted, 'request 44k1 rate flag changed')
    # These exact two reply tag chains must feed the actual reply next-Q cone.
    for carry, left, right in (
            ('n304_3', [n.canonical('',f'task3_pair_rx_payload[{i}]') for i in range(32)], [q('token',i) for i in range(32)]),
            ('n338_3', [n.canonical('',f'task3_pair_rx_payload[{i+32}]') for i in range(32)], [n.pin(payload[i+32],'Q') for i in range(32)])):
        require(g.inequality_chain(local(carry)) == {frozenset(pair) for pair in zip(left,right)},
                'reply token/sequence comparison operands changed: ' + carry)
    reply_frontier = g.carry_frontier(n.pin(regs['reply'][0], 'D'))
    require({*key_comparisons, local('n304_3'), local('n338_3')} <= reply_frontier,
            'actual reply path lost full-key/token/sequence guards')
    # Exact per-bit next-Q data equation with the same four explicit control
    # cuts. Those control functions are not abstracted into an acceptance claim.
    load, mask, keep, read = [local(x) for x in ('n737_4','n12043_24','n12043_11','n12043_12')]
    s1,s2 = q('state',1),q('state',2)
    reply_proofs = []
    for bit,p in enumerate(regs['reply']):
        incoming = n.canonical('',f'task3_pair_rx_payload[{bit}]')
        netq = n.pin(p,'Q')
        nets = [n.pin(p,'D'),netq,incoming,load,mask,keep,read,s1,s2]
        reply_proofs.append(g.equivalent('reply data bit '+str(bit), nets,
            lambda v: v[0] == (v[5] and ((not v[3] and v[1]) if v[4] else
                                         ((not v[7] and v[2]) if v[8] else (v[1] and v[6])))),
            cuts={netq,incoming,load,mask,keep,read,s1,s2}))
        require(n.pin(p,'CE') in g.high, 'reply next-Q enable changed')
    # The watermark includes the real unacknowledged flight, not just local
    # posted capacity. Prove its actual consumption by the batch FLUSH gate.
    count = [n.pin(p,'Q') for p in g.group(W,'building_count',3)]
    flight = [n.pin(p,'Q') for p in g.group(W,'flight',2)]
    held = n.pin(g.register(W,'held'),'Q')
    empty = endpoint('n890_20')
    proofs.append(g.equivalent('window empty includes actual unacknowledged flight',
        [empty,*count,*flight],lambda v:v[0] == int(not any(v[1:]))))
    flush_to_send = local('n12046_11')
    proofs.append(g.equivalent('batch flush transition waits for held/building/flight watermark',
        [flush_to_send,q('state'),held,active,empty],
        lambda v:v[0] == int(not v[1] and not v[2] and v[3] and v[4]), cuts={active}))
    watermark_state = _local_transport_influence(n,g,regs['state'][0],{flush_to_send},scope=B)
    flush = window('n10383_6')
    other = window('n10383_8')
    s0 = q('state')
    proofs.append(g.equivalent('active pending batch externally flushes nonempty idle window',
        [flush,active,other,s0,s1,s2,*count,*flight],
        lambda v:v[0] == int(any(v[6:9]) and not any(v[9:]) and
                            (not v[2] or (v[1] and ((v[3]+2*v[4]+4*v[5]) in (2,3,4))))),
        cuts={active,other}))
    flight_d = n.pin(g.register(W,'flight',0),'D')
    gate = window('n890_24')
    old_flight = window('n5090_8')
    timer = n.canonical('', 'partial_timer_31_9')
    if g.drivers[old_flight]:
        flight_mapping = 'separate_old_flight_gate'
        proofs.append(g.equivalent('external flush gate drives actual window flight register',
            [flight_d,old_flight,timer,flush,gate],
            lambda v:v[0] == int(v[4] and (v[1] or (v[2] and v[3]))),
            cuts={old_flight,timer,flush,gate}))
    else:
        # The exact fault fixes permit Gowin to absorb old_flight into the
        # final LUT. Retain the real flight Q and inhibit net as independent
        # inputs; prove the actual next-D function, never cut an absent net.
        require(source['fault_source_adaptations'], 'unreviewed merged flight mapping')
        inhibit = window('n5090_10')
        flight_q = n.pin(g.register(W,'flight',0),'Q')
        require(len(g.drivers[inhibit]) == 1 and len(g.drivers[gate]) == 1,
                'merged flight actual gate missing/ambiguous')
        flight_mapping = 'merged_old_flight_gate'
        proofs.append(g.equivalent('merged external flush drives actual flight D',
            [flight_d,flight_q,inhibit,timer,flush,gate],
            lambda v:v[0] == int(v[5] and ((v[1] and not v[2]) or (v[3] and v[4]))),
            cuts={inhibit,timer,flush,gate}))
    tx = g.group(E,'tx_payload_o',256)
    for bit,p in enumerate(tx):
        check_ff(p,'DFFCE','CLEAR')
        require(n.pin(p,'Q')==n.canonical('',f'task3_pair_tx_payload[{bit}]'),
                'actual transport payload register binding changed: ' + p)
    sources = {n.pin(p,'Q') for p in payload}
    transport = [_local_transport_influence(n,g,tx[bit],sources) for bit in range(238)]
    require(all(row['source']==n.pin(payload[bit],'Q') for bit,row in enumerate(transport)),
            'request payload bit transport permutation')
    return dict(policy=POLICY, **source, fault_control_boundaries=fault_proof, actual_executor=B, actual_window=W,
        actual_batch_state_bits=len(inventory), checked_clock_reset_registers=len(checked),
        checked_transport_registers=len(tx), register_init_and_port_inventory_verified=True,
        root_q=root_q, root_startup_proven_here=False,
        request_payload_bits=238, request_conditional_bdd_checks=bdd_checks+1,
        declared_request_bus_width=256, high_padding_zero_proven=False,
        key_stored_bits=128, generation_and_token_share_actual_input=True,
        key_comparison_bits=128, reply_tag_comparison_bits=64,
        local_equations=proofs, watermark_actual_state_influence=watermark_state,
        window_flight_mapping=flight_mapping,
        reply_data_bit_equations=reply_proofs,
        transport_data_influence=transport,
        transport_check_scope='bit-specific local Boolean influence with independent non-data boundary cuts; arbitration not proven',
        complete_state_machine_proven=False, response_acceptance_function_proven=False,
        full_protocol_functionality_proven=False, physical_cdc_accepted=False,
        routed_timing_verified=False, hardware_tested=False, deployment_allowed=False)
