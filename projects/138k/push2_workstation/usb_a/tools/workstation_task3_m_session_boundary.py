"""Actual paired-M HCI held key and three-edge session capture proof.

Each bit proves ready-next implies its data-next is unchanged. Unrelated
admission logic is conservatively arbitrary, with shared cuts kept correlated.
Only exact finite data constraints are emitted; hardware acceptance is separate.
"""
from tools.workstation_runtime_pcm_cdc import Graph, COMB, BooleanDiagram
from tools.workstation_task3_root_reset_audit import RootDiagram
from tools.workstation_task3_native_held import zero_ff
from tools.workstation_recording_phase1_cdc import complete_closure

class KeyDiagram(RootDiagram):
    def __init__(self,inputs):
        # This one proof retains both complete 64-bit key operands. The
        # shared 120-leaf bound is deliberately unchanged for other audits.
        require(len(inputs)==len(set(inputs))<=256,'paired key support exceeds 256')
        super().__init__([])
        self.inputs={net:self.node(i,0,1)for i,net in enumerate(inputs)}

    def net(self,graph,net,memo=None,active=()):
        if net not in self.inputs and net not in graph.high|graph.low:
            ds=graph.drivers[net]
            if len(ds)==1 and graph.n.cells[ds[0][0]]['kind']=='ALU' and graph.n.cells[ds[0][0]]['parameters'].get('ALU_MODE')=='3':
                path,port=ds[0]
                require(port=='COUT' and graph.n.pin(path,'I3')in graph.low,'unreviewed NE primitive output')
                # Respect every named conservative carry cut instead of
                # expanding through it to unrelated operand publishers.
                a,c,carry=[self.net(graph,graph.n.pin(path,p),memo,(*active,net))for p in ('I0','I1','CIN')]
                return self.either(self.different(a,c),carry)
        return super().net(graph,net,memo,active)

S='u_task3_m_endpoint' 
T='u_managed/runtime/cpu_pcm.session'

def require(ok,message):
    if not ok:raise ValueError('M session boundary: '+message)


def frontier(n,g,outputs,protected):
    memo={}
    def depends(net):
        if net in protected:return True
        if net in memo:return memo[net]
        if net in g.high|g.low:return False
        ds=g.drivers[net]
        if len(ds)!=1:return False
        p,port=ds[0]
        if p in g.regs:return False
        require(n.cells[p]['kind'] in COMB,'opaque key dependency '+p)
        memo[net]=any(depends(n.pin(p,k))for k in n.cells[p]['ports'] if k not in COMB[n.cells[p]['kind']])
        return memo[net]
    result=set();seen=set();todo=list(outputs)
    while todo:
        net=todo.pop()
        if net in seen or net in g.high|g.low:continue
        seen.add(net)
        if net in protected or not depends(net):result.add(net);continue
        p,port=g.drivers[net][0]
        todo.extend(n.pin(p,k)for k in n.cells[p]['ports'] if k not in COMB[n.cells[p]['kind']])
    return sorted(result)


def audit(n):
    g=Graph(n);ready=g.register(S,'hci_ready_o');source=g.group(S,'remote_status',70)[6:]
    zero_ff(n,g,ready,'clk_50m');require(n.pin(ready,'CE') in g.high,'ready publisher gated')
    rows=[]
    for i,p in enumerate(source,6):
        zero_ff(n,g,p,'clk_50m')
        require(n.pin(p,'CLEAR')==n.pin(ready,'CLEAR'),'source reset differs')
        old=n.pin(p,'Q');incoming=n.canonical('',f'task3_pair_rx_payload[{i}]')
        outputs=[n.pin(ready,'D'),n.pin(p,'CE'),n.pin(p,'D')]
        leaves=sorted(set([old,incoming]+frontier(n,g,outputs,{old,incoming,n.canonical(S,'new_identity')})))
        order=[x for j,sp in enumerate(source,6)for x in (n.pin(sp,'Q'),n.canonical('',f'task3_pair_rx_payload[{j}]'))]
        leaves=[x for x in order if x in leaves]+sorted(set(leaves)-set(order))
        b=KeyDiagram(leaves)
        # All non-key admission conditions remain arbitrary; none is assumed
        # true to make the property pass.
        next_data=b.choose(b.net(g,n.pin(p,'CE')),b.net(g,n.pin(p,'D')),b.inputs[old])
        violation=b.both(b.net(g,n.pin(ready,'D')),b.different(next_data,b.inputs[old]))
        if violation:
            node=violation;witness={}
            while node>1:
                variable,lo,hi=b.nodes[node];take=bool(hi);witness[leaves[variable]]=int(take);node=hi if take else lo
            raise ValueError('M key counterexample bit '+str(i)+' '+repr(witness))
        require(violation==0,
                'key can change while ready-next high bit '+str(i))
        rows.append(dict(register=p,bit=i,ready_next_implies_data_unchanged=True,
                         conservative_symbolic_cuts=leaves))
    release=g.group(T,'release_pipe',3);live=g.register(T,'live_o')
    q=lambda p:n.pin(p,'Q')
    leaves=[q(ready),q(g.register('u_managed/runtime','compute_release',2))]
    # Reset release equations and exact early fanout, including the final
    # final live register which shares assertion with the release pipe.
    for i,p in enumerate(release):
        zero_ff(n,g,p,'audio_clk');b=BooleanDiagram(leaves)
        require(b.net(g,n.pin(p,'CLEAR'))==b.invert(b.both(*[b.inputs[x]for x in leaves])),
                'session asynchronous assertion differs')
        require(n.pin(p,'CE')in g.high and
                (n.pin(p,'D')in g.high if i==0 else n.pin(p,'D')==q(release[i-1])),
                'session release shift changed')
        if i<2:
            c=complete_closure(n,g,[p]);require(c['ff_endpoints']=={release[i+1]+'/D':'audio_clk'}and
                not c['primitive_endpoints']and not c['top_output_endpoints'],'early session release extra consumer')
    zero_ff(n,g,live,'audio_clk')
    require(n.pin(live,'CLEAR')==n.pin(release[0],'CLEAR')and n.pin(live,'D')in g.high and
            n.pin(live,'CE')==q(release[2]),'session live capture changed')
    captures=g.group(T,'generation_o',32)+g.group(T,'epoch_o',32)
    for p,src in zip(captures,source):
        zero_ff(n,g,p,'audio_clk');b=BooleanDiagram([q(release[2]),q(live)])
        require(n.pin(p,'D')==q(src)and
                b.net(g,n.pin(p,'CE'))==b.both(b.inputs[q(release[2])],b.invert(b.inputs[q(live)])),
                'session atomic data/enable mapping changed '+p)
        capture_release=q(g.register('u_managed/runtime','compute_release',2))
        br=BooleanDiagram([capture_release])
        require(br.net(g,n.pin(p,'CLEAR'))==br.invert(br.inputs[capture_release]),'session functional reset changed')
    closure=complete_closure(n,g,source)
    remote={p:c for p,c in closure['ff_endpoints'].items()if c!='clk_50m'}
    require(remote=={p+'/D':'audio_clk'for p in captures}and not closure['primitive_endpoints']and
            not closure['top_output_endpoints'],'key remote consumer inventory changed')
    path='-from [get_pins {'+' '.join(p+'/Q'for p in source)+'}] -to [get_pins {'+' '.join(p+'/D'for p in captures)+'}]'
    sdc='\n# Proven paired M held HCI key: capture after three destination edges\nset_max_delay 10.000 '+path+'\nset_min_delay 1.800 '+path+'\n'
    return dict(policy='task3_M_actual_held_HCI_key_v1',source=source,capture=captures,
        source_stability=rows,release=release,source_complete_closure=closure,
        minimum_destination_wait_edges=3,max_data_delay_ns=10.0,min_data_delay_ns=1.8,
        hold_check_retained=True,routed_timing_verified=False,hardware_tested=False),sdc
