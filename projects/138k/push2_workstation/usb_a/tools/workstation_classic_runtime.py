"""Explicit Classic CPU/HCI/PCM composition; reuses the existing ROM builder."""
from pathlib import Path
import hashlib,json,re,subprocess,shutil
from tools.ae350_local_memory import call_chain_report
POLICY='ae350_classic_runtime_failclosed_v1'
PROVIDER='rtl/workstation/workstation_profile_classic_runtime_v1.sv'
DEPENDENCIES=('tools/workstation_classic_runtime.py','tools/experiment_ae350_rom_split.py',
    'tools/ae350_classic_runtime_audit.py','firmware/ae350/boot_ilm_dlm_rom128_split.ld')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def firmware_inputs(root):
    # Explicit new profile alone locks this entire maintained/vendor inventory.
    return sorted(str(p.relative_to(root))for p in (Path(root)/'firmware/ae350').rglob('*')if p.is_file())
def decode_rom(path):
    words=Path(path).read_text().splitlines()
    if len(words)!=32768 or any(not re.fullmatch('[0-9a-fA-F]{8}',w)for w in words):
        raise ValueError('Classic runtime requires exact physical ROM128 image')
    return b''.join(int(w,16).to_bytes(4,'little')for w in words)
def cdc_bundle():
    """Scoped synthesis constraints; physical endpoint resolution is still due."""
    bridge='u_managed/pcm_apb/commands';session='u_managed/runtime/cpu_pcm/session'
    owner='u_managed/runtime/cpu_pcm/owner';runtime='u_managed/runtime'
    lines=[]
    def held(source,destination):
        lines.append('set_max_delay 10.000 -from [get_regs {'+source+'}] -to [get_regs {'+destination+'}]')
        lines.append('set_false_path -hold -from [get_regs {'+source+'}] -to [get_regs {'+destination+'}]')
    held(bridge+'/request_held*',bridge+'/request_local*')
    held(bridge+'/response_held*',bridge+'/response_local*')
    held('u_bluetooth/u_core/initializer/boot_id* u_bluetooth/u_core/owner/flow/generations* u_bluetooth/u_core/owner/flow/active* u_bluetooth/u_core/owner/flow/is_le*',session+'/epoch_o* '+session+'/generation_o*')
    for source,destination in [('request_toggle','req_meta'),('acknowledge_toggle','ack_meta')]:
        lines.append('set_false_path -from [get_regs {'+bridge+'/'+source+'*}] -to [get_pins {'+bridge+'/'+destination+'*/D}]')
    for first,second in [('req_meta','req_sync'),('ack_meta','ack_sync')]:
        lines.append('set_max_delay 2.000 -from [get_regs {'+bridge+'/'+first+'*}] -to [get_regs {'+bridge+'/'+second+'*}]')
    # Only explicit asynchronous close/reset pins are excepted. Payload is
    # bounded above; no audio clock or whole-domain false path is introduced.
    for pins in [session+'/release_pipe*/CLEAR '+session+'/live_o*/CLEAR',
        runtime+'/cpu_pcm/switch_inhibit_compute*/CLEAR',runtime+'/pcm_hold_serial*/CLEAR',
        bridge+'/p_release*/CLEAR '+bridge+'/a_release*/CLEAR',
        bridge+'/req_meta*/CLEAR '+bridge+'/req_sync*/CLEAR '+bridge+'/req_settled*/CLEAR '+bridge+'/request_decoded*/CLEAR '+bridge+'/request_local*/CLEAR '+bridge+'/response_held*/CLEAR '+bridge+'/acknowledge_toggle*/CLEAR',
        bridge+'/ack_meta*/CLEAR '+bridge+'/ack_sync*/CLEAR '+bridge+'/ack_settled*/CLEAR '+bridge+'/request_held*/CLEAR '+bridge+'/response_local*/CLEAR '+bridge+'/request_toggle*/CLEAR '+bridge+'/state*/CLEAR']:
        lines.append('set_false_path -to [get_pins {'+pins+'}]')
    return dict(policy='classic_pcm_scoped_candidate_cdc_v1',held_payload_max_delay_ns=10,
        synchronizer_max_delay_ns=2,physical_endpoint_resolution_verified=False,
        physical_timing_verified=False,source_bundle_before_capture=True,
        remaining=['resolve mux source/destination bits against actual synthesis','registered ready async-close recovery/removal','switch-inhibit and serial-hold propagation','routed setup/hold and complete service budget'],
        sdc='\n'.join(lines)+'\n')
def _selected_hdl(stage):
    from xml.etree import ElementTree
    entries=ElementTree.parse(Path(stage)/'Prj1.gprj').find('FileList')
    enabled=[x.get('path')for x in entries if x.get('enable')=='1']
    hdl=[p for p in enabled if Path(p).suffix.lower()in ('.v','.sv')]
    if not hdl or len(hdl)!=len(set(hdl)):
        raise ValueError('Classic runtime enabled HDL compilation owner changed')
    return enabled,hdl
def _preprocess(stage,tool,hdl):
    argv=[str(tool),'-g2012','-grelative-include','-E','-I.','-o','-',*hdl]
    result=subprocess.run(argv,cwd=stage,capture_output=True)
    if result.returncode:
        raise ValueError('Classic runtime actual include/macro closure failed: '+result.stderr.decode())
    return argv,result.stdout,result.stderr.decode()
def prepare_selection(root,stage,output):
    root,stage,output=map(Path,(root,stage,output))
    installed=shutil.which('iverilog')
    if not installed:raise ValueError('Classic runtime actual preprocessing requires iverilog')
    tool=Path(installed).resolve();enabled,hdl=_selected_hdl(stage)
    target=output/'classic_runtime_preprocessed.v';log=output/'classic_runtime_preprocess.log'
    argv,payload,diagnostic=_preprocess(stage,tool,hdl)
    target.write_bytes(payload);log.write_text(diagnostic)
    from tools.workstation_ae350_pcm import source_bundle
    record=dict(policy=POLICY,pcm=dict(source_bundle(root),profile_selected=True),
        provider=PROVIDER,preprocessed_sha256=sha(target),command=argv,
        enabled_hdl_sha256={p:sha(stage/p)for p in hdl},enabled_hdl_count=len(hdl),
        tool_sha256={str(tool):sha(tool)},cdc={k:v for k,v in cdc_bundle().items()if k!='sdc'},
        GeneralBonding_enabled=False,hardware_accepted=False,physical_CDC_accepted=False)
    verify_selection(root,stage,output,record)
    return record
def verify_selection(root,stage,output,record):
    root,stage,output=map(Path,(root,stage,output))
    from tools.workstation_ae350_pcm import source_bundle,SOURCES
    if record.get('policy')!=POLICY or record.get('pcm')!=dict(source_bundle(root),profile_selected=True)or record.get('provider')!=PROVIDER:
        raise ValueError('Classic runtime joint source selection changed')
    target=output/'classic_runtime_preprocessed.v'
    if record['preprocessed_sha256']!=sha(target):raise ValueError('Classic runtime macro evidence changed')
    enabled,hdl=_selected_hdl(stage)
    if enabled.count(PROVIDER)!=1 or any(enabled.count(s)!=1 for s in SOURCES):
        raise ValueError('Classic runtime PCM/provider compilation owner omitted')
    if record.get('enabled_hdl_sha256')!={p:sha(stage/p)for p in hdl}or record.get('enabled_hdl_count')!=len(hdl):
        raise ValueError('Classic runtime actual enabled HDL closure changed')
    if len(record.get('tool_sha256',{}))!=1:raise ValueError('Classic runtime preprocessing tool omitted')
    tool,tool_hash=next(iter(record['tool_sha256'].items()))
    if sha(tool)!=tool_hash:raise ValueError('Classic runtime preprocessing executable drift')
    argv,payload,_=_preprocess(stage,tool,hdl)
    if argv!=record['command']or hashlib.sha256(payload).hexdigest()!=record['preprocessed_sha256']:
        raise ValueError('Classic runtime actual macro closure cannot be reproduced')
    text=target.read_text()
    for anchor in ['localparam AE350_PCM_ENABLED=1;','gw138k_boot_memory #(.ROM_BYTES(131072))',
        '.hci_classic_ready_o(hci_pcm_session_ready)', '.hci_epoch_o(hci_pcm_controller_epoch)',
        '.hci_classic_generation_o(hci_pcm_transport_generation)',
        '.hci_controller_epoch_i(hci_pcm_controller_epoch)', '.hci_transport_generation_i(hci_pcm_transport_generation)']:
        if text.count(anchor)!=1:raise ValueError('Classic runtime actual macro/ABI branch missing: '+anchor)
    cdc=cdc_bundle()
    if record['cdc']!={k:v for k,v in cdc.items()if k!='sdc'}or any((stage/'constraints/custom_138k.sdc').read_text().splitlines().count(line)!=1 for line in cdc['sdc'].splitlines()):
        raise ValueError('Classic runtime scoped CDC input changed')
    if any(record[k]for k in ['GeneralBonding_enabled','hardware_accepted','physical_CDC_accepted']):
        raise ValueError('Classic runtime acceptance fabricated')
    return record
def build(root,evidence,prefix=None):
    from tools.experiment_ae350_rom_split import build as link
    from tools.ae350_classic_runtime_audit import analyze
    root,evidence=Path(root),Path(evidence)
    linked=link(evidence,prefix,root,runtime_owner=True)
    if linked['link_returncode']:raise ValueError('Classic runtime actual ROM128 link failed')
    graph=analyze(evidence,root)
    linked.update(callback_call_chain_audit=True,runtime_callgraph_report_sha256=sha(evidence/'runtime_callgraph_verification.json'))
    (evidence/'verification.json').write_text(json.dumps(linked,indent=2)+'\n')
    record=dict(linked,memory_profile='ilm64k_dlm64k',recording_api_enabled=True,business_owner_enabled=True,
        runtime_policy=POLICY,rom_sha256=sha(evidence/'boot.mem'),elf_sha256=sha(evidence/'firmware.elf'),
        binary_sha256=sha(evidence/'firmware.bin'),call_chain_stack=graph['stack'],
        tool_versions=dict(exact_executable_sha256=linked['tool_sha256']),
        cold_boot=dict(image_capacity_bytes=131072,image_storage='explicit_128k_pl_boot_rom_split',
            cache_policy='reject_enabled_i_or_d_cache_on_entry'),
        GeneralBonding_enabled=False,PCM_sustained_verified=False,measured_delay_valid=False)
    (evidence/'build_metadata.json').write_text(json.dumps(record,indent=2)+'\n')
    verify_build(root,evidence,record)
    return record
def verify_build(root,evidence,record):
    root,evidence=Path(root),Path(evidence)
    if record.get('runtime_policy')!=POLICY or not record.get('runtime_owner') or record.get('source_text_overlay')is not False:
        raise ValueError('Classic runtime actual source root omitted')
    linked=json.loads((evidence/'verification.json').read_text())
    if not linked['callback_call_chain_audit'] or linked['input_sha256']!=record['input_sha256']:
        raise ValueError('Classic runtime actual link/audit evidence drift')
    for name,h in record['input_sha256'].items():
        if sha(root/name)!=h:raise ValueError('Classic runtime source input drift: '+name)
    if record['compiled_sources']!=linked['compiled_sources'] or any(x in record['compiled_sources']for x in ['combined_budget_adapter.c']):
        raise ValueError('Classic runtime source root replaced by budget adapter')
    if record['rom_sha256']!=sha(evidence/'boot.mem')or record['elf_sha256']!=sha(evidence/'firmware.elf')or record['binary_sha256']!=sha(evidence/'firmware.bin'):
        raise ValueError('Classic runtime ELF/BIN/ROM identity drift')
    decode_rom(evidence/'boot.mem')
    graph=json.loads((evidence/'runtime_callgraph_verification.json').read_text())
    review=json.loads((evidence/'runtime_indirect_review.json').read_text())
    if linked['runtime_callgraph_report_sha256']!=sha(evidence/'runtime_callgraph_verification.json'):
        raise ValueError('Classic runtime callback report changed')
    for name,h in graph['input_sha256'].items():
        path=evidence/'adapted'/name.removeprefix('external/adapted/')if name.startswith('external/adapted/')else root/name
        if sha(path)!=h:raise ValueError('Classic runtime adapted source drift: '+name)
    stack=call_chain_report(evidence,graph['compiler_stack_frames'],(evidence/'firmware.dis').read_text(),16384,
        reviewed_indirect_calls=review,input_sha256=graph['input_sha256'])
    if stack!=record['call_chain_stack']or stack!=graph['stack']or graph['reviewed_JALR_sites']!=171:
        raise ValueError('Classic runtime complete actual callback chain changed')
    if any(record[x]for x in ['GeneralBonding_enabled','PCM_sustained_verified','measured_delay_valid']):
        raise ValueError('Classic runtime acceptance fabricated')
    if 'firmware_runtime.enabled=0;'not in (root/'firmware/ae350/classic_runtime.c').read_text():
        raise ValueError('Classic runtime durable backend gate removed')
    return graph
