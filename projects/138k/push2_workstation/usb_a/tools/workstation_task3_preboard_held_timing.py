"""Finite timing for paired F808 and M PANIC mailboxes, with hold retained."""
from tools.workstation_runtime_pcm_cdc import Graph,BooleanDiagram
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
        if row['id'] not in ('F808_request','F808_response'):continue
        for field,region in (('source',DDR_FAR_LAUNCH_REGION),('capture',DDR_FAR_CAPTURE_REGION)):
            for pin in row[field]:
                path=pin.rsplit('/',1)[0]
                require(path not in seen and ('"'+path+'"').encode() not in cst,
                        'duplicate or preconstrained held endpoint '+path)
                seen.add(path);lines.append(f'INS_LOC "{path}" {region};')
                rows.append(dict(register=path,region=region,mailbox=row['id'],side=field))
    require(len(rows)==164, 'incomplete F808 placement inventory')
    selected=cst+('\n# Proved F808 held data separation; all timing retained\n'+'\n'.join(lines)+'\n').encode()
    return selected,dict(policy='task3_F808_exact_held_endpoint_separation_v1',registers=rows,
        before_cst_sha256=digest(cst),after_cst_sha256=digest(selected),
        payload_hold_checks_retained=True,clocks_changed=False,routed_timing_verified=False)


def w_native_placement(cst,n):
    """Bound B7's tag-to-client round trips and separate observed short data.

    The actual failed path had 13.235ns of wire across R13..96/C26..167.
    Keep this native DDR service and its two consumers in one broad region.
    Preserve every timing check and every same-edge fault equation. The raw
    command/completion placements address their observed short hold paths;
    no timing exception is added for a payload or functional reset.
    """
    from tools.workstation_custom_board_implementation import digest
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
    completion=[]
    for stem,width in [('completion_generation',32),('completion_committed',32),
                       ('completion_kind',2),('completion_code',4)]:
        completion+=g.group(scope,stem,width)
    select(completion,'R[85:95]C[85:100]','memory_clk')
    select(g.group(scope,'accepted_frames_o',32)+[g.register(scope,'memory_drained')],
           'R[45:55]C[20:35]','clk_50m')
    require(len(overrides)==280,'W held data layout inventory changed')
    # P&R absorbs five of the synthesis INV cells into primitive polarity.
    # Constrain only placeable logic/registers; INV locality is not required
    # for this floorplan, and all data/control timing checks remain active.
    kinds={'DFFCE','DFFPE','DFFRE','LUT2','LUT3','LUT4','ALU',
           'MUX2_LUT5','MUX2_LUT6','MUX2_LUT7','MUX2_LUT8'}
    groups=[];selected={}
    for prefix,count in [('u_task3_media/memory/u_arbiter/',2672),
                         ('u_task3_media/raw_store/',4685),
                         ('u_managed/runtime/delay_dma/',1773)]:
        paths=sorted(p for p,c in n.cells.items()if p.startswith(prefix)and c['kind']in kinds)
        require(len(paths)==count,'W native B7 primitive inventory changed '+prefix)
        groups.append(dict(scope=prefix,primitive_count=count))
        for p in paths:
            require(('"'+p+'"').encode()not in cst,'preconstrained W native primitive '+p)
            selected[p]=overrides.get(p,'R[45:100]C[20:110]')
    require(set(overrides)<=set(selected),'W held data is outside native layout inventory')
    lines=[f'INS_LOC "{p}" {region};'for p,region in sorted(selected.items())]
    added=('\n# W B7 tag/native-client locality; all timing retained\n'+'\n'.join(lines)+'\n').encode()
    result=cst+added
    return result,dict(policy='task3_W_B7_native_wire_and_held_locality_v2',groups=groups,
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
    for row in rows:
        path='-from [get_pins {'+' '.join(row['source'])+'}] -to [get_pins {'+' '.join(row['capture'])+'}]'
        lines.extend(['set_max_delay 10.000 '+path,'set_min_delay 1.800 '+path])
    return dict(policy='task3_exact_pair_held_min1p8_max10_v1',role=role,payloads=rows,
        toggle_chains=chains,hold_checks_retained=True,functional_reset_exceptions_added=False,
        routed_timing_verified=False,hardware_tested=False),'\n# Paired F808/PANIC finite data and isolated toggle synchronizers\n'+'\n'.join(lines)+'\n'
