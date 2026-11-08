"""Mapped TF Gray publishers and small FIFO ownership control.

Binary/Gray relations follow inductively from zero INIT and these exact next-Q
equations. First-stage sampling/skew and RAM arcs are checked by the frame CDC
and physical gates; this module does not claim routed or hardware acceptance.
"""
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
    rows.append(counter('generation',binary,gray,root,([event],lambda b:b.inputs[event])))
    binary=g.group(B,'ack_binary',32)
    gray=g.group(B,'ack_gray',31)+[binary[31]]
    expected=g.group(B,'expected_generation_o',32)
    expected_q=list(map(q,expected));valid=q(register(B,'expected_generation_valid_o'))
    def ack_enable(b):
        ne=b.invert(b.all([b.invert(b.different(b.inputs[q(p)],b.inputs[e]))
                          for p,e in zip(binary,expected_q)]))
        return b.both(b.inputs[valid],ne)
    rows.append(counter('ack',binary,gray,compute,([valid],ack_enable),expected_q))

    fifo=[]
    for side in ('write','read'):
        binary=g.group(F,side+'_binary',4 if side=='write' else 5)
        gray=g.group(F,side+'_gray',5 if side=='write' else 4)
        if side=='write':binary.append(gray[4])
        else:gray.append(binary[4])
        event=n.pin(gray[0],'CE')
        fifo.append(counter(side,binary,gray,write_reset if side=='write' else compute,
                            ([event],lambda b,event=event:b.inputs[event])))
    # Both sides use exact full/empty comparisons of all five pointer bits.
    # Prove that actual commits cannot advance into full or past empty. Other
    # local admission inputs remain arbitrary; this is a safety implication.
    controls=[]
    for side,remote,flip in (('write','read',True),('read','write',False)):
        local=fifo[0 if side=='write' else 1]['gray']
        synced=g.group(F,remote+'_gray_sync',5)
        event=n.pin(local[0],'CE')
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
