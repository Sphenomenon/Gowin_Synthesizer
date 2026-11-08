"""Exact same-cycle W full-key comparator structural lineage."""
import hashlib
SOURCE = 'rtl/workstation/workstation_task3_w_bus_endpoint.sv'
TOOL = 'tools/workstation_w_context_compare.py'
POLICY = 'task3_W_full128_context_byte_compare_v1'
ARM_CAPTURE_SHA256 = 'cfabbd51941804aad088fb56ba099e7835038984fb77eb96d89fd3a77fb6250e'
ARM_CAPTURE = '    workstation_task3_phone_command_proxy #(.CAPTURE_ARM(BLOCK_PCM)) phone_proxy('
ARM_PARENT = '    workstation_task3_phone_command_proxy phone_proxy('
PARENT_SHA256 = '6be589f8299ac6b0754833b2269a62691e638cb09b3730607c36dd2dba650ecb'
SELECTED_SHA256 = '904dac4d5f4ac55bad9e8ad3af2bce45798082d43afc006cdaf2eafdd02fa4f9'
PARENT = '    wire context_current=observed_context=={local_boot_i,common};\n'
SELECTED = '    // Keep byte comparisons separate: one carry chain across the full key\n    // put immediate session fencing on the W critical path. No extra state.\n    wire [127:0] current_context={local_boot_i,common};\n    (* syn_keep=1 *) wire [15:0] context_equal_bytes;\n    genvar context_byte;\n    generate for(context_byte=0;context_byte<16;context_byte=context_byte+1)begin:g_context_equal\n        assign context_equal_bytes[context_byte]=\n            observed_context[context_byte*8+:8]==current_context[context_byte*8+:8];\n    end endgenerate\n    wire context_current=&context_equal_bytes;\n'

def normalize(source):
    from tools.workstation_record_cancel_compare import normalize as cancel_parent
    from tools.workstation_w_tx_class import normalize as tx_parent
    source=cancel_parent(tx_parent(source))
    digest = lambda b: hashlib.sha256(b).hexdigest()
    if digest(source)==ARM_CAPTURE_SHA256:
        if source.count(ARM_CAPTURE.encode())!=1:raise ValueError('W ARM capture instance drift')
        source=source.replace(ARM_CAPTURE.encode(),ARM_PARENT.encode(),1)
        if digest(source)!=SELECTED_SHA256:raise ValueError('W ARM capture exact inverse drift')
    if digest(source) == PARENT_SHA256:
        return source
    if digest(source) != SELECTED_SHA256 or source.count(SELECTED.encode()) != 1:
        raise ValueError('W full-key comparison source drift')
    old = source.replace(SELECTED.encode(), PARENT.encode(), 1)
    if digest(old) != PARENT_SHA256 or old.replace(PARENT.encode(), SELECTED.encode(), 1) != source:
        raise ValueError('W full-key comparison exact inverse changed')
    return old


def audit_mapped(n, g):
    """Check all 128 compared bits and prove each byte vetoes actual live.

    Zero propagation evaluates exact LUT cofactors with every unspecified
    input free. It neither assumes legal states nor cuts a missing driver.
    """
    import re
    from tools.workstation_task3_root_reset_audit import RootDiagram
    scope='u_task3_bus_endpoint'
    live=n.canonical(scope,'live')
    current=[n.canonical('',name+f'[{bit}]')
        for name in ('task3_pair_generation','task3_pair_session',
                     'task3_pair_peer_boot','task3_pair_local_boot')for bit in range(32)]
    observed=[n.pin(g.register(scope,'observed_context',bit),'Q')for bit in range(128)]
    rows=[]
    for byte in range(16):
        pairs=list(zip(observed[byte*8:byte*8+8],current[byte*8:byte*8+8]))
        result=n.canonical(scope,f'context_equal_bytes[{byte}]')
        frontier=g.carry_frontier(result)
        if len(frontier)!=1:
            raise ValueError('W context byte carry frontier changed: '+str(byte))
        carry=next(iter(frontier));actual_pairs=g.inequality_chain(carry)
        expected_pairs={frozenset(pair)for pair in pairs}
        remaining=expected_pairs-actual_pairs
        if not actual_pairs<=expected_pairs or len(actual_pairs)!=7 or len(remaining)!=1:
            raise ValueError('W context byte carry operands changed: '+str(byte))
        left,right=sorted(next(iter(remaining)))
        b=RootDiagram([carry,left,right])
        expected=b.both(b.invert(b.inputs[carry]),b.invert(b.different(b.inputs[left],b.inputs[right])))
        if b.net(g,result)!=expected:
            raise ValueError('W context mapped final byte equation changed: '+str(byte))
        known={**{net:0 for net in g.low},**{net:1 for net in g.high},result:0}
        todo=[result];checked=set()
        while todo:
            net=todo.pop()
            for path,pin,role in g.fan[net]:
                if role!='comb':continue
                cell=n.cells[path];kind=cell['kind']
                if kind=='INV':
                    inputs=[n.pin(path,'I')];out=n.pin(path,'O');table=1
                elif re.fullmatch('LUT[1-6]',kind):
                    width=int(kind[3:]);inputs=[n.pin(path,'I'+str(i))for i in range(width)]
                    out=n.pin(path,'F')
                    value=re.fullmatch(r"(\d+)'h([0-9a-fA-F]+)",cell['parameters'].get('INIT',''))
                    if value is None or int(value[1])!=1<<width:
                        raise ValueError('W context veto LUT truth table changed: '+path)
                    table=int(value[2],16)
                else:continue
                values={table>>index&1 for index in range(1<<len(inputs))
                    if all(net not in known or index>>i&1==known[net]for i,net in enumerate(inputs))}
                if len(values)!=1:continue
                value=next(iter(values));checked.add(path)
                if out in known:
                    if known[out]!=value:raise ValueError('W context veto has conflicting constants')
                else:known[out]=value;todo.append(out)
        if known.get(live)!=0:
            raise ValueError('W context byte no longer vetoes endpoint live: '+str(byte))
        rows.append(dict(byte=byte,observed=[a for a,z in pairs],current=[z for a,z in pairs],
            comparison_net=result,exact_8bit_equality=True,all_other_inputs_free=True,
            zero_forces_live_zero=True,constant_cofactor_cells=len(checked),BDD_nodes=len(b.nodes)))
    return dict(policy=POLICY,compared_bits=128,byte_equations=rows,
                every_byte_mismatch_fences_live=True,no_state_or_extra_cycles=True,
                full_endpoint_state_machine_proven=False,routed_timing_verified=False)


def prove_zero_veto(n,g,source,sink):
    """Exact constant cofactors, with all other inputs free; no state assumption."""
    import re
    known={**{net:0 for net in g.low},**{net:1 for net in g.high},source:0}
    pending=[source];checked=set()
    while pending:
        net=pending.pop()
        for path,pin,role in g.fan[net]:
            if role!='comb':continue
            c=n.cells[path];kind=c['kind']
            if kind=='INV':inputs=[n.pin(path,'I')];out=n.pin(path,'O');table=1
            elif re.fullmatch('LUT[1-6]',kind):
                width=int(kind[3:]);inputs=[n.pin(path,'I'+str(i))for i in range(width)];out=n.pin(path,'F')
                match=re.fullmatch(r"(\d+)'h([0-9a-fA-F]+)",c['parameters'].get('INIT',''))
                if not match or int(match[1])!=1<<width:raise ValueError('W zero-veto LUT format changed')
                table=int(match[2],16)
            else:continue
            values={table>>i&1 for i in range(1<<len(inputs))
                    if all(k not in known or i>>j&1==known[k]for j,k in enumerate(inputs))}
            if len(values)!=1:continue
            value=next(iter(values));checked.add(path)
            if out in known:
                if known[out]!=value:raise ValueError('W zero-veto conflicting constants')
            else:known[out]=value;pending.append(out)
    if known.get(sink)!=0:raise ValueError('W actual zero input no longer vetoes sink')
    return dict(source=source,sink=sink,all_other_inputs_free=True,
                zero_forces_zero=True,constant_cofactor_cells=sorted(checked))
