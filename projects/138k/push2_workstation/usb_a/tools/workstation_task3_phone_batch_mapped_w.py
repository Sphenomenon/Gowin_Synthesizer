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
        require(all((stage/p).is_file() for p in (BANKED96_PROVIDER, *SOURCE_SHA256)),
                'required banked96 composition source missing')
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
            elif p == 'rtl/workstation/workstation_task3_w_bus_endpoint.sv':
                from tools.workstation_w_context_compare import normalize
                normalized = normalize((stage/p).read_bytes())
                require(hashlib.sha256(normalized).hexdigest() == SOURCE_SHA256[p],
                        'W full-key comparison parent changed')
                adaptations.append(dict(path=p, selected_sha256=sha(stage/p),
                    parent_sha256=SOURCE_SHA256[p], exact_inverse_verified=True,
                    comparison_bits=128, extra_cycles=0))
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
    # Generated intermediate names move when unused W USB is retired. Admit
    # this mapping only through the explicit retired-USB source policy; every
    # selected node below still has to satisfy its actual Boolean equation.
    from tools.workstation_task3_w_usb_retirement import audit_absence
    selected_paths = [row.get('path') for row in ET.parse(Path(stage)/'Prj1.gprj').find('FileList')
                      if row.get('enable') == '1']
    retired_usb = 'rtl/workstation/workstation_task3_w_usb_retired.sv' in selected_paths
    usb_absence = audit_absence(n) if retired_usb else None
    import json
    configuration=json.loads((Path(stage).parents[1]/'workstation_profile.json').read_text())['configuration']
    from tools.workstation_effects_reserved_config import W_POLICY,evidence as dispatch_evidence
    reserved_dispatch=configuration.get('effects_dispatch_policy')==W_POLICY
    if reserved_dispatch:
        # The selected effects implementation moves this mapped intermediate
        # to an enclosing port. The four full-width operand chains and exact
        # all-four equality equation remain mandatory below.
        dispatch_evidence(stage,configuration)
        require(retired_usb,'reserved W dispatch requires retired unused USB')
    same = endpoint('n737_13') if reserved_dispatch else local('n737_10') if retired_usb else endpoint('n737_9')
    if reserved_dispatch:
        candidates={n.pin(p,'F')for p,c in n.cells.items()if n.scopes[p]in (E,B) and c['kind']=='LUT4' and
            c['parameters'].get('INIT')=="16'h0001" and
            {n.pin(p,'I'+str(i))for i in range(4)}==set(key_comparisons)}
        require(len(candidates)==1,'unique exact all-four key equality output absent')
        same=next(iter(candidates))
    proofs.append(g.equivalent('full key equality includes all four stored words',
        [same, *key_comparisons], lambda v: v[0] == int(not any(v[1:])), cuts=set(key_comparisons)))
    from tools.workstation_w_context_compare import SOURCE as context_source, SELECTED_SHA256 as grouped_sha, ARM_CAPTURE_SHA256
    arm_capture = sha(Path(stage)/context_source) == ARM_CAPTURE_SHA256
    grouped_context = sha(Path(stage)/context_source) in (grouped_sha,ARM_CAPTURE_SHA256)
    active = window('n10383_7') if grouped_context else endpoint('n10383_7') if retired_usb else endpoint('n10383_32')
    qual = local('n737_18') if retired_usb else endpoint('n737_12')
    live = endpoint('live') if retired_usb else n.canonical('', 'live')
    if grouped_context:
        from tools.workstation_w_context_compare import audit_mapped as audit_context
        proofs.append(audit_context(n,g))
        live_parts = [endpoint(x) for x in ('live_6', 'live_7', 'live_5')]
        qual = endpoint('phone_arm_attempt_21')
        proofs.append(g.equivalent('grouped endpoint live is actual three-factor conjunction',
            [live, *live_parts], lambda v:v[0] == int(all(v[1:])), cuts=set(live_parts)))
        if reserved_dispatch:
            # This implementation absorbs the old qualification intermediate.
            # Prove its expanded equation, including the real HCI readiness
            # and window fault, rather than cutting an absent numeric alias.
            command_release=n.pin(g.register('u_task3_pair_link/config_cdc','a_release',2),'Q')
            require(command_release==n.canonical('','command_reset_n'),
                    'expanded qualification command-release publisher changed')
            positive=[*live_parts,command_release,n.canonical('','clock_command_reset_n'),
                n.canonical('','hci_pcm_session_ready'),endpoint('media_cap_ready'),
                endpoint('phone_proxy_armed'),q('context_valid')]
            # Both legal physical forms retain the exact context FF above:
            # either root is an explicit LUT input, or synthesis absorbs it
            # into context_valid's checked, root-owned asynchronous CLEAR.
            # Compare both complete equations; never choose an arbitrary cut.
            negative=[endpoint('media_cap_fault'),endpoint('phone_window_fault'),
                endpoint('phone_proxy_fault'),q('fault_o'),*key_comparisons]
            leaves=list(dict.fromkeys(positive+negative));bd=BooleanDiagram(leaves)
            expected=bd.all([*(bd.inputs[x]for x in positive),
                             *(bd.invert(bd.inputs[x])for x in negative)])
            # Synthesis may move/rename this conjunction. Find its actual
            # output from the reviewed leaves, then prove the same equation.
            # No generated name or unverified Boolean cut selects the result.
            pending=[q('context_valid')];reachable=set();seen=set()
            while pending:
                net=pending.pop()
                if net in seen:continue
                seen.add(net)
                for cell,pin,role in g.fan[net]:
                    if role=='comb' and n.scopes[cell]in (E,B,W) and n.cells[cell]['kind'].startswith('LUT'):
                        out=n.pin(cell,'F')
                        if out not in reachable:reachable.add(out);pending.append(out)
            support_memo={net:{net}for net in leaves}
            def reviewed_support(net):
                if net in support_memo:return support_memo[net]
                if net in g.high|g.low:return set()
                drivers=g.drivers[net]
                if len(drivers)!=1:return None
                cell,port=drivers[0];kind=n.cells[cell]['kind']
                if kind=='INV':pins=['I']
                elif re.fullmatch('LUT[1-6]',kind):pins=['I'+str(i)for i in range(int(kind[3:]))]
                else:return None
                parts=[reviewed_support(n.pin(cell,p))for p in pins]
                support_memo[net]=None if any(p is None for p in parts)else set().union(*parts)
                return support_memo[net]
            candidates=[]
            for explicit_root in (True, False):
                inputs=[*leaves,root_q] if explicit_root else leaves
                diagram=BooleanDiagram(inputs)
                wanted=diagram.all([*(diagram.inputs[x] for x in positive),
                    *(diagram.invert(diagram.inputs[x]) for x in negative),
                    *([diagram.inputs[root_q]] if explicit_root else [])])
                for out in sorted(reachable):
                    # root is a reviewed leaf even in the absorbed form; it
                    # must not disappear through an unsupported driver.
                    support_memo[root_q]={root_q}
                    if reviewed_support(out)==set(inputs) and diagram.net(g,out)==wanted:
                        candidates.append((out,explicit_root,diagram,wanted,inputs))
            require(len(candidates)==1,'unique expanded reserved-dispatch active qualification absent')
            active,explicit_root,bd,expected,leaves=candidates[0]
            invariant=BooleanDiagram(list(dict.fromkeys([*leaves,root_q])))
            settled=invariant.either(invariant.invert(invariant.inputs[q('context_valid')]),
                                      invariant.inputs[root_q])
            actual=invariant.net(g,active)
            gated=invariant.both(invariant.inputs[root_q],actual)
            require(invariant.both(settled,actual)==invariant.both(settled,gated),
                    'settled context reset invariant does not preserve active root guard')
            proofs.append(dict(contract='reserved dispatch expanded active qualification',
                positive_inputs=positive+([root_q] if explicit_root else []),negative_inputs=negative,
                independent_inputs=leaves,all_assignments_proven=True,
                Boolean_assignments=1<<len(leaves),BDD_nodes=len(bd.nodes),
                explicit_combinational_root_required=explicit_root,
                actual_qualification_net=active,
                raw_root_assertion_checked_by_actual_FF_CLEAR=True,
                reset_absorbed_in_context_CLEAR=not explicit_root,
                context_register=regs['context_valid'][0],context_clear=clear,
                settled_context_implies_root=True,
                settled_reset_invariant_equivalence_proven=True,
                reset_scope='After asynchronous CLEAR has settled; no analog reset propagation or recovery/removal claim.',
                absent_intermediate_cut_used=False))
        else:
            active_inputs = [active, *live_parts, root_q, qual, endpoint('phone_proxy_armed'),
                endpoint('phone_proxy_fault'), q('context_valid'), q('fault_o'), *key_comparisons]
            proofs.append(g.equivalent('grouped mapped batch active retains root and every full-key guard',
                active_inputs, lambda v:v[0] == int(all(v[1:7]) and not v[7] and v[8] and not v[9] and not any(v[10:])),
                cuts={*live_parts, root_q, qual, *key_comparisons}))
    elif retired_usb:
        # Reset is implemented by the checked asynchronous CLEAR of
        # context_valid, not an additional combinational root input. Do not
        # claim a Boolean root gate absent from this actual implementation.
        live_parts = [endpoint('live_53'), endpoint('live_5')]
        proofs.append(g.equivalent('endpoint live is actual factored conjunction',
            [live, *live_parts], lambda v:v[0] == int(v[1] and v[2]), cuts=set(live_parts)))
        active_inputs = [active, *live_parts, qual, endpoint('phone_proxy_armed'),
            endpoint('phone_proxy_fault'), q('context_valid'), q('fault_o'), *key_comparisons]
        proofs.append(g.equivalent('mapped batch active rejects every full-key mismatch', active_inputs,
            lambda v:v[0] == int(all(v[1:5]) and not v[5] and v[6] and not v[7] and not any(v[8:])),
            cuts={*live_parts, qual, *key_comparisons}))
    else:
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
    load, mask, keep, read = [local(x) for x in
        ('n737_4', 'n12043_41' if reserved_dispatch else 'n12043_44' if grouped_context else 'n12043_28' if retired_usb else 'n12043_24', 'n12043_11','n12043_12')]
    if reserved_dispatch:
        reply_driver=g.drivers[n.pin(regs['reply'][0],'D')]
        require(len(reply_driver)==1,'reply mux driver absent/ambiguous')
        reply_cell,reply_port=reply_driver[0]
        require(n.cells[reply_cell]['kind']=='LUT4' and reply_port=='F' and
                n.cells[reply_cell]['parameters'].get('INIT')=="16'hC500",
                'reserved reply top mux truth table changed')
        mask,keep=n.pin(reply_cell,'I2'),n.pin(reply_cell,'I3')
    load_cuts = {local(x) for x in ('n737_5','n737_20','n737_7')} if grouped_context else {load}
    if reserved_dispatch:
        load_drivers=g.drivers[load]
        require(len(load_drivers)==1,'reserved load driver absent/ambiguous')
        load_cell,load_port=load_drivers[0]
        load_table=n.cells[load_cell]['parameters'].get('INIT')
        # ARM source identity does not determine optimizer factoring. The
        # byte-header rebuild uses the original 7000/EA00 equations again;
        # select only these independently checked actual primitive forms.
        require(n.cells[load_cell]['kind']=='LUT4' and load_port=='F' and
                load_table in (("16'hF700","16'h7000") if arm_capture else ("16'h7000",)),
                'reserved load truth table changed')
        load_arm_factored=load_table=="16'hF700"
        # Preserve the four actual control cuts. New integration can rename
        # synthesized intermediates without changing this exact equation.
        load_terms=[n.pin(load_cell,'I'+str(i))for i in range(4)]
        require(len(set(load_terms))==4,'reserved load control cuts alias')
        load_cuts=set(load_terms)
        # ARM capture changes the factored load cone, while leaving these
        # four independent, explicitly unproved control boundaries. Keep
        # the per-bit reply equation below tied to this actual load output.
        proofs.append(g.equivalent('reserved dispatch actual factored load retains exact LUT equation',
            [load,*load_terms],lambda v:v[0]==int(v[4] and
                ((v[3] or not(v[1] and v[2])) if load_arm_factored else
                 (v[3] and not(v[1] and v[2])))),cuts=load_cuts))
    elif grouped_context:
        load_terms = [local(x) for x in ('n737_5','n737_20','n737_7')]
        proofs.append(g.equivalent('actual factored load retains exact LUT equation',
            [load,*load_terms],lambda v:v[0]==int(not v[1] and v[2] and v[3]),cuts=set(load_terms)))
    s1,s2 = q('state',1),q('state',2)
    reply_proofs = []
    for bit,p in enumerate(regs['reply']):
        incoming = n.canonical('',f'task3_pair_rx_payload[{bit}]')
        netq = n.pin(p,'Q')
        cuts={netq,incoming,*load_cuts,mask,keep,read,s1,s2}
        leaves=sorted(cuts);bd=BooleanDiagram(leaves);v=bd.inputs
        # The same exhaustive Boolean contract as the old truth-table loop.
        # Canonical BDD equality avoids re-evaluating each recursive LUT cone
        # thousands of times per bit; no additional control cut is admitted.
        expected=bd.both(v[keep],bd.choose(v[mask],
            bd.both(bd.invert(bd.net(g,load)),v[netq]),
            bd.choose(v[s2],bd.both(bd.invert(v[s1]),v[incoming]),
                      bd.both(v[netq],v[read]))))
        require(bd.net(g,n.pin(p,'D'))==expected,'reply data bit equation changed: '+str(bit))
        reply_proofs.append(dict(contract='reply data bit '+str(bit),support=leaves,
            cuts=leaves,exhaustive_assignments=1<<len(leaves),BDD_nodes=len(bd.nodes),
            all_assignments_proven=True))
        require(n.pin(p,'CE') in g.high, 'reply next-Q enable changed')
    # The watermark includes the real unacknowledged flight, not just local
    # posted capacity. Prove its actual consumption by the batch FLUSH gate.
    count = [n.pin(p,'Q') for p in g.group(W,'building_count',3)]
    flight = [n.pin(p,'Q') for p in g.group(W,'flight',2)]
    held = n.pin(g.register(W,'held'),'Q')
    empty = endpoint('n890_16') if reserved_dispatch else endpoint('n890_18') if retired_usb else endpoint('n890_20')
    if reserved_dispatch:
        leaves=[*count,*flight];bd=BooleanDiagram(leaves)
        expected=bd.invert(bd.either(bd.either(bd.inputs[count[0]],bd.inputs[count[1]]),
            bd.either(bd.inputs[count[2]],bd.either(bd.inputs[flight[0]],bd.inputs[flight[1]]))))
        matches=set()
        for path,cell in n.cells.items():
            if not path.startswith(E+'/') or not path.rsplit('/',1)[-1].startswith('n890_') or cell['kind']not in COMB:continue
            for port in COMB[cell['kind']]:
                net=n.pin(path,port)
                try:
                    if bd.net(g,net)==expected:matches.add(net)
                except ValueError:pass
        require(len(matches)==1,'window empty exact five-bit implementation absent/ambiguous')
        empty=next(iter(matches))

    proofs.append(g.equivalent('window empty includes actual unacknowledged flight',
        [empty,*count,*flight],lambda v:v[0] == int(not any(v[1:]))))
    flush_to_send = local('n12046_12') if retired_usb else local('n12046_11')
    if retired_usb:
        # The shared watermark gate is factored before the state/active
        # selection in this mapping, rather than including them in one LUT.
        proofs.append(g.equivalent('batch watermark requires no held/building/flight work',
            [flush_to_send,held,empty], lambda v:v[0] == int(not v[1] and v[2])))
    else:
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
    gate = window('n890_22') if reserved_dispatch else window('n890_24')
    if reserved_dispatch:
        drivers=g.drivers[flight_d]
        require(len(drivers)==1,'actual window flight D driver absent/ambiguous')
        path,port=drivers[0]
        flight_table=n.cells[path]['parameters'].get('INIT')
        require(n.cells[path]['kind']=='LUT4' and port=='F' and
                flight_table in (("16'hF400","16'hEA00") if arm_capture else ("16'hEA00",)),
                'actual window flight D truth table changed')
        flight_arm_factored=flight_table=="16'hF400"
        gate=n.pin(path,'I3')
    old_flight = window('n5090_8')
    timer = endpoint('partial_timer_31_9') if reserved_dispatch else window('partial_timer_31_12') if grouped_context else endpoint('partial_timer_31_9') if retired_usb else n.canonical('', 'partial_timer_31_9')
    if arm_capture and flight_arm_factored:
        # Here n5090_8 is the inhibit, rather than the old-flight term.
        # Expand the real Q and timer/flush input instead of assigning the
        # previous semantic meaning to the surviving numeric net name.
        inhibit = old_flight
        flight_q = n.pin(g.register(W,'flight',0),'Q')
        require(n.pin(path,'I1')==flight_q,'ARM window flight Q feedback changed')
        flight_mapping = 'arm_capture_inhibit_and_registered_flight'
        proofs.append(g.equivalent('ARM capture external flush drives actual flight D',
            [flight_d,flight_q,inhibit,timer,flush,gate],
            lambda v:v[0] == int(v[5] and ((v[1] and not v[2]) or (v[3] and v[4]))),
            cuts={inhibit,timer,flush,gate}))
    elif g.drivers[old_flight]:
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
        actual_reply_load_LUT_INIT=load_table if reserved_dispatch else None,
        actual_window_flight_LUT_INIT=flight_table if reserved_dispatch else None,
        actual_batch_state_bits=len(inventory), checked_clock_reset_registers=len(checked),
        USB_retirement_mapping=usb_absence,
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
