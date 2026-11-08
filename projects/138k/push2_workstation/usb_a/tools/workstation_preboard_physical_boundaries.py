"""Physical exceptions for named, proved asynchronous reset synchronizers.

Only explicit complete paired preboard candidates may select this adapter.
It never changes functional reset paths, clocks, setup/hold budgets, or legacy
SDC. Early-stage fanout and every next-Q equation are checked on the actual VG
before producing exact CLEAR selectors. Hardware acceptance is separate.
"""
from tools.workstation_runtime_pcm_cdc import Graph, BooleanDiagram, COMB
from tools.workstation_recording_phase1_cdc import complete_closure
from tools.workstation_task3_native_held import zero_ff

POLICY='task3_preboard_actual_reset_synchronizer_CLEAR_v1'
# Startup-gated release sequences retain their local startup input as data.
COMMON=(('u_managed','reset_compute_pipe',3,'startup_compute'),
        ('u_managed/runtime','compute_release',3,'startup_compute'),
        ('u_managed/midi_bytes','destination_release',3,None),
        ('u_managed/observation','destination_release',3,None))


def require(ok,message):
    if not ok:raise ValueError('preboard physical reset: '+message)


def prove_release(n,g,regs,*,startup=None):
    domain=n.pin(regs[0],'CLK');clear=n.pin(regs[0],'CLEAR')
    gate=n.pin(startup,'Q')if startup else None
    if startup:
        zero_ff(n,g,startup,domain)
        require(n.pin(startup,'CE') in g.high,'startup gate not unconditional')
    proofs=[]
    for i,p in enumerate(regs):
        zero_ff(n,g,p,domain)
        require(n.pin(p,'CLEAR')==clear and n.pin(p,'CE') in g.high,
                'release assertion or enable differs '+p)
        prior=n.pin(regs[i-1],'Q')if i else None
        leaves=list(dict.fromkeys(x for x in [gate,prior]if x))
        b=BooleanDiagram(leaves)
        expected=b.inputs[prior]if prior else 1
        if gate:expected=b.both(expected,b.inputs[gate])
        require(b.net(g,n.pin(p,'D'))==expected,'local release data changed '+p)
        row=dict(register=p,clock=domain,unconditional=True,next_D_equation_exact=True)
        if i<len(regs)-1:
            closure=complete_closure(n,g,[p])
            require(closure['ff_endpoints']=={regs[i+1]+'/D':domain}and
                not closure['primitive_endpoints']and not closure['top_output_endpoints'],
                'early release extra consumer '+p)
            row['early_complete_closure']=closure
        proofs.append(row)
    return dict(registers=regs,clock=domain,assertion=clear,stages=proofs)


def prove_level_synchronizer(n,g,regs,source,domain):
    """Only the final stage may escape a level synchronizer's shift chain."""
    clear=n.pin(regs[0],'CLEAR');proofs=[]
    for i,p in enumerate(regs):
        zero_ff(n,g,p,domain)
        require(n.pin(p,'CE') in g.high and n.pin(p,'CLEAR')==clear and
                n.pin(p,'D')==(n.pin(regs[i-1],'Q') if i else source),
                'level synchronizer clock/enable/reset/data changed '+p)
        row=dict(register=p,next_D_equation_exact=True)
        if i<len(regs)-1:
            closure=complete_closure(n,g,[p])
            require(closure['ff_endpoints']=={regs[i+1]+'/D':domain} and
                    not closure['primitive_endpoints'] and not closure['top_output_endpoints'],
                    'early level synchronizer extra consumer '+p)
            row['early_complete_closure']=closure
        proofs.append(row)
    return dict(registers=regs,clock=domain,assertion=clear,source=source,stages=proofs)


def w_routed_first_captures(n):
    """The four specific asynchronous first captures exposed by W route B6.

    No functional payload or later synchronizer stage is excepted. The FIFO
    MSB is an exact registered Gray alias, which the old *gray* selector missed.
    """
    from tools.workstation_task3_root_reset_audit import RootDiagram
    g=Graph(n);rows=[];lines=[]
    task='u_task3_media/cnn_stream/task_service'
    for scope,first,last,source in (
        (task,'broker_fault_meta','broker_fault_sync',g.register(task+'/broker','fault_o')),
        (task+'/cnn','g_drain_restart.memory_failed_meta','g_drain_restart.memory_failed_sync',
         g.register(task+'/cnn','g_drain_restart.memory_failed')),
        ('u_task3_media/cnn_stream','transport_fault_control_0','transport_fault_control_1',None)):
        regs=[g.register(scope,first),g.register(scope,last)]
        src=n.pin(source,'Q')if source else n.pin(regs[0],'D')
        if source:zero_ff(n,g,source,'memory_clk')
        else:
            require(src==n.canonical('u_task3_media','task3_memory_transport_fault'),
                    'CNN transport fault named source changed')
            # This status includes the encrypted DDR interface. It is an
            # asynchronous level, not a claim that every source FF is proven.
            # The maintained tag-consumer proof independently rejects a tag
            # bypass into CNN, while the exact two-stage chain is proved here.
            from tools.workstation_task3_w_fault_cdc import audit as fault_audit
            fault_audit(n,cnn_control=True)
        row=prove_level_synchronizer(n,g,regs,src,'clk_50m');rows.append(row)
        lines.extend(['set_false_path -to [get_pins {'+regs[0]+'/D}]',
            'set_max_delay 2.000 -from [get_pins {'+regs[0]+'/Q}] -to [get_pins {'+regs[1]+'/D}]'])
    scope=task+'/staging_requests'
    binary=g.group(scope,'read_binary',3)
    gray=g.group(scope,'read_gray',2)+[binary[2]]
    q=[n.pin(p,'Q')for p in binary];enable=n.pin(gray[0],'CE')
    from tools.workstation_task3_m_session_boundary import KeyDiagram,frontier
    protected=set(q+[n.pin(p,'Q')for p in gray+g.group(scope,'write_gray_sync',3)])
    outputs=[n.pin(p,pin)for p in binary+gray for pin in ('D','CE')]
    b=KeyDiagram(sorted(protected|set(frontier(n,g,outputs,protected))))
    event=b.net(g,enable);carry=event;next_binary=[]
    for bit,p in enumerate(binary):
        zero_ff(n,g,p,'memory_clk')
        expect=b.different(b.inputs[q[bit]],carry)
        actual=b.choose(b.net(g,n.pin(p,'CE')),b.net(g,n.pin(p,'D')),b.inputs[q[bit]])
        require(actual==expect,'staging FIFO binary increment changed')
        next_binary.append(expect);carry=b.both(carry,b.inputs[q[bit]])
    for bit,p in enumerate(gray[:2]):
        zero_ff(n,g,p,'memory_clk')
        require(n.pin(p,'CLEAR')==n.pin(binary[0],'CLEAR'),'staging FIFO reset differs')
        expect=b.choose(event,b.different(next_binary[bit],next_binary[bit+1]),
                        b.inputs[n.pin(p,'Q')])
        actual=b.choose(b.net(g,n.pin(p,'CE')),b.net(g,n.pin(p,'D')),b.inputs[n.pin(p,'Q')])
        require(actual==expect,'staging FIFO registered Gray changed')
    first=g.group(scope,'read_gray_meta',3);second=g.group(scope,'read_gray_sync',3)
    for source,one,two in zip(gray,first,second):
        row=prove_level_synchronizer(n,g,[one,two],n.pin(source,'Q'),'clk_50m')
        rows.append(row)
    # Keep the existing finite 10ns flight bound, including the aliased MSB.
    path='-from [get_pins {'+gray[2]+'/Q}] -to [get_pins {'+first[2]+'/D}]'
    lines.extend(['set_max_delay 10.000 '+path,'set_false_path -hold '+path,
        'set_max_delay 2.000 -from [get_pins {'+first[2]+'/Q}] -to [get_pins {'+second[2]+'/D}]'])
    return dict(policy='task3_W_B6_proven_async_first_capture_v1',chains=rows,
        fifo_binary_next_Q_equations=3,fifo_Gray_next_Q_equations=2,
        fifo_MSB_exact_binary_alias=True,functional_payload_exceptions_added=False), '\n'+'\n'.join(lines)+'\n'


def audit(n,*,role,stage):
    from pathlib import Path
    import json
    profile=json.loads((Path(stage).parents[1]/'workstation_profile.json').read_text())
    require(profile['profile']=='custom138k-workstation-task3-'+role.lower()+'-preboard-v1',
            'unselected preboard profile')
    require(role in ('M','W'),'explicit role required')
    g=Graph(n);rows=[]
    selected=COMMON if role=='W' else (COMMON[0],COMMON[1],COMMON[3])
    for scope,stem,width,gate in selected:
        regs=g.group(scope,stem,width)
        startup=g.register(scope,gate,1)if gate else None
        rows.append(prove_release(n,g,regs,startup=startup))
    bridge='u_managed/runtime/bridge'
    rows.append(prove_release(n,g,g.group(bridge,'compute_release',2)+
                              [g.register(bridge,'compute_reset_n')]))
    if role=='M':
        for scope in ('u_managed/control_cdc','u_task3_m_pcm_commands'):
            rows.append(prove_release(n,g,g.group(scope,'a_release',3)))
        # These are level observers, not functional state. The complete root
        # proof binds runtime_reset_n separately; do not except their consumers.
        for scope,stem,domain in (
                ('u_managed','startup_compute','audio_clk'),
                ('u_managed/runtime','startup_compute','audio_clk'),
                ('u_managed/runtime','startup_memory','memory_clk'),
                ('u_managed/runtime','startup_serial','dac_mclk_d')):
            rows.append(prove_level_synchronizer(n,g,g.group(scope,stem,2),
                        n.canonical('','runtime_reset_n'),domain))
        owner=[]
        for i in range(3):
            found=g.names[f'task3_m_owner_live_sync_{i}']
            require(len(found)==1,'owner level synchronizer stage absent/ambiguous')
            owner.append(found[0])
        source=g.names['task3_m_phone_live_source']
        require(len(source)==1,'owner level source absent/ambiguous')
        zero_ff(n,g,source[0],'clk_50m')
        rows.append(prove_level_synchronizer(n,g,owner,n.pin(source[0],'Q'),'audio_clk'))
    compute=None
    if role=='M':
        from tools.workstation_tf_compute_local_release import audit_mapped
        compute=audit_mapped(n,stage=stage)
    selected=[p+'/CLEAR'for row in rows for p in row['registers']]
    if compute is not None:
        selected.extend(p+'/CLEAR'for p in compute['root_asserted_synchronizer_registers'])
    require(len(selected)==len(set(selected)),'duplicate release selector')
    sdc='\n# '+POLICY+'\nset_false_path -to [get_pins {'+' '.join(selected)+'}]\n'
    routed_first=None
    if role=='W':
        routed_first,extra=w_routed_first_captures(n);sdc+=extra
        # B7 exposed the raw-store local reset release and its isolated
        # memory-up observer. These are receiving synchronizers, not payload
        # or functional reset consumers. Prove their complete first-Q fanout.
        scope='u_task3_media/raw_store'
        release=prove_release(n,g,g.group(scope,'control_release',2))
        parent=g.register('u_task3_media/memory','memory_release',2)
        zero_ff(n,g,parent,'memory_clk')
        parent_q=n.pin(parent,'Q');root_q=n.pin(g.register('u_reset','started'),'Q')
        b=BooleanDiagram([parent_q,root_q])
        require(release['clock']=='clk_50m' and
                b.net(g,release['assertion'])==b.invert(b.both(b.inputs[parent_q],b.inputs[root_q])),
                'raw-store control release is not asserted by the actual memory client release')
        zero_ff(n,g,g.register(scope,'memory_release',1),'memory_clk')
        observer=prove_level_synchronizer(n,g,
            [g.register(scope,'memory_up_meta'),g.register(scope,'memory_up_sync')],
            n.pin(g.register(scope,'memory_release',1),'Q'),'clk_50m')
        routed_first['raw_store_release']=release
        routed_first['raw_store_memory_up']=observer
        sdc+='\n# W B7 isolated raw-store receiving synchronizers\n'
        sdc+='set_false_path -to [get_pins {'+' '.join(p+'/CLEAR'for p in release['registers'])+'}]\n'
        first,last=observer['registers']
        sdc+='set_false_path -to [get_pins {'+first+'/D}]\n'
        sdc+='set_max_delay 2.000 -from [get_pins {'+first+'/Q}] -to [get_pins {'+last+'/D}]\n'
    return dict(policy=POLICY,role=role,release_chains=rows,exact_CLEAR_pins=selected,
                tf_compute_functional_reset=compute,
                W_routed_first_captures=routed_first,
                functional_reset_exceptions_added=False,setup_hold_unchanged=True,
                physical_CDC_accepted=False,hardware_tested=False),sdc
