"""Exact reversible paired M stage selection; no historical provider changes."""
from pathlib import Path
import hashlib,json,re,subprocess
POLICY='task3_m_paired_exact_top_composition_v1'
NAME='custom138k-workstation-task3-m-paired-v1'
PROVIDER='rtl/workstation/workstation_profile_task3_m_paired.sv'
REFERENCE='rtl/workstation/workstation_task3_m_paired_top_reference.json'
BOARD='rtl/workstation/workstation_task3_m_paired_board.svh'
BATCH_PROVIDER='rtl/workstation/workstation_profile_task3_m_paired_phone_batch.sv'
SYNC_PROVIDER='rtl/workstation/workstation_profile_task3_m_paired_sync_storage.sv'
SYNC_POLICY='sync_score_and_final_tap_prefetch_v1'
TERMINAL_POLICY='task3_m_one_slot_terminal_validation_v1'
PHONE_WINDOW_PROVIDER='rtl/workstation/workstation_profile_task3_m_paired_phone_blocks.sv'
BATCH_MEDIA_POLICY='task3_pcm_block6_credit8_phone_window5_atomic_snapshot_batch_v3'
BATCH_POLICY='full_key_atomic_owner_snapshot_command_v1'
PARENT_TOP_SHA256='4b4a99f674a7033b032a3e82b98e553d7d7675689627ca4fb0cebf9746738d0f'
REFERENCE_SHA256='e1af8daa488fbb704a7fd3fdc04b4b0fae89bdbcbe531643d3f2f97cbcd5e473'
SOURCES=('rtl/workstation/workstation_task3_m_bus_endpoint.sv',
 'rtl/music/workstation_task3_tf_analysis_source.sv','rtl/music/workstation_task3_score_commit_m.sv',
 'rtl/workstation/workstation_task3_final_tap_export.sv','rtl/workstation/workstation_task3_phone_command_ingress.sv',
 'rtl/workstation/workstation_task3_phone_command_mux.sv',
 'rtl/workstation/workstation_task3_phone_window_rx.sv',
 'rtl/workstation/workstation_task3_phone_batch_m.sv')
MAINTAINED_UPDATES=('rtl/workstation/workstation_runtime_controlled.sv',
 'rtl/workstation/workstation_runtime_audio.sv','rtl/audio/workstation_ae350_pcm_owner.sv',
 'rtl/tf_audio/workstation_tf_direct_runtime_service.sv')
DEPENDENCIES=('tools/workstation_task3_m_paired_profile.py',PROVIDER,REFERENCE,BOARD,
 'tools/workstation_task3_identity_compare.py',
 'tools/workstation_task3_phone_identity_compare.py',
 'tools/workstation_task3_demand_identity_compare.py',
 'tools/workstation_task3_capture_compare.py',
 'rtl/workstation/task3_paired_channels.vh','rtl/workstation/workstation_runtime_controlled.sv',
 'rtl/workstation/workstation_runtime_audio.sv','rtl/audio/workstation_ae350_pcm_owner.sv',
 'rtl/tf_audio/workstation_tf_direct_runtime_service.sv',
 BATCH_PROVIDER,PHONE_WINDOW_PROVIDER,SYNC_PROVIDER)
def digest(s):return hashlib.sha256(s.encode() if isinstance(s,str) else s).hexdigest()
def reference(root):
 payload=(Path(root)/REFERENCE).read_bytes()
 if digest(payload)!=REFERENCE_SHA256:raise ValueError('M paired reference identity drift')
 d=json.loads(payload)
 if d.get('schema')!=1 or d.get('policy')!=POLICY or d.get('parent_sha256')!=PARENT_TOP_SHA256:raise ValueError('M paired reference schema/parent drift')
 return d
def apply_top(root,text):
 d=reference(root)
 if digest(text)!=d['parent_sha256']:raise ValueError('M paired input top identity drift')
 for row in d['edits']:
  if text.count(row['parent'])!=1:raise ValueError('M paired forward anchor drift')
  text=text.replace(row['parent'],row['selected'],1)
 if digest(text)!=d['selected_sha256']:raise ValueError('M paired selected top identity drift')
 return text
def inverse_top(root,text):
 if 'WORKSTATION_TASK3_M_PAIRED' not in text:return text
 if '`include "'+BOARD+'"' not in text:raise ValueError('M paired board include missing')
 selected=text
 d=reference(root)
 if digest(text)!=d['selected_sha256']:raise ValueError('M paired selected identity drift')
 for row in reversed(d['edits']):
  if text.count(row['selected'])!=1:raise ValueError('M paired inverse anchor drift')
  text=text.replace(row['selected'],row['parent'],1)
 if digest(text)!=d['parent_sha256'] or apply_top(root,text)!=selected:raise ValueError('M paired inverse identity drift')
 return text

def selected_batch_source_evidence(root,stage,configuration,provider):
    """Prove explicit batch selection and the real M snapshot/reset bindings."""
    media=configuration.get('interboard_media_policy')
    batch=configuration.get('phone_batch_policy')
    sync=configuration.get('m_endpoint_storage_policy')
    terminal=configuration.get('m_score_terminal_policy')
    from tools import workstation_task3_m_phone_lease_source as lease_source
    from tools import workstation_task3_tf_tail_reset as tail_reset
    from tools import workstation_task3_demand_identity_compare as demand_identity
    registered_lease=lease_source.configured(configuration)
    local_tail=tail_reset.configured(configuration)
    grouped_demand=demand_identity.configured(configuration)
    from tools import workstation_task3_capture_compare as capture_compare
    grouped_capture=capture_compare.configured(configuration)
    selected_sync=provider==SYNC_PROVIDER
    if (sync==SYNC_POLICY)!=selected_sync or sync not in (None,SYNC_POLICY):
        raise ValueError('M synchronous storage requires its explicit provider and policy')
    if terminal not in (None,TERMINAL_POLICY) or terminal is not None and not selected_sync:
        raise ValueError('M terminal pipeline requires its explicit synchronous policy')
    requested=provider in (BATCH_PROVIDER,SYNC_PROVIDER) or media==BATCH_MEDIA_POLICY or batch is not None
    if not requested:return None
    if provider not in (BATCH_PROVIDER,SYNC_PROVIDER) or media!=BATCH_MEDIA_POLICY or batch!=BATCH_POLICY:
        raise ValueError('M phone batch requires its exact provider and both explicit policies')
    root,stage=Path(root),Path(stage)
    files=(BATCH_PROVIDER,PHONE_WINDOW_PROVIDER,BOARD,
           'rtl/workstation/workstation_runtime_controlled.sv',
           'rtl/workstation/workstation_runtime_audio.sv',
           'rtl/audio/workstation_ae350_pcm_owner.sv',
           'rtl/workstation/workstation_task3_m_bus_endpoint.sv',
           'rtl/workstation/workstation_task3_phone_batch_m.sv')
    if selected_sync:
        files+= (SYNC_PROVIDER,'rtl/music/workstation_task3_score_commit_m.sv',
                  'rtl/workstation/workstation_task3_final_tap_export.sv')
    hashes={}
    for relative in files:
        source=(root/relative).read_bytes();selected=(stage/relative).read_bytes()
        compared=selected
        if relative==tail_reset.RUNTIME and local_tail:
            compared=tail_reset.native(relative,selected.decode()).encode()
            source=tail_reset.native(relative,source.decode()).encode()
        if relative==demand_identity.ENDPOINT and grouped_demand:
            compared=demand_identity.native(selected.decode()).encode()
            source=demand_identity.native(source.decode()).encode()
        if relative==capture_compare.SOURCE and grouped_capture:
            compared=capture_compare.native(selected.decode()).encode()
            source=capture_compare.native(source.decode()).encode()
        if relative==BOARD and registered_lease:
            compared=lease_source.restore(selected.decode()).encode()
            if digest(source)!=lease_source.PARENT_SHA256:
                source=lease_source.restore(source.decode()).encode()
        if source!=compared:raise ValueError('M phone batch maintained input differs: '+relative)
        hashes[relative]=digest(selected)
    def compact(text):return ''.join(re.sub(r'//[^\n]*|/\*.*?\*/','',text,flags=re.S).split())
    def exact(text,anchor,label):
        if compact(text).count(compact(anchor))!=1:
            raise ValueError('M phone batch '+label+' drift')
    if selected_sync:
        wrapper='''`define WORKSTATION_TASK3_M_SYNC_STORAGE
`include "rtl/workstation/workstation_profile_task3_m_paired_phone_batch.sv"
`undef WORKSTATION_TASK3_M_SYNC_STORAGE'''
        if compact((stage/SYNC_PROVIDER).read_text())!=compact(wrapper):
            raise ValueError('M synchronous storage wrapper scope drift')
    wrapper='''`define WORKSTATION_TASK3_PHONE_BATCH
`include "rtl/workstation/workstation_profile_task3_m_paired_phone_blocks.sv"
`undef WORKSTATION_TASK3_PHONE_BATCH'''
    if compact((stage/BATCH_PROVIDER).read_text())!=compact(wrapper):
        raise ValueError('M phone batch wrapper macro/include scope drift')
    macros=('WORKSTATION_TASK3_PHONE_WINDOW_BLOCK','WORKSTATION_TASK3_M_PAIRED','WORKSTATION_AE350_PCM',
            'WORKSTATION_NO_BLUETOOTH','WORKSTATION_NO_LOCAL_PANEL','WORKSTATION_NO_CNN',
            'WORKSTATION_TF_MENU_WITHOUT_CNN','WORKSTATION_TF_DIRECT_NATIVE',
            'WORKSTATION_DEMO_NO_LOCAL_RECORD','WORKSTATION_DEMO_NO_LOCAL_SCORE')
    wrapper='\n'.join('`define '+m for m in macros)+'\n`include "rtl/workstation/workstation_profile_runtime.sv"\n'+\
            '\n'.join('`undef '+m for m in reversed(macros))
    if compact((stage/PHONE_WINDOW_PROVIDER).read_text())!=compact(wrapper):
        raise ValueError('M phone batch included window provider scope drift')
    top_path=stage/'rtl/workstation/gw138k_push_workstation_top.v'
    top=top_path.read_text()
    # Later independently audited CPU-memory adaptations may change the final
    # top hash. Retain every frozen paired binding without claiming that this
    # final stage is the earlier apply_top intermediate byte identity.
    frozen=reference(root)
    for row in frozen['edits']:
        if top.count(row['selected'])!=1:
            raise ValueError('M phone batch frozen paired binding drift')
    prepared=subprocess.run(['iverilog','-g2012','-E','-I.','-o','-',provider],
                            cwd=stage,capture_output=True,text=True,timeout=30)
    if prepared.returncode:raise ValueError('M phone batch provider preprocessing failed: '+prepared.stderr)
    matches=re.findall(r'\bmodule\s+workstation_custom_138k_top\b.*?\bendmodule\b',prepared.stdout,re.S)
    if len(matches)!=1:raise ValueError('M phone batch actual top must be unique')
    top=matches[0]
    lease=lease_source.selection(stage,configuration,top)
    from tools.workstation_task3_identity_compare import selection as identity_selection
    identity=identity_selection(stage,configuration,top,sync_selected=selected_sync)
    from tools.workstation_task3_phone_identity_compare import selection as phone_identity_selection
    phone_identity=phone_identity_selection(stage,configuration,top,sync_selected=selected_sync)
    demand=demand_identity.evidence(stage,configuration)
    capture=capture_compare.evidence(stage,configuration)
    storage_binding="defparam u_task3_m_endpoint.SYNC_READ_STORAGE=1'b1;"
    if selected_sync:
        exact(top,storage_binding,'synchronous endpoint storage binding')
        endpoint=(stage/'rtl/workstation/workstation_task3_m_bus_endpoint.sv').read_text()
        exact(endpoint,"parameter bit SYNC_READ_STORAGE=1'b0",'storage default off')
        score_binding=('workstation_task3_score_commit_m #(.SYNC_READ_STORAGE(SYNC_READ_STORAGE)) collector_m('
            if terminal is None else 'workstation_task3_score_commit_m #(.SYNC_READ_STORAGE(SYNC_READ_STORAGE),.PIPELINED_TERMINAL(SYNC_READ_STORAGE)) collector_m(')
        exact(endpoint,score_binding,'score storage/terminal binding')
        exact(endpoint,'workstation_task3_final_tap_export #(.SYNC_READ_STORAGE(SYNC_READ_STORAGE)) recording(','tap storage binding')
    elif compact(storage_binding) in compact(top):
        raise ValueError('unselected M synchronous storage binding')
    for anchor,label in [
        ("localparam bit TASK3_PHONE_BATCH=1'b1;",'selected board policy'),
        ("localparam bit TASK3_PHONE_WINDOW_BLOCK=1'b1;",'selected window policy'),
        ("defparam u_managed.PCM_SNAPSHOT_ENABLE=1'b1;",'exact forward snapshot binding'),
        ("workstation_task3_m_bus_endpoint #(.BLOCK_PCM(1'b1),.PHONE_WINDOW_BLOCK(TASK3_PHONE_WINDOW_BLOCK),.PHONE_BATCH(TASK3_PHONE_BATCH)) u_task3_m_endpoint(",'actual endpoint binding'),
        ('gw138k_apb_cdc u_task3_m_pcm_commands(\n.reset_n(runtime_common_reset_n && (!TASK3_PHONE_BATCH || '+('task3_m_phone_live_source' if registered_lease else 'task3_m_phone_live')+')),','observer-only lease reset'),
        ('.remote_pcm_owner_ready_i(task3_m_pcm_reset && task3_m_owner_live_sync[2]),','owner observer readiness'),
        ('.REMOTE_PCM_COMMAND_ENABLE(1)','same real remote owner')]:
        exact(top,anchor,label)
    runtimes=re.findall(r'\bworkstation_runtime_controlled\s*#\(.*?\)\s*u_managed\s*\(.*?\);',top,re.S)
    if len(runtimes)!=1:raise ValueError('M phone batch actual controlled runtime must be unique')
    exact(runtimes[0],'.rst_ni(runtime_reset_n),.common_reset_ni(runtime_common_reset_n),','common owner root')
    controlled=(stage/'rtl/workstation/workstation_runtime_controlled.sv').read_text()
    audio=(stage/'rtl/workstation/workstation_runtime_audio.sv').read_text()
    owner=(stage/'rtl/audio/workstation_ae350_pcm_owner.sv').read_text()
    for text,anchor,label in [
        (controlled,'parameter bit PCM_SNAPSHOT_ENABLE=0','controlled default off'),
        (controlled,'.PCM_SNAPSHOT_ENABLE(PCM_SNAPSHOT_ENABLE)','controlled to audio parameter'),
        (controlled,'assign pcm_owner_reset=reset_compute_n && remote_pcm_owner_ready_i;','observer ready only'),
        (audio,'parameter bit PCM_SNAPSHOT_ENABLE=0','audio default off'),
        (audio,'workstation_ae350_pcm_owner #(.SUSTAINED_VERIFIED(D_ONLY_ENABLE),.SNAPSHOT_ENABLE(PCM_SNAPSHOT_ENABLE)) owner(','audio to owner parameter'),
        (audio,'.clk_i(compute_clk_i),.reset_ni(compute_reset_n),.cpu_ready_i(pcm_cpu_ready_i),','owner root independent of observer'),
        (owner,'parameter bit SNAPSHOT_ENABLE=0','owner default off'),
        (owner,'end else if(!cpu_ready_i)begin\nvalid<=0;\nend else if(capture)begin','observer reset retains capture ID'),
        (owner,'last_controller<=staged_controller;last_generation<=staged_generation;last_stream<=staged_stream;','real retired stream key')]:
        exact(text,anchor,label)
    if re.search(r'defparam\s+u_managed\.(?!PCM_SNAPSHOT_ENABLE\s*=)',top):
        raise ValueError('M phone batch adds an unrelated runtime defparam')
    result=dict(selected_policy=BATCH_POLICY,interboard_media_policy=BATCH_MEDIA_POLICY,
        compilation_provider=provider,source_sha256=hashes,
        actual_preprocessed_provider_sha256=digest(prepared.stdout),
        prepared_top_sha256=digest(top_path.read_bytes()),
        frozen_paired_reference_sha256=REFERENCE_SHA256,
        snapshot_parameter_chain='u_managed.PCM_SNAPSHOT_ENABLE -> runtime.PCM_SNAPSHOT_ENABLE -> cpu_pcm.owner.SNAPSHOT_ENABLE',
        owner_reset='compute_reset_n; observer revocation changes cpu_ready only',
        observer_APB_reset='runtime_common_reset_n && (!TASK3_PHONE_BATCH || task3_m_phone_live)',
        actual_endpoint_PHONE_BATCH=True,atomic_owner_snapshot=True,default_enabled=False,
        physical_CDC_accepted=False,routed_timing_verified=False,hardware_accepted=False)
    if lease is not None:
        result['lease_source']=lease
        result['observer_APB_reset']='runtime_common_reset_n && (!TASK3_PHONE_BATCH || task3_m_phone_live_source)'
    if selected_sync:
        result['local_storage']=dict(policy=SYNC_POLICY,score_capacity_notes=2048,
            tap_capacity_frames=256,synchronous_read=True,held_prefetch=True,
            tap_write_forwarding=True,score_initial_read_cycles=1,
            continuous_read_frames_per_cycle=1,physical_BSRAM_mapping_verified=False)
        if terminal is not None:
            result['local_storage']['terminal_commit']=dict(policy=TERMINAL_POLICY,
                queue_slots=1,extra_validation_cycles=1,shared_result_backpressure_cycles=1,
                pending_payload_reset_free=True,revoked_by=['reset','cancel','PANIC','link_loss'],
                independent_audio_schedule_unchanged=True)
        if identity is not None:
            result['local_storage']['identity_comparison']=identity
        if phone_identity is not None:
            result['local_storage']['phone_identity_comparison']=phone_identity
        if demand is not None:
            result['local_storage']['demand_identity_comparison']=demand
        if capture is not None:
            result['local_storage']['capture_comparison']=capture
    return result
