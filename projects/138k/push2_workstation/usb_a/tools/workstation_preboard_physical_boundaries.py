"""Physical constraints for named, proved receiving synchronizers.

Only explicit complete paired preboard candidates may select this adapter.
It never excepts functional resets or payload timing, changes clocks or legacy
SDC. Early-stage fanout and every next-Q equation are checked on the actual VG
before producing exact D/CLEAR/PRESET selectors and finite later-stage bounds.
Registered Gray first captures retain finite flight limits. Acceptance is separate.
"""
from tools.workstation_runtime_pcm_cdc import Graph, BooleanDiagram, COMB
from tools.workstation_recording_phase1_cdc import complete_closure
from tools.workstation_task3_native_held import zero_ff

POLICY='task3_preboard_actual_receiving_synchronizers_v2'
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


def prove_asserted_release(n,g,regs,domain,asserted,release):
    """A9's two immediate-hold assertions shift out locally as two zeroes."""
    preset=n.pin(regs[0],'PRESET');b=BooleanDiagram([asserted,release])
    require(b.net(g,preset)==b.either(b.inputs[asserted],b.invert(b.inputs[release])),
            'hold assertion differs from source OR local reset')
    for i,p in enumerate(regs):
        require(n.cells[p]['kind']=='DFFPE'and n.pin(p,'CLK')==domain and
            n.cells[p]['parameters'].get('INIT',"1'b1")=="1'b1" and
            n.pin(p,'CE')in g.high and n.pin(p,'PRESET')==preset and
            (n.pin(p,'D')==n.pin(regs[i-1],'Q')if i else n.pin(p,'D')in g.low),
            'hold release equation changed '+p)
        if i<len(regs)-1:
            c=complete_closure(n,g,[p])
            require(c['ff_endpoints']=={regs[i+1]+'/D':domain}and
                not c['primitive_endpoints']and not c['top_output_endpoints'],
                'early hold release extra consumer '+p)
    return dict(registers=regs,clock=domain,assertion=preset,
        exact_shift_equations=True,early_complete_consumer_proved=True)


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
            if 'u_task3_media' in n.frames:
                named=n.canonical('u_task3_media','task3_memory_transport_fault')
            else:
                require(set(n.frames)=={''},'unexpected partially flattened fault hierarchy')
                named=n.canonical('',r'\u_task3_media/task3_memory_transport_fault')
                require(len(g.drivers.get(named,[]))==1,'flat named fault has no unique actual driver')
            require(src==named,'CNN transport fault named source changed')
            # This status includes the encrypted DDR interface. It is an
            # asynchronous level, not a claim that every source FF is proven.
            # The maintained tag-consumer proof independently rejects a tag
            # bypass into CNN, while the exact two-stage chain is proved here.
            from tools.workstation_task3_w_fault_cdc import audit as fault_audit
            fault_audit(n,cnn_control=True)
        row=prove_level_synchronizer(n,g,regs,src,'clk_50m');rows.append(row)
        lines.extend(['set_false_path -to [get_pins {'+regs[0]+'/D}]',
            'set_max_delay 2.000 -from [get_pins {'+regs[0]+'/Q}] -to [get_pins {'+regs[1]+'/D}]'])
    gray_rows,gray_lines=fifo_read_gray(n,g,task+'/staging_requests','memory_clk','clk_50m')
    rows.extend(gray_rows);lines.extend(gray_lines)
    return dict(policy='task3_W_B6_proven_async_first_capture_v1',chains=rows,
        fifo_binary_next_Q_equations=3,fifo_Gray_next_Q_equations=2,
        fifo_MSB_exact_binary_alias=True,functional_payload_exceptions_added=False), '\n'+'\n'.join(lines)+'\n'


def fifo_read_gray(n,g,scope,source_clock,destination_clock,*,all_bits=False):
    rows=[];lines=[]
    binary=g.group(scope,'read_binary',3)
    gray=g.group(scope,'read_gray',2)+[binary[2]]
    q=[n.pin(p,'Q')for p in binary]
    # The W ACK rebuild moves gray[0]'s read_fire into its D equation.
    # Use the real common FIFO pop net, then prove every effective next-Q;
    # no CE pin is assumed to retain the source enable in all mappings.
    enable=n.canonical(scope,'read_fire')
    require(enable not in g.high|g.low and len(g.drivers[enable])==1,
            'staging FIFO read_fire absent/constant/ambiguous')
    from tools.workstation_task3_m_session_boundary import KeyDiagram,frontier
    protected=set(q+[n.pin(p,'Q')for p in gray+g.group(scope,'write_gray_sync',3)])
    outputs=[n.pin(p,pin)for p in binary+gray for pin in ('D','CE')]
    b=KeyDiagram(sorted(protected|set(frontier(n,g,outputs,protected))))
    event=b.net(g,enable);carry=event;next_binary=[]
    for bit,p in enumerate(binary):
        zero_ff(n,g,p,source_clock)
        expect=b.different(b.inputs[q[bit]],carry)
        actual=b.choose(b.net(g,n.pin(p,'CE')),b.net(g,n.pin(p,'D')),b.inputs[q[bit]])
        require(actual==expect,'staging FIFO binary increment changed')
        next_binary.append(expect);carry=b.both(carry,b.inputs[q[bit]])
    for bit,p in enumerate(gray[:2]):
        zero_ff(n,g,p,source_clock)
        require(n.pin(p,'CLEAR')==n.pin(binary[0],'CLEAR'),'staging FIFO reset differs')
        expect=b.choose(event,b.different(next_binary[bit],next_binary[bit+1]),
                        b.inputs[n.pin(p,'Q')])
        actual=b.choose(b.net(g,n.pin(p,'CE')),b.net(g,n.pin(p,'D')),b.inputs[n.pin(p,'Q')])
        require(actual==expect,'staging FIFO registered Gray changed')
    first=g.group(scope,'read_gray_meta',3);second=g.group(scope,'read_gray_sync',3)
    for source,one,two in zip(gray,first,second):
        row=prove_level_synchronizer(n,g,[one,two],n.pin(source,'Q'),destination_clock)
        rows.append(row)
    # Keep the existing finite 10ns flight bound, including the aliased MSB.
    for bit in (range(3)if all_bits else (2,)):
        path='-from [get_pins {'+gray[bit]+'/Q}] -to [get_pins {'+first[bit]+'/D}]'
        lines.extend(['set_max_delay 10.000 '+path,'set_false_path -hold '+path,
            'set_max_delay 2.000 -from [get_pins {'+first[bit]+'/Q}] -to [get_pins {'+second[bit]+'/D}]'])
    return rows,lines


def audit(n,*,role,stage):
    from pathlib import Path
    import json
    profile=json.loads((Path(stage).parents[1]/'workstation_profile.json').read_text())
    require(profile['profile']=='custom138k-workstation-task3-'+role.lower()+'-preboard-v1',
            'unselected preboard profile')
    require(role in ('M','W'),'explicit role required')
    g=Graph(n);rows=[];preset_rows=[]
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
        owner_proof=rows[-1]
        def top_group(stem,width):
            result=[]
            for i in range(width):
                found=g.names.get(f'{stem}_{i}',[])
                require(len(found)==1,'top synchronizer absent/ambiguous '+stem)
                result.append(found[0])
            return result
        idle=top_group('task3_m_idle_sync',2)
        idle_proof=prove_level_synchronizer(n,g,idle,
            n.canonical('','task3_m_pcm_idle_compute'),'clk_50m')
        rows.append(idle_proof)
        ack=[g.register('u_task3_m_pcm_commands',s)for s in ('ack_meta','ack_sync','ack_settled')]
        ack_source=g.register('u_task3_m_pcm_commands','acknowledge_toggle')
        zero_ff(n,g,ack_source,'audio_clk')
        ack_proof=prove_level_synchronizer(n,g,ack,n.pin(ack_source,'Q'),'clk_50m')
        rows.append(ack_proof)
        safety=top_group('output_safe_sync',2)
        rows.append(prove_level_synchronizer(n,g,safety,
            n.canonical('','compute_output_safe_n'),'audio_clk'))
        rows.append(prove_release(n,g,top_group('output_safe_compute',3),startup=safety[1]))
        rows.append(prove_release(n,g,g.group('u_runtime/u_usb_cdc','source_release',3)))
        usb_ready=g.group('u_runtime','g_usb_cdc_reset.usb_ready',2)
        # This legacy telemetry instance is flattened into the top module;
        # bind its actual top reset and USB release publisher, not a fabricated
        # module-formal name which canonical() would leave unresolved.
        usb_inputs=[n.canonical('','reset_n'),n.pin(top_group('usb_release',4)[3],'Q')]
        b=BooleanDiagram(usb_inputs);expected=1
        for net in usb_inputs:expected=b.both(expected,b.inputs[net])
        require(b.net(g,n.pin(usb_ready[0],'D'))==expected,'telemetry USB readiness source changed')
        rows.append(prove_level_synchronizer(n,g,usb_ready,n.pin(usb_ready[0],'D'),'usb_clk'))
        if (Path(stage)/'rtl/telemetry/gw138k_push_performance_uart.sv').exists():
            last=n.pin(usb_ready[1],'Q');b=BooleanDiagram([last])
            for p in g.group('u_runtime','usb_divider',16):
                zero_ff(n,g,p,'usb_clk')
                require(b.net(g,n.pin(p,'CLEAR'))==b.invert(b.inputs[last]),
                        'telemetry functional divider bypasses local release '+p)
        runtime='u_managed/runtime'
        preset_rows.append(prove_asserted_release(n,g,
            g.group(runtime,'cpu_pcm.switch_inhibit_compute',2),'audio_clk',
            n.pin(g.register(runtime,'cpu_pcm.switch_inhibit_50'),'Q'),
            n.pin(g.register(runtime,'compute_release',2),'Q')))
        preset_rows.append(prove_asserted_release(n,g,
            g.group(runtime,'pcm_hold_serial',2),'dac_mclk_d',
            n.canonical(runtime,'pcm_serial_hold'),
            n.pin(g.register(runtime,'serial_common_release',2),'Q')))
    compute=None
    if role=='M':
        from tools.workstation_tf_compute_local_release import audit_mapped
        compute=audit_mapped(n,stage=stage)
    selected=[p+'/CLEAR'for row in rows for p in row['registers']]
    if compute is not None:
        selected.extend(p+'/CLEAR'for p in compute['root_asserted_synchronizer_registers'])
    require(len(selected)==len(set(selected)),'duplicate release selector')
    sdc='\n# '+POLICY+'\nset_false_path -to [get_pins {'+' '.join(selected)+'}]\n'
    preset_selected=[p+'/PRESET'for row in preset_rows for p in row['registers']]
    if preset_selected:
        sdc+='set_false_path -to [get_pins {'+' '.join(preset_selected)+'}]\n'
    routed_first=None
    m_first=None
    if role=='M':
        # A9: the asynchronous publisher was still checked against the first
        # owner observer. Its exact three-stage equation and complete early-Q
        # fanout have just been proved; later stages remain finitely timed.
        m_first=dict(owner_live=owner_proof,idle=idle_proof,command_ack=ack_proof,
            functional_payload_exceptions_added=False)
        sdc+='\n# M A9 isolated owner-live observer\n'
        gray_rows,gray_lines=fifo_read_gray(n,g,'u_task3_m_score_push_cdc','usb_clk','clk_50m',all_bits=True)
        m_first['score_read_gray']=gray_rows
        sdc+='\n'+'\n'.join(gray_lines)+'\n'
        for chain in (owner,idle,ack):
            sdc+='set_false_path -to [get_pins {'+chain[0]+'/D}]\n'
            for first,last in zip(chain,chain[1:]):
                sdc+='set_max_delay 2.000 -from [get_pins {'+first+'/Q}] -to [get_pins {'+last+'/D}]\n'
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
                asserted_hold_release_chains=preset_rows,exact_PRESET_pins=preset_selected,
                tf_compute_functional_reset=compute,
                W_routed_first_captures=routed_first,
                M_routed_first_captures=m_first,
                functional_reset_exceptions_added=False,functional_setup_hold_unchanged=True,
                physical_CDC_accepted=False,hardware_tested=False),sdc
