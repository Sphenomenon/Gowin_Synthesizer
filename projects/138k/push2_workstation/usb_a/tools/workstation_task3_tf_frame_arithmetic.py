"""Mapped TF Gray publishers and small FIFO ownership control.

Binary/Gray relations follow inductively from zero INIT and these exact next-Q
equations. First-stage sampling/skew and RAM arcs are checked by the frame CDC
and physical gates; this module does not claim routed or hardware acceptance.
"""
import re
from tools.workstation_runtime_pcm_cdc import Graph,COMB
from tools.workstation_task3_root_reset_audit import RootDiagram
from tools.workstation_task3_native_held import zero_ff

B='u_tf_audio/frames'
F=B+'/frames_0'


def require(ok,message):
    if not ok:raise ValueError('TF frame arithmetic: '+message)


def audit(n):
    g=Graph(n);rows=[]
    class Diagram(RootDiagram):
        def net(self,graph,net,memo=None,active=()):
            if net not in self.inputs and net not in graph.high|graph.low:
                ds=graph.drivers[net]
                if len(ds)==1 and n.cells[ds[0][0]]['kind']=='ALU' and n.cells[ds[0][0]]['parameters'].get('ALU_MODE')=='3':
                    # The shared checker validates every mode, carry link,
                    # inversion and operand before this NE summary is used.
                    pairs=graph.inequality_chain(net)
                    value=0
                    for a,c in sorted(sorted(pair)for pair in pairs):
                        value=self.either(value,self.different(self.net(graph,a),self.net(graph,c)))
                    return value
            return super().net(graph,net,memo,active)
    q=lambda p:n.pin(p,'Q')
    register=lambda scope,stem,i=None:g.register(scope,stem,i)
    root=q(register('u_reset','started'))
    compute=q(register(B,'compute_release',2))
    write_reset=q(register(B,'source_release',2))

    def counter(label,binary,gray,live,enable,extra=()):
        # Interleave equality operands to keep 32-bit predicates compact.
        leaves=[]
        for i,p in enumerate(binary):
            leaves.append(q(p))
            if i<len(extra):leaves.append(extra[i])
        leaves.extend([*map(q,gray),live,*enable[0]])
        b=Diagram(list(dict.fromkeys(leaves)))
        en=enable[1](b);carry=1;increment=[]
        for p in binary:
            value=b.inputs[q(p)]
            increment.append(b.different(value,carry));carry=b.both(carry,value)
        proofs=[]
        for kind,regs in (('binary',binary),('gray',gray)):
            for i,p in enumerate(regs):
                zero_ff(n,g,p,n.pin(binary[0],'CLK'))
                require(g.support(n.pin(p,'CLEAR'))=={live} and
                        b.net(g,n.pin(p,'CLEAR'))==b.invert(b.inputs[live]),
                        label+' reset publisher changed')
                value=increment[i]
                if kind=='gray' and i<len(regs)-1:value=b.different(value,increment[i+1])
                expected=b.both(b.inputs[live],b.choose(en,value,b.inputs[q(p)]))
                actual=b.choose(b.net(g,n.pin(p,'CLEAR')),0,b.choose(
                    b.net(g,n.pin(p,'CE')),b.net(g,n.pin(p,'D')),b.inputs[q(p)]))
                require(actual==expected,label+' '+kind+' next-Q bit '+str(i))
                proofs.append(dict(register=p,kind=kind,bit=i,next_Q_exact=True))
        return dict(id=label,binary=binary,gray=gray,next_Q=proofs,
                    zero_initial_state=True,modular_increment=True,
                    registered_Gray_invariant_inductive=True,
                    at_most_one_changed_Gray_bit_per_source_edge=True)

    binary=g.group(B,'source_generation_o',32)
    gray=g.group(B,'source_generation_gray',31)+[binary[31]]
    event=n.pin(binary[0],'CE')
    enable=([event],lambda b:b.inputs[event])
    guard_proof=None
    if event in g.high:
        # Synthesis can absorb the LSB enable into its D LUT. All remaining
        # binary bits must retain one actual, nonconstant event CE. Expand
        # that CE's exact LUT, sharing its actual inputs with the LSB D LUT;
        # every bit is then checked below over independent guard inputs.
        # No state-machine predicate or invented event replaces the enable.
        events={n.pin(p,'CE') for p in binary[1:]}
        require(len(events)==1,'generation higher-bit event enables differ')
        event=next(iter(events))
        require(event not in g.high|g.low,'generation event is constant')
        drivers=g.drivers[event]
        require(len(drivers)==1,'generation event driver absent/ambiguous')
        cell,port=drivers[0];kind=n.cells[cell]['kind']
        require(re.fullmatch('LUT[1-6]',kind) and port=='F',
                'generation absorbed event is not an actual LUT')
        leaves=[n.pin(cell,'I'+str(i)) for i in range(int(kind[3:]))]
        require(len(set(leaves))==len(leaves) and
                not set(leaves)&set(map(q,binary+gray)),
                'generation event inputs alias counter state')
        enable=(leaves,lambda b:b.net(g,event))
        guard_proof=dict(policy='actual_LSB_D_absorbed_enable_v1',
            event_net=event,actual_event_LUT=cell,independent_guard_inputs=leaves,
            event_truth=n.cells[cell]['parameters'].get('INIT'),
            LSB_enable_constant_high=True,all_binary_and_Gray_next_Q_checked=True,
            event_state_machine_semantics_proven=False)
    result=counter('generation',binary,gray,root,enable)
    result['absorbed_LSB_event_proof']=guard_proof
    rows.append(result)
    binary=g.group(B,'ack_binary',32)
    gray=g.group(B,'ack_gray',31)+[binary[31]]
    expected=g.group(B,'expected_generation_o',32)
    expected_q=list(map(q,expected));valid=q(register(B,'expected_generation_valid_o'))
    def ack_enable(b):
        ne=b.invert(b.all([b.invert(b.different(b.inputs[q(p)],b.inputs[e]))
                          for p,e in zip(binary,expected_q)]))
        return b.both(b.inputs[valid],ne)
    rows.append(counter('ack',binary,gray,compute,([valid],ack_enable),expected_q))

    def absorbed_fifo_counter(side,binary,gray,live,event):
        # The empty-slot rebuild absorbs the read LSB/Gray0 enable into D.
        # Expand the actual higher-bit commit and all D/CE cones together;
        # no composite-event cut or pointer correlation is assumed.
        from tools.workstation_task3_w_consumer_nextq import Circuit,Expressions,sat_compare
        e=Expressions();c=Circuit(n,e);en=c.net(event);carry=1;increment=[]
        for path in binary:
            value=c.net(q(path));increment.append(e.xor(value,carry))
            carry=e.choose(carry,value,0)
        proofs=[]
        for kind,regs in (('binary',binary),('gray',gray)):
            for i,p in enumerate(regs):
                zero_ff(n,g,p,n.pin(binary[0],'CLK'))
                require(g.support(n.pin(p,'CLEAR'))=={live},side+' reset publisher changed')
                clear=Diagram([live])
                require(clear.net(g,n.pin(p,'CLEAR'))==clear.invert(clear.inputs[live]),
                        side+' reset polarity changed')
                value=increment[i]
                if kind=='gray' and i<len(regs)-1:value=e.xor(value,increment[i+1])
                expected=e.choose(c.net(live),e.choose(en,value,c.net(q(p))),0)
                actual,init,clock=c.next_q(p)
                require(init=="1'b0",side+' counter initialization changed')
                proof=sat_compare(e,actual,expected)
                proofs.append(dict(register=p,kind=kind,bit=i,next_Q_exact=True,**proof))
        return dict(id=side,binary=binary,gray=gray,next_Q=proofs,
            commit_event=event,absorbed_LSB_and_Gray0_enable=True,
            full_actual_commit_cone_expanded=True,zero_initial_state=True,
            modular_increment=True,registered_Gray_invariant_inductive=True,
            at_most_one_changed_Gray_bit_per_source_edge=True)

    fifo=[]
    for side in ('write','read'):
        binary=g.group(F,side+'_binary',4 if side=='write' else 5)
        gray=g.group(F,side+'_gray',5 if side=='write' else 4)
        if side=='write':binary.append(gray[4])
        else:gray.append(binary[4])
        event=n.pin(gray[0],'CE')
        live=write_reset if side=='write' else compute
        if event in g.high:
            events={n.pin(p,'CE') for p in gray[1:]}
            require(len(events)==1,'FIFO higher Gray commit enables differ')
            event=next(iter(events))
            require(event not in g.high|g.low,'FIFO commit event is constant')
            fifo.append(absorbed_fifo_counter(side,binary,gray,live,event))
        else:
            fifo.append(counter(side,binary,gray,live,
                                ([event],lambda b,event=event:b.inputs[event])))
    # Both sides use exact full/empty comparisons of all five pointer bits.
    # Prove that actual commits cannot advance into full or past empty. Other
    # local admission inputs remain arbitrary; this is a safety implication.
    controls=[]
    for side,remote,flip in (('write','read',True),('read','write',False)):
        local=fifo[0 if side=='write' else 1]['gray']
        synced=g.group(F,remote+'_gray_sync',5)
        event=fifo[0 if side=='write' else 1].get('commit_event',n.pin(local[0],'CE'))
        cuts={q(p)for p in local+synced}
        # Upstream track/generation admission is allowed to suppress work.
        # Its arithmetic is arbitrary here; it must never bypass full/empty.
        memo={}
        def depends(net):
            if net in cuts:return True
            if net in memo:return memo[net]
            if net in g.high|g.low:return False
            ds=g.drivers[net]
            require(len(ds)==1,'ownership driver missing/ambiguous')
            path,port=ds[0]
            if path in g.regs:return False
            require(n.cells[path]['kind']in COMB,'ownership opaque primitive')
            memo[net]=any(depends(n.pin(path,pin))for pin in n.cells[path]['ports']
                          if pin not in COMB[n.cells[path]['kind']])
            return memo[net]
        support=set();todo=[event];seen=set()
        while todo:
            net=todo.pop()
            if net in seen or net in g.high|g.low:continue
            seen.add(net)
            if net in cuts or not depends(net):support.add(net);continue
            path,port=g.drivers[net][0]
            todo.extend(n.pin(path,pin)for pin in n.cells[path]['ports']
                        if pin not in COMB[n.cells[path]['kind']])
        b=Diagram(list(dict.fromkeys([x for pair in zip(map(q,local),map(q,synced))for x in pair]+sorted(support-cuts))))
        equal=b.all([b.invert(b.different(b.inputs[q(a)],
            b.invert(b.inputs[q(c)])if flip and i>=3 else b.inputs[q(c)]))
            for i,(a,c)in enumerate(zip(local,synced))])
        require(b.both(b.net(g,event),equal)==0,side+' commit violates full/empty ownership')
        controls.append(dict(side=side,commit=event,full_or_empty_blocks_commit=True,
                             pointer_bits=5,remote_second_stage_only=True))
    return dict(policy='task3_actual_TF_frame_Gray_and_FIFO_control_v1',
                publishers=rows+fifo,ownership_controls=controls,
                next_Q_equations=sum(len(r['next_Q'])for r in rows+fifo),
                memory_ownership_basis='zero pointers; Gray one-step publication; full/empty exclusion; synchronized release before address reuse',
                physical_RAM_arcs_and_skew_required=True,routed_timing_verified=False,hardware_tested=False)
