"""Actual TF cancellation counter and registered Gray next-Q equations."""
from tools.workstation_runtime_pcm_cdc import BooleanDiagram,Graph
from tools.workstation_task3_root_reset_audit import RootDiagram
from tools.workstation_task3_native_held import zero_ff

SCOPE='u_managed/runtime/g_direct_tf.tail'

def require(ok,message):
    if not ok:raise ValueError('TF tail cancellation Gray: '+message)

def audit(n,*,local_release_q):
    g=Graph(n);r=lambda stem,i:g.register(SCOPE,stem,i)
    gray=[r('fence_gray',i)for i in range(32)]
    # Gray's MSB is exactly the binary MSB and is merged by this synthesis.
    binary=[r('fence_count',i)for i in range(31)]+[gray[31]]
    q=[n.pin(p,'Q')for p in binary];gq=[n.pin(p,'Q')for p in gray]
    require(not any(p.startswith(SCOPE+'/fence_count_31_s')for p in g.regs),
            'unreviewed separate binary MSB state')
    candidates={n.pin(p,'CE')for p in binary+gray}-{*g.high,*g.low}
    require(len(candidates)==1,'unique fence update enable missing')
    enable=next(iter(candidates))
    # Gowin duplicates the fence event as an inverted module input for the
    # always-enabled endpoint bits. Prove the relation before substituting it;
    # independent symbolic cuts here would admit contradictory event values.
    inverse_event=n.canonical(SCOPE,'n2037_9')
    kind=n.frames[SCOPE]['kind'];external=set()
    for name,direction in n.directions[kind].items():
        if direction!='input':continue
        bounds=n.ranges[kind].get(name)
        bits=[name] if bounds is None else [name+'['+str(i)+']'for i in range(min(bounds),max(bounds)+1)]
        external.update(n.canonical(SCOPE,bit)for bit in bits)
    inverted_alias=None
    if g.drivers[inverse_event]:
        cuts=external-{enable,inverse_event}
        support=g.support(enable,cuts=cuts)|g.support(inverse_event,cuts=cuts)
        e=BooleanDiagram(sorted(support))
        require(e.net(g,inverse_event)==e.invert(e.net(g,enable)),
                'duplicated fence event is not the exact inverse')
        event_inputs=[enable]
        inverted_alias=dict(net=inverse_event,exact_inverse_proven=True,
                            independent_inputs=sorted(support))
        event_mapping='proved_inverted_event_alias'
    else:
        # The boot-geometry build factors the shared event into two real
        # module inputs. Expand both into every D/CE equation; an independent
        # event cut would lose their relation to always-enabled counter bits.
        drivers=g.drivers[enable]
        require(len(drivers)==1,'factored event driver missing/ambiguous')
        cell,port=drivers[0]
        require(n.cells[cell]['kind']=='LUT2' and port=='F' and
                n.cells[cell]['parameters'].get('INIT')=="4'hE",
                'factored event is not the actual two-input OR')
        event_inputs=[n.pin(cell,'I0'),n.pin(cell,'I1')]
        require(len(set(event_inputs))==2 and set(event_inputs)<=external and
                not set(event_inputs)&set(q+gq+[local_release_q]),
                'factored event inputs are not independent module inputs')
        event_mapping='expanded_two_input_OR'
    class CounterDiagram(RootDiagram):
        def net(self,graph,net,memo=None,active=()):
            if inverted_alias is not None and net==inverse_event:
                return self.invert(self.inputs[enable])
            return super().net(graph,net,memo,active)
    leaves=list(dict.fromkeys([*q,*gq,local_release_q,*event_inputs]));b=CounterDiagram(leaves)
    live=b.inputs[local_release_q];en=b.net(g,enable);carry=en;next_binary=[]
    for bit,p in enumerate(binary):
        zero_ff(n,g,p,'audio_clk');clear=n.pin(p,'CLEAR')
        require(g.support(clear)=={local_release_q} and
            b.net(g,clear)==b.invert(live),'counter reset is not exact local release')
        v=b.inputs[q[bit]];expected=b.different(v,carry);carry=b.both(carry,v);next_binary.append(expected)
        actual=b.both(live,b.choose(b.net(g,n.pin(p,'CE')),b.net(g,n.pin(p,'D')),v))
        require(actual==b.both(live,expected),'binary increment next-Q changed bit '+str(bit))
    for bit,p in enumerate(gray):
        zero_ff(n,g,p,'audio_clk');clear=n.pin(p,'CLEAR')
        require(g.support(clear)=={local_release_q} and
            b.net(g,clear)==b.invert(live),'Gray reset is not exact local release')
        v=b.inputs[gq[bit]]
        value=next_binary[bit] if bit==31 else b.different(next_binary[bit],next_binary[bit+1])
        expected=b.both(live,b.choose(en,value,v))
        actual=b.both(live,b.choose(b.net(g,n.pin(p,'CE')),b.net(g,n.pin(p,'D')),v))
        require(actual==expected,'registered Gray next-Q changed bit '+str(bit))
    return dict(policy='actual_TF_fence_counter_registered_Gray_v1',binary=binary,gray=gray,
        shared_event_enable=enable,local_release_q=local_release_q,binary_next_Q_equations=32,
        inverted_event_alias=inverted_alias,event_mapping=event_mapping,
        event_equation_inputs=event_inputs,event_relation_preserved_in_all_next_Q=True,
        Gray_next_Q_equations=32,MSB_exact_binary_alias=True,all_counter_states_included=True,
        routed_timing_verified=False,hardware_tested=False)
