"""Finite timing for paired F808 and M PANIC mailboxes, with hold retained."""
from tools.workstation_runtime_pcm_cdc import Graph,BooleanDiagram,COMB
from tools.workstation_task3_native_held import zero_ff
from tools.workstation_recording_phase1_cdc import complete_closure
from tools.workstation_native_protocol_audit import audit_apb_held_boundary
from tools.workstation_task3_m_session_boundary import frontier,KeyDiagram

def require(ok,message):
    if not ok:raise ValueError('paired held timing: '+message)


def placement(cst, proof):
    """Separate the proved F808 held endpoints; retain finite min/max timing.

    B6 placed direct Q-to-D payloads together, giving 0.36ns against 1.8ns
    plus clock skew. Only mailbox data FFs move; no clock or false-path changes.
    The full source/capture proof must precede this physical selection.
    """
    from tools.workstation_custom_board_implementation import (
        DDR_FAR_LAUNCH_REGION, DDR_FAR_CAPTURE_REGION, digest)
    require(proof['hold_checks_retained'] is True, 'placement requires held proof')
    rows=[];lines=[];seen=set()
    for row in proof['payloads']:
        if row['id'] not in ('F808_request','F808_response','PANIC_epoch','M_PCM_response','M_PCM_request'):continue
        regions=(DDR_FAR_LAUNCH_REGION,DDR_FAR_CAPTURE_REGION)
        # The M complete design occupies 88% of CLS; its 82 F808 FFs shared
        # the 49-site DDR launch corner with the initialization/reset cells.
        # Both P2R0 and bounded P2R1 failed detailed routing. Give only F808
        # more room at the same opposite corners; keep DDR and PCM placement,
        # every data min/max limit, and routed hold checks unchanged.
        if proof['role']=='M' and row['id']in('F808_request','F808_response'):
            regions=('R[96:110]C[164:181]','R[2:16]C[2:28]')
        # A10 put 174 data FFs at each 49-CFU corner and failed to route.
        # Keep the previously routed F808 corners; place the additional M
        # mailboxes in their own regions, with opposite PCM directions sharing
        # domain-local regions. Finite payload min/max and hold stay active.
        # A11 routed these payloads with ~1ns data flight against the retained
        # 1.8ns minimum plus ~2ns clock skew. Use two broad, opposite regions
        # for the additional M mailboxes; keep F808's routed corner policy.
        if row['id']in('PANIC_epoch','M_PCM_request'):
            regions=('R[15:25]C[140:155]','R[75:85]C[20:35]')
        if row['id']=='M_PCM_response':regions=('R[75:85]C[20:35]','R[15:25]C[140:155]')
        for field,region in zip(('source','capture'),regions):
            for pin in row[field]:
                path=pin.rsplit('/',1)[0]
                require(path not in seen and ('"'+path+'"').encode() not in cst,
                        'duplicate or preconstrained held endpoint '+path)
                seen.add(path);lines.append(f'INS_LOC "{path}" {region};')
                rows.append(dict(register=path,region=region,mailbox=row['id'],side=field))
    expected=348 if proof['role']=='M' else 164
    require(len(rows)==expected, 'incomplete paired held placement inventory')
    selected=cst+('\n# Proved paired held data separation; all timing retained\n'+'\n'.join(lines)+'\n').encode()
    return selected,dict(policy=('task3_M_F808_corner_capacity_v5'if proof['role']=='M'
                                 else'task3_exact_held_endpoint_separation_v3'),registers=rows,
        before_cst_sha256=digest(cst),after_cst_sha256=digest(selected),
        payload_hold_checks_retained=True,clocks_changed=False,routed_timing_verified=False)


def w_native_placement(cst,n,*,publication=False,terminal=False,tuple_cofactor=False,pack_cofactor=False,native_fault_cofactor=False,identity_bytes=False,fetch_range=False,fetch_end_capture=False,registered_tx_class=False,fifo_compare_first=False):
    """Bound B7's tag-to-client round trips and separate observed short data.

    The actual failed path had 13.235ns of wire across R13..96/C26..167.
    Keep its exact tag-return causal cone in one bounded local region.
    Preserve every timing check and every same-edge fault equation. The raw
    command/completion placements address their observed short hold paths;
    no timing exception is added for a payload or functional reset.
    """
    from tools.workstation_custom_board_implementation import digest
    require(not terminal or publication,'W terminal layout requires completion publication')
    require(not tuple_cofactor or terminal,'W tuple layout requires terminal cofactor')
    require(not pack_cofactor or tuple_cofactor,'W pack layout requires tuple cofactor')
    require(not native_fault_cofactor or pack_cofactor,'W native fault layout requires pack cofactor')
    require(not identity_bytes or native_fault_cofactor,'W key-byte layout requires native fault cofactor')
    require(not fetch_range or identity_bytes,'W parallel fetch range requires reviewed byte identities')
    require(not fetch_end_capture or fetch_range,'W captured end requires reviewed parallel fetch range')
    require(not registered_tx_class or fetch_end_capture,'W registered TX layout requires captured-end composition')
    publication_proof=None
    if publication:
        from tools.workstation_ble_completion_publication import audit_mapped
        publication_proof=audit_mapped(n)
    g=Graph(n);scope='u_task3_media/raw_store';overrides={}
    def select(paths,region,clock):
        for p in paths:
            require(p not in overrides,'duplicate W layout register '+p)
            require(n.pin(p,'CLK')==clock,'W layout register clock changed '+p)
            overrides[p]=region
    command=[]
    for stem,width in [('command_event_target',9),('command_length',13),
                       ('command_offset',32),('command_generation',32),('command_kind',2)]:
        command+=g.group(scope,stem,width)
    select(command,'R[25:35]C[35:50]','clk_50m')
    select(g.group(scope,'g_command_capture.payload',89),'R[45:55]C[65:80]','memory_clk')
    if fetch_end_capture:
        select(g.group(scope,'g_command_capture.fetch_end',33),'R[45:55]C[65:80]','memory_clk')
    completion=[]
    for stem,width in [('completion_generation',32),('completion_committed',32),
                       ('completion_kind',2),('completion_code',4)]:
        completion+=g.group(scope,stem,width)
    select(completion,'R[85:95]C[85:100]','memory_clk')
    select(g.group(scope,'accepted_frames_o',32)+[g.register(scope,'memory_drained')],
           'R[45:55]C[20:35]','clk_50m')
    require(len(overrides)==(313 if fetch_end_capture else 280),'W held data layout inventory changed')
    # P&R absorbs five of the synthesis INV cells into primitive polarity.
    # Constrain only placeable logic/registers; INV locality is not required
    # for this floorplan, and all data/control timing checks remain active.
    kinds={'DFFCE','DFFPE','DFFRE','LUT2','LUT3','LUT4','ALU',
           'MUX2_LUT5','MUX2_LUT6','MUX2_LUT7','MUX2_LUT8'}
    groups=[];reviewed=set()
    # Full publication mapping reviewed separately: 34 new raw FFs; local
    # LUT factoring changes the arbiter by +1 and DMA by -2. No region grows.
    # The terminal cofactor rebuild changes only these reviewed broad
    # inventories. Its actual tag-return cone remains the same74 cells.
    # The complete ACK-byte rebuild absorbs two raw-store LUTs. Both exact
    # compiler identities retain the same selected tag/held causal inventory.
    # The selected pack/fetch cofactor adds 33 raw-store primitives. Its
    # independently reviewed tag-return cone adds read_outstanding_s4 only.
    # Retain all earlier inventories for candidates without that selection.
    tuple_counts=(2670,4871,1790) if pack_cofactor else (2670,4838,1790)
    # The parallel fetch comparison changes only 26 combinational primitives;
    # all 2175 raw FFs and both other owner inventories remain unchanged.
    # The captured-end rebuild adds exactly 33 raw FFs to the real inventory;
    # keep the exact earlier mapping for every retained uncaptured candidate.
    # v79 registered TX selection refactors shared gates in these unchanged
    # owners. Keep this exact mapping separate from every retained recipe.
    require(not fifo_compare_first or registered_tx_class,'FIFO-first layout requires registered W TX class')
    counts=(2669,4944,1791) if fifo_compare_first else (2669,4957,1788) if registered_tx_class else (2674,4979,1780) if fetch_end_capture else (2674,4946,1780) if fetch_range else (2674,4920,1780) if identity_bytes else (2669,4888,1790) if native_fault_cofactor else tuple_counts if tuple_cofactor else(2673,4724,1778)if terminal else(2673,4700,1771)if publication else(2672,4685,1773)
    for prefix,count in zip(['u_task3_media/memory/u_arbiter/',
                             'u_task3_media/raw_store/',
                             'u_managed/runtime/delay_dma/'],counts):
        paths=sorted(p for p,c in n.cells.items()if p.startswith(prefix)and c['kind']in kinds)
        require(len(paths)==count,'W native B7 primitive inventory changed '+prefix)
        groups.append(dict(scope=prefix,primitive_count=count))
        for p in paths:
            require(('"'+p+'"').encode()not in cst,'preconstrained W native primitive '+p)
            reviewed.add(p)
    require(set(overrides)<=reviewed,'W held data is outside native layout inventory')
    # B9 and B11 both expanded the broad per-object allowed-placement sets
    # beyond 124 GB, including GROUP form. Target only B7's actual tag-return
    # causal cone and the previously proved held FFs; leave unrelated logic to
    # the placer. Never disable timing or constrain absorbed inverter names.
    tag_scope='u_task3_media/memory/u_arbiter/g_recording.u_core'
    tags=[g.register(tag_scope,f'g_recording.tags[{slot}]',bit)
          for slot in range(32)for bit in range(4)]
    require({p for p in g.regs if p.startswith(tag_scope+'/g_recording.tags[')}==set(tags),
            'W exact authoritative tag inventory changed')
    delay=g.group('u_managed/runtime/delay_dma','rsp_hold',256)+[
        g.register('u_managed/runtime/delay_dma','read_outstanding')]
    for p in tags+delay:
        require(n.pin(p,'CLK')=='memory_clk','W tag-return clock changed '+p)
    forward=set();seen=set();todo=[n.pin(p,'Q')for p in tags]
    while todo:
        net=todo.pop()
        if net in seen:continue
        seen.add(net)
        for p,pin,role in g.fan[net]:
            if role=='comb':
                forward.add(p);todo.extend(n.pin(p,out)for out in COMB[n.cells[p]['kind']])
    backward=set();seen=set();todo=[n.pin(p,pin)for p in delay for pin in ('D','CE')]
    while todo:
        net=todo.pop()
        if net in seen:continue
        seen.add(net)
        for p,pin in g.drivers[net]:
            kind=n.cells[p]['kind']
            if kind in COMB:
                backward.add(p);todo.extend(n.pin(p,port)for port in n.cells[p]['ports']if port not in COMB[kind])
    cone=forward&backward
    # The selected rebuild absorbs two DMA n6315 LUTs and renames one slot
    # LUT. The same 128 tag Qs and 257 return FFs bound the actual causal cone.
    cone_count=75 if registered_tx_class else 76 if identity_bytes else 75 if pack_cofactor else 74 if publication else 76
    require(len(cone)==cone_count and {n.cells[p]['kind']for p in cone}==
            {'LUT2','LUT3','LUT4','MUX2_LUT5','MUX2_LUT6'},'W tag-return causal cone changed')
    excluded=[];status_hold=[];local_controls=[]
    if native_fault_cofactor:
        # V17 routed this shared watchdog gate from C135 to C55 and back,
        # adding 6.318ns of wire. Keep its causal membership in the proof,
        # but allow the placer to serve its watchdog consumer locally.
        shared='u_managed/runtime/delay_dma/n420_s3' if fifo_compare_first or (identity_bytes and not registered_tx_class) else 'u_managed/runtime/delay_dma/n420_s2'
        require(shared in cone and n.cells[shared]['kind']=='LUT4' and
                n.cells[shared]['parameters']=={'INIT':"16'h0700"},
                'W diagnosed shared watchdog gate changed')
        if identity_bytes:
            # V18's ready path went from local native logic to remote DMA
            # state/watchdog logic and back to the local read-outstanding CE.
            # Bound those real register publishers with the causal gate;
            # moving the shared gate alone had only reversed the round trip.
            local_controls=[*g.group(tag_scope,'g_recording.read_pointer',5),
                *g.group('u_managed/runtime/delay_dma','state',4),
                g.register('u_managed/runtime/delay_dma','watchdog_reset_delay')]
            require(len(local_controls)==10 and all(n.pin(p,'CLK')=='memory_clk' for p in local_controls),
                    'W ready-path local control inventory changed')
        else:excluded=[shared]
        source=g.register(scope,'status_payload',4)
        capture=g.register(scope,'fetch_fault_o')
        require(n.pin(source,'CLK')=='memory_clk' and n.pin(capture,'CLK')=='clk_50m',
                'W observed status hold domains changed')
        # V18: status bit 4 at R85C94 reached the control capture at R45C24
        # in 2.886ns, leaving -0.335ns hold with the retained 1.8ns limit.
        # Increase only this mailbox source's physical separation.
        status_hold=[dict(register=source,region='R[96:105]C[110:125]' if identity_bytes else 'R[85:95]C[85:100]'),
                     dict(register=capture,region='R[45:55]C[20:35]')]
    selected={p:'R[50:70]C[55:80]'for p in (*tags,*delay,*sorted(cone-set(excluded)),*local_controls)}
    require(not(set(selected)&set(overrides)),'W held/critical placement overlaps')
    selected.update(overrides)
    for row in status_hold:
        require(row['register'] not in selected and row['register'] in reviewed,
                'W status separation inventory changed')
        selected[row['register']]=row['region']
    require(len(selected)==(785 if registered_tx_class else 786 if fetch_end_capture else 753 if identity_bytes else 741 if native_fault_cofactor else 740 if pack_cofactor else 739 if publication else 741),'W targeted placement inventory changed')
    regions=sorted(set(selected.values()));lines=[];placement_groups=[]
    for i,region in enumerate(regions):
        name=f'task3_w_native_{i}'
        require(name.encode() not in cst,'duplicate W native placement group')
        members=sorted(p for p,r in selected.items()if r==region)
        # The installed CST parser requires each GROUP statement on one
        # physical line (B10 rejected a newline before the first member).
        # The same-device two-FF probe passed syntax, P&R and region placement.
        lines.append('GROUP '+name+' = { '+' '.join('"'+p+'"'for p in members)+' };')
        lines.append(f'GRP_LOC {name} {region};')
        placement_groups.append(dict(name=name,region=region,primitive_count=len(members)))
    added=('\n# W B7 tag/native-client locality; all timing retained\n'+'\n'.join(lines)+'\n').encode()
    result=cst+added
    return result,dict(policy=('task3_W_registered_tx_captured_end_locality_v10'if registered_tx_class
                              else'task3_W_captured_end_and_key_bytes_locality_v9'if fetch_end_capture
                              else'task3_W_key_bytes_ready_publishers_and_status_locality_v8'if identity_bytes
                              else'task3_W_native_fault_shared_watchdog_and_status_locality_v7'if native_fault_cofactor
                              else'task3_W_B7_pack_tag_return_and_held_locality_v6'if pack_cofactor
                              else'task3_W_B7_publication_tag_return_and_held_locality_v5'if publication
                              else'task3_W_B7_exact_tag_return_and_held_locality_v4'),groups=groups,
        completion_publication=publication_proof,terminal_cofactor_layout=terminal,
        terminal_tuple_layout=tuple_cofactor,
        pack_cofactor_layout=pack_cofactor,
        **(dict(captured_fetch_end_layout=True) if fetch_end_capture else {}),
        **(dict(registered_tx_class_layout=True) if registered_tx_class else {}),
        native_fault_cofactor_layout=native_fault_cofactor,
        causal_cells_excluded_from_placement_only=excluded,
        ready_path_register_publishers=local_controls,
        observed_status_hold_separation=status_hold,
        placement_groups=placement_groups,historical_broad_primitive_review_count=len(reviewed),
        tag_return_cone=dict(source=tags,capture=delay,combinational_cells=sorted(cone)),
        broad_region_constraints_removed=True,
        primitive_count=len(selected),held_register_count=len(overrides),
        exact_constraints_sha256=digest(added),before_cst_sha256=digest(cst),
        after_cst_sha256=digest(result),same_edge_fault_logic_unchanged=True,
        payload_hold_checks_retained=True,clocks_changed=False,
        timing_exceptions_added=False,routed_timing_verified=False)


def audit(n,*,role):
    require(role in ('M','W'),'explicit role required');g=Graph(n);rows=[]
    apb=audit_apb_held_boundary(n,g,scope='u_task3_pair_link/config_cdc',destination_clock='clk_50m')
    scope='u_task3_pair_link/config_cdc'
    rows.append(dict(id='F808_request',source=[p+'/Q'for p in g.group(scope,'request_held',49)],
        capture=[p+'/D'for p in g.group(scope,'request_local',49)],proof=apb))
    rows.append(dict(id='F808_response',source=apb['source_pins'],capture=apb['capture_pins']))
    lines=[]
    def chain(scope,source,first,second,domain,third=None):
        first,second=g.register(scope,first),g.register(scope,second)
        for p in [first,second]:zero_ff(n,g,p,domain)
        require(n.pin(first,'D')==n.pin(source,'Q')and n.pin(second,'D')==n.pin(first,'Q')and
            n.pin(first,'CE')in g.high and n.pin(second,'CE')in g.high and
            n.pin(first,'CLEAR')==n.pin(second,'CLEAR'),'toggle chain changed')
        c=complete_closure(n,g,[first]);require(c['ff_endpoints']=={second+'/D':domain}and
            not c['primitive_endpoints']and not c['top_output_endpoints'],'toggle first extra consumer')
        lines.append('set_false_path -from [get_pins {'+source+'/Q}] -to [get_pins {'+first+'/D}]')
        lines.append('set_max_delay 2.000 -from [get_pins {'+first+'/Q}] -to [get_pins {'+second+'/D}]')
        if third:
            last=g.register(scope,third);zero_ff(n,g,last,domain)
            require(n.pin(last,'D')==n.pin(second,'Q')and n.pin(last,'CE')in g.high and
                n.pin(last,'CLEAR')==n.pin(second,'CLEAR'),'third stage changed')
            lines.append('set_max_delay 2.000 -from [get_pins {'+second+'/Q}] -to [get_pins {'+last+'/D}]')
        return dict(source=source,first=first,second=second,first_complete_closure=c)
    chains=[chain(scope,g.register(scope,'request_toggle'),'req_meta','req_sync','clk_50m','req_settled'),
            chain(scope,g.register(scope,'acknowledge_toggle'),'ack_meta','ack_sync','ram_clk','ack_settled')]
    if role=='M':
        scope='u_task3_m_panic_epoch';q=lambda stem:n.pin(g.register(scope,stem),'Q')
        source=g.group(scope,'held_data',10);capture=g.group(scope,'destination_data',10)
        req,ack=g.register(scope,'request_toggle'),g.register(scope,'acknowledge_toggle')
        chains.extend([chain(scope,req,'req_meta','req_sync','clk_50m','req_settled'),
                       chain(scope,ack,'ack_meta','ack_sync','audio_clk')])
        reqq,ackq=q('request_toggle'),q('ack_sync');enables={n.pin(p,'CE')for p in source}
        require(len(enables)==1,'panic source capture differs');ce=next(iter(enables))
        leaves=sorted(set([reqq,ackq]+frontier(n,g,[ce],{reqq,ackq})));b=KeyDiagram(leaves)
        require(b.both(b.net(g,ce),b.different(b.inputs[reqq],b.inputs[ackq]))==0,
            'panic held payload can overwrite while busy')
        nextreq=b.choose(b.net(g,n.pin(req,'CE')),b.net(g,n.pin(req,'D')),b.inputs[reqq])
        require(nextreq==b.different(b.inputs[reqq],b.net(g,ce)),'panic request publication differs')
        for p,s in zip(capture,source):
            zero_ff(n,g,p,'clk_50m');zero_ff(n,g,s,'audio_clk')
            bb=BooleanDiagram([q('req_settled'),q('acknowledge_toggle')]);expected=bb.different(*bb.inputs.values())
            require(n.pin(p,'D')==n.pin(s,'Q')and bb.net(g,n.pin(p,'CE'))==expected and
                n.pin(p,'CE')==n.pin(ack,'CE')and n.pin(ack,'D')==q('req_settled'),
                'panic capture data/ack/third stage changed')
        c=complete_closure(n,g,source);remote={p:d for p,d in c['ff_endpoints'].items()if d!='audio_clk'}
        require(remote=={p+'/D':'clk_50m'for p in capture}and not c['primitive_endpoints']and
            not c['top_output_endpoints'],'panic payload remote consumer changed')
        rows.append(dict(id='PANIC_epoch',source=[p+'/Q'for p in source],capture=[p+'/D'for p in capture],
            source_busy_prevents_overwrite=True,source_next_request_exact=True,source_complete_closure=c))
        pcm=audit_apb_held_boundary(n,g,scope='u_task3_m_pcm_commands',
            source_clock='clk_50m',destination_clock='audio_clk')
        rows.append(dict(id='M_PCM_response',source=pcm['source_pins'],
            capture=pcm['capture_pins'],proof=pcm))
        rows.append(dict(id='M_PCM_request',
            source=[p+'/Q'for p in g.group('u_task3_m_pcm_commands','request_held',49)],
            capture=[p+'/D'for p in g.group('u_task3_m_pcm_commands','request_local',49)],proof=pcm))
        chains.append(chain('u_task3_m_pcm_commands',
            g.register('u_task3_m_pcm_commands','request_toggle'),
            'req_meta','req_sync','audio_clk','req_settled'))
    for row in rows:
        path='-from [get_pins {'+' '.join(row['source'])+'}] -to [get_pins {'+' '.join(row['capture'])+'}]'
        lines.extend(['set_max_delay 10.000 '+path,'set_min_delay 1.800 '+path])
    return dict(policy='task3_exact_pair_held_min1p8_max10_v1',role=role,payloads=rows,
        toggle_chains=chains,hold_checks_retained=True,functional_reset_exceptions_added=False,
        routed_timing_verified=False,hardware_tested=False),'\n# Paired F808/PANIC finite data and isolated toggle synchronizers\n'+'\n'.join(lines)+'\n'
