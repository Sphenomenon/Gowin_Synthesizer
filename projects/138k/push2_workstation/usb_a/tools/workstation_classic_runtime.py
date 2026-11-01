"""Explicit Classic CPU/HCI/PCM composition; reuses the existing ROM builder."""
from pathlib import Path
import copy,hashlib,json,re,struct,subprocess,shutil
from tools.ae350_local_memory import call_chain_report
POLICY='ae350_classic_runtime_failclosed_v1'
WORKER_POLICY='ae350_worker_session_classic_runtime_v1'
WORKER_AUDIO_POLICY='ae350_worker_audio_only_classic_runtime_v1'
PROVIDER='rtl/workstation/workstation_profile_classic_runtime_v1.sv'
ROM96_POLICY='ae350_classic_runtime_rom96_failclosed_v1'
ROM96_PROVIDER='rtl/workstation/workstation_profile_classic_runtime_rom96_v1.sv'
ROM96_REFERENCE='tools/ae350_rom96_reference.json'
ROM96_DEPENDENCIES=(ROM96_REFERENCE,)
DEPENDENCIES=('tools/workstation_classic_runtime.py','tools/experiment_ae350_rom_split.py',
    'tools/ae350_classic_runtime_audit.py','tools/ae350_worker_audio_audit.py','firmware/ae350/boot_ilm_dlm_rom128_split.ld')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def firmware_inputs(root,*,headless_worker=False):
    # Explicit new profile alone locks this entire maintained/vendor inventory.
    return sorted(str(p.relative_to(root))for p in (Path(root)/'firmware/ae350').rglob('*')if p.is_file())
def composition(physical_rom_bytes):
    if physical_rom_bytes==131072:return POLICY,PROVIDER
    if physical_rom_bytes==98304:return ROM96_POLICY,ROM96_PROVIDER
    raise ValueError('Classic runtime physical ROM must explicitly be 96 or 128 KiB')
def decode_rom(path,physical_rom_bytes=131072):
    composition(physical_rom_bytes)
    words=Path(path).read_text().splitlines()
    if len(words)!=physical_rom_bytes//4 or any(not re.fullmatch('[0-9a-fA-F]{8}',w)for w in words):
        raise ValueError('Classic runtime requires exact physical ROM'+str(physical_rom_bytes//1024)+' image')
    return b''.join(int(w,16).to_bytes(4,'little')for w in words)
def physical96_report(root,evidence):
    """Revalidate actual ELF and impose a stricter physical bound than its layout.

    The historical __boot_rom_bytes=128K linker symbol is an unchanged layout
    envelope. It is not used to infer the selected physical storage capacity.
    File load spans consume ROM; DLM NOLOAD tails consume runtime DLM only.
    """
    from tools.ae350_rom_split import split_memory_report
    from tools.ae350_local_memory import symbol_values
    root,evidence=Path(root),Path(evidence);base=0x80000000;limit=base+98304
    binary=(evidence/'firmware.bin').read_bytes()
    if len(binary)>98304:raise ValueError('ROM96 physical binary/cold bank overflow')
    symbols=symbol_values((evidence/'firmware.nm').read_text())
    if symbols.get('__boot_rom_bytes')!=131072:
        raise ValueError('ROM96 unchanged linker layout envelope missing')
    layout=split_memory_report((evidence/'firmware.size').read_text(),
        (evidence/'firmware.nm').read_text(),binary,evidence/'firmware.elf')
    if not base+65536==symbols['__rom_text_start']<symbols['__rom_text_end']<=limit or symbols['__image_end']!=base+len(binary):
        raise ValueError('ROM96 physical cold address boundary overflow')
    raw=(evidence/'firmware.elf').read_bytes();h=struct.unpack_from('<16sHHIIIIIHHHHHH',raw)
    segments=[]
    for n in range(h[10]):
        kind,offset,vma,lma,size,memsize,flags,alignment=struct.unpack_from('<IIIIIIII',raw,h[5]+n*h[9])
        if kind!=1:continue
        if size>memsize or offset+size>len(raw)or not base<=lma<=limit or lma+size>limit:
            raise ValueError('ROM96 actual ELF load segment escapes physical storage')
        if base<=vma<limit:
            owner='physical_ROM96'
            valid=(lma==vma and vma+memsize<=limit)
        elif 0xa0000000<=vma<0xa000fffc:
            owner='ILM64'
            valid=(vma+memsize<=0xa000fffc and lma+size<=base+65536)
        elif 0xa0200100<=vma<symbols['__stack_bottom']:
            owner='DLM64_before_stack'
            valid=(vma+memsize<=symbols['__stack_bottom']and lma+size<=base+65536)
        else:valid=False;owner='invalid'
        if not valid:raise ValueError('ROM96 actual ELF runtime memory span invalid')
        segments.append(dict(run_address=vma,run_end=vma+memsize,load_address=lma,
            stored_end=lma+size,file_bytes=size,memory_bytes=memsize,owner=owner))
    reference=json.loads((root/ROM96_REFERENCE).read_text())
    actual=dict(elf_sha256=sha(evidence/'firmware.elf'),binary_sha256=sha(evidence/'firmware.bin'),
        nm_sha256=sha(evidence/'firmware.nm'))
    if reference.get('policy')!='rom96_same_elf_bin_layout_reference_v1'or reference.get('link_layout_bytes')!=131072 or reference.get('physical_rom_bytes')!=98304 or any(reference[k]!=v for k,v in actual.items()):
        raise ValueError('ROM96 ELF/BIN/code address reference identity changed')
    capacity=copy.deepcopy(layout)
    capacity.update(rom_capacity_bytes=98304,cold_code_unallocated_bytes=limit-symbols['__rom_text_end'])
    report=dict(policy='strict_rom96_actual_elf_storage_v1',physical_rom_bytes=98304,
        link_layout_limit_bytes=131072,legacy_layout_symbol=dict(name='__boot_rom_bytes',value=131072,
            meaning='unchanged link address envelope only; selected physical bound checked separately'),
        actual_ELF_load_and_runtime_spans=segments,layout_capacity=layout,
        reference=ROM96_REFERENCE,reference_sha256=sha(root/ROM96_REFERENCE),**actual,
        all_original_ELF_BIN_and_code_addresses_identical=True,only_zero_ROM_padding_removed=True,
        nominal_removed_storage_bytes=32768,nominal_removed_512x32_storage_banks=16,
        actual_resource_savings_verified=False,constant_padding_may_be_pruned_by_synthesis=True)
    return capacity,report
def cdc_bundle(*,registered_controller_epoch=False):
    """Scoped synthesis constraints; physical endpoint resolution is still due."""
    if type(registered_controller_epoch)is not bool:raise ValueError('registered HCI epoch requires explicit boolean')
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
    result=dict(policy='classic_pcm_scoped_candidate_cdc_v1',held_payload_max_delay_ns=10,
        synchronizer_max_delay_ns=2,physical_endpoint_resolution_verified=False,
        physical_timing_verified=False,source_bundle_before_capture=True,
        remaining=['resolve mux source/destination bits against actual synthesis','registered ready async-close recovery/removal','switch-inhibit and serial-hold propagation','routed setup/hold and complete service budget'],
        sdc='\n'.join(lines)+'\n')
    if registered_controller_epoch:
        from tools.workstation_hci_epoch import cdc_selection
        return cdc_selection(result,True)
    return result
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
def prepare_selection(root,stage,output,physical_rom_bytes=131072,*,selected_provider=None,headless_worker=False,registered_controller_epoch=False):
    root,stage,output=map(Path,(root,stage,output))
    policy,provider=composition(physical_rom_bytes)
    if selected_provider is not None:
        if selected_provider != "rtl/workstation/workstation_profile_w_demo.sv":
            raise ValueError("unreviewed Classic demo compilation provider")
        provider=selected_provider
        policy=WORKER_AUDIO_POLICY if headless_worker else WORKER_POLICY
    if headless_worker and selected_provider is None:raise ValueError('audio-only worker requires explicit W provider')
    if type(registered_controller_epoch)is not bool or (registered_controller_epoch and (not headless_worker or selected_provider!='rtl/workstation/workstation_profile_w_demo.sv')):raise ValueError('registered HCI epoch requires explicit audio-only W provider')
    installed=shutil.which('iverilog')
    if not installed:raise ValueError('Classic runtime actual preprocessing requires iverilog')
    tool=Path(installed).resolve();enabled,hdl=_selected_hdl(stage)
    target=output/'classic_runtime_preprocessed.v';log=output/'classic_runtime_preprocess.log'
    argv,payload,diagnostic=_preprocess(stage,tool,hdl)
    target.write_bytes(payload);log.write_text(diagnostic)
    from tools.workstation_ae350_pcm import source_bundle
    record=dict(policy=policy,pcm=dict(source_bundle(root),profile_selected=True),
        provider=provider,headless_worker=headless_worker,preprocessed_sha256=sha(target),command=argv,
        enabled_hdl_sha256={p:sha(stage/p)for p in hdl},enabled_hdl_count=len(hdl),
        tool_sha256={str(tool):sha(tool)},cdc={k:v for k,v in cdc_bundle(registered_controller_epoch=registered_controller_epoch).items()if k!='sdc'},
        GeneralBonding_enabled=False,hardware_accepted=False,physical_CDC_accepted=False)
    if registered_controller_epoch:record['hci_epoch_policy']='registered_controller_epoch_v1'
    verify_selection(root,stage,output,record,physical_rom_bytes,selected_provider=selected_provider,headless_worker=headless_worker,registered_controller_epoch=registered_controller_epoch)
    return record
def verify_cdc_selection(text,record,*,worker_demo=False,registered_controller_epoch=False):
    """Check the exact final scoped lines for the explicitly selected role."""
    cdc=cdc_bundle(registered_controller_epoch=registered_controller_epoch)
    selected=cdc['sdc']
    if worker_demo:
        from tools.workstation_demo_policy import adapt_constraints
        selected,_=adapt_constraints(selected,'W')
    if record!={k:v for k,v in cdc.items()if k!='sdc'}or any(
            text.splitlines().count(line)!=1 for line in selected.splitlines()):
        raise ValueError('Classic runtime scoped CDC input changed')

def verify_selection(root,stage,output,record,physical_rom_bytes=131072,*,selected_provider=None,headless_worker=False,registered_controller_epoch=False):
    root,stage,output=map(Path,(root,stage,output))
    policy,provider=composition(physical_rom_bytes)
    if selected_provider is not None:
        if selected_provider != "rtl/workstation/workstation_profile_w_demo.sv":
            raise ValueError("unreviewed Classic demo compilation provider")
        provider=selected_provider
        policy=WORKER_AUDIO_POLICY if headless_worker else WORKER_POLICY
    if headless_worker and selected_provider is None:raise ValueError('audio-only worker requires explicit W provider')
    if type(registered_controller_epoch)is not bool or (registered_controller_epoch and (not headless_worker or selected_provider!='rtl/workstation/workstation_profile_w_demo.sv')):raise ValueError('registered HCI epoch requires explicit audio-only W provider')
    if record.get('headless_worker',False)!=headless_worker:raise ValueError('audio-only worker selection drift')
    if (record.get('hci_epoch_policy')=='registered_controller_epoch_v1')!=registered_controller_epoch or (not registered_controller_epoch and 'hci_epoch_policy'in record):raise ValueError('registered HCI epoch metadata selection drift')
    from tools.workstation_ae350_pcm import source_bundle,SOURCES
    if record.get('policy')!=policy or record.get('pcm')!=dict(source_bundle(root),profile_selected=True)or record.get('provider')!=provider:
        raise ValueError('Classic runtime joint source selection changed')
    target=output/'classic_runtime_preprocessed.v'
    if record['preprocessed_sha256']!=sha(target):raise ValueError('Classic runtime macro evidence changed')
    enabled,hdl=_selected_hdl(stage)
    if enabled.count(provider)!=1 or any(enabled.count(s)!=1 for s in SOURCES):
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
    if text.count('.REGISTERED_CONTROLLER_EPOCH(1)')!=(1 if registered_controller_epoch else 0):raise ValueError('registered HCI epoch actual owner parameter selection drift')
    for anchor in ['localparam AE350_PCM_ENABLED=1;','gw138k_boot_memory #(.ROM_BYTES('+str(physical_rom_bytes)+'))',
        '.hci_classic_ready_o(hci_pcm_session_ready)', '.hci_epoch_o(hci_pcm_controller_epoch)',
        '.hci_classic_generation_o(hci_pcm_transport_generation)',
        '.hci_controller_epoch_i(hci_pcm_controller_epoch)', '.hci_transport_generation_i(hci_pcm_transport_generation)']:
        if text.count(anchor)!=1:raise ValueError('Classic runtime actual macro/ABI branch missing: '+anchor)
    verify_cdc_selection((stage/'constraints/custom_138k.sdc').read_text(),record['cdc'],
        worker_demo=selected_provider=='rtl/workstation/workstation_profile_w_demo.sv',registered_controller_epoch=registered_controller_epoch)
    if any(record[k]for k in ['GeneralBonding_enabled','hardware_accepted','physical_CDC_accepted']):
        raise ValueError('Classic runtime acceptance fabricated')
    return record
def build(root,evidence,prefix=None,physical_rom_bytes=131072,*,worker_demo=False,headless_worker=False):
    from tools.experiment_ae350_rom_split import build as link
    from tools.ae350_classic_runtime_audit import analyze
    root,evidence=Path(root),Path(evidence)
    policy,_=composition(physical_rom_bytes)
    if worker_demo:
        if physical_rom_bytes!=131072:raise ValueError('W DEMO selects the reviewed ROM128 composition')
        policy=WORKER_AUDIO_POLICY if headless_worker else WORKER_POLICY
    if headless_worker and not worker_demo:raise ValueError('audio-only worker requires explicit W runtime')
    linked=link(evidence,prefix,root,runtime_owner=True,worker_demo=worker_demo,headless_worker=headless_worker)
    if linked['link_returncode']:raise ValueError('Classic runtime actual ROM128 link failed')
    graph=analyze(evidence,root)
    physical=None
    if physical_rom_bytes==98304:
        capacity,physical=physical96_report(root,evidence)
        image=decode_rom(evidence/'boot.mem')
        reference=json.loads((root/ROM96_REFERENCE).read_text())
        if sha(evidence/'boot.mem')!=reference['layout128_rom_sha256']or any(image[98304:]):
            raise ValueError('ROM96 removed layout128 padding is not exactly zero')
        shutil.copyfile(evidence/'boot.mem',evidence/'link_layout128_boot.mem')
        (evidence/'boot.mem').write_text(''.join(evidence.joinpath('link_layout128_boot.mem').read_text().splitlines(keepends=True)[:24576]))
        linked['capacity']=capacity
    linked.update(callback_call_chain_audit=True,runtime_callgraph_report_sha256=sha(evidence/'runtime_callgraph_verification.json'))
    (evidence/'verification.json').write_text(json.dumps(linked,indent=2)+'\n')
    record=dict(linked,memory_profile='ilm64k_dlm64k',recording_api_enabled=not headless_worker,business_owner_enabled=True,
        runtime_policy=policy,worker_demo=worker_demo,rom_sha256=sha(evidence/'boot.mem'),elf_sha256=sha(evidence/'firmware.elf'),
        binary_sha256=sha(evidence/'firmware.bin'),call_chain_stack=graph['stack'],
        reviewed_JALR_sites=graph['reviewed_JALR_sites'],tool_versions=dict(exact_executable_sha256=linked['tool_sha256']),
        cold_boot=dict(image_capacity_bytes=physical_rom_bytes,image_storage='explicit_'+str(physical_rom_bytes//1024)+'k_pl_boot_rom_split',
            cache_policy='reject_enabled_i_or_d_cache_on_entry'),
        GeneralBonding_enabled=False,PCM_sustained_verified=False,measured_delay_valid=False)
    if physical is not None:record['physical_storage']=physical
    (evidence/'build_metadata.json').write_text(json.dumps(record,indent=2)+'\n')
    verify_build(root,evidence,record,physical_rom_bytes)
    return record
def verify_build(root,evidence,record,physical_rom_bytes=131072):
    root,evidence=Path(root),Path(evidence)
    policy,_=composition(physical_rom_bytes)
    if record.get('worker_demo',False):
        if physical_rom_bytes!=131072:raise ValueError('W DEMO physical ROM changed')
        policy=WORKER_AUDIO_POLICY if record.get('headless_worker',False) else WORKER_POLICY
    if record.get('headless_worker',False):
        if not record.get('worker_demo') or record.get('recording_api_enabled') or not record.get('business_owner_enabled'):
            raise ValueError('audio-only worker firmware selection drift')
    if record.get('runtime_policy')!=policy or not record.get('runtime_owner') or record.get('source_text_overlay')is not False:
        raise ValueError('Classic runtime actual source root omitted')
    linked=json.loads((evidence/'verification.json').read_text())
    for key in ['worker_demo','headless_worker','runtime_owner','source_text_overlay',
                'single_recording_owner','local_recording_proxy','graph_ui_compiled',
                'recording_compiled','business_protocol_compiled','session_only_pairing']:
        if record.get(key)!=linked.get(key):
            raise ValueError('Classic runtime linked role evidence changed: '+key)
    if record.get('commands')!=linked.get('commands'):
        raise ValueError('Classic runtime actual compile commands changed')
    if record.get('recording_api_enabled')is not (not bool(linked.get('headless_worker'))):
        raise ValueError('Classic runtime recording API does not match linked role')
    if record.get('business_owner_enabled')is not True:
        raise ValueError('Classic runtime native HCI provider omitted')
    if linked.get('headless_worker'):
        from tools.ae350_worker_audio_audit import verify_composition
        verify_composition(evidence,root,record)
    else:
        from tools.stage_ae350_firmware import selected_sources
        if not set(selected_sources(True,True))<=set(record['compiled_sources']):
            raise ValueError('Classic runtime legacy UI/recording composition omitted')
        for command in record['commands']:
            if command['name'].startswith('compile-'):
                flags=command['argv']
                if '-DA138_WORKER_AUDIO_ONLY' in flags or '-DA138_BLE_BUSINESS' not in flags or ('-DA138_SINGLE_BLE_RECORDING' in flags)!=bool(linked.get('worker_demo')):
                    raise ValueError('Classic runtime legacy compile role changed')
    if not linked['callback_call_chain_audit'] or linked['input_sha256']!=record['input_sha256']:
        raise ValueError('Classic runtime actual link/audit evidence drift')
    for name,h in record['input_sha256'].items():
        if sha(root/name)!=h:raise ValueError('Classic runtime source input drift: '+name)
    if record['compiled_sources']!=linked['compiled_sources'] or any(x in record['compiled_sources']for x in ['combined_budget_adapter.c']):
        raise ValueError('Classic runtime source root replaced by budget adapter')
    if record['rom_sha256']!=sha(evidence/'boot.mem')or record['elf_sha256']!=sha(evidence/'firmware.elf')or record['binary_sha256']!=sha(evidence/'firmware.bin'):
        raise ValueError('Classic runtime ELF/BIN/ROM identity drift')
    image=decode_rom(evidence/'boot.mem',physical_rom_bytes)
    if physical_rom_bytes==98304:
        capacity,physical=physical96_report(root,evidence)
        layout=decode_rom(evidence/'link_layout128_boot.mem')
        reference=json.loads((root/ROM96_REFERENCE).read_text())
        if (capacity!=record['capacity']or linked['capacity']!=capacity or record.get('physical_storage')!=physical
            or sha(evidence/'link_layout128_boot.mem')!=reference['layout128_rom_sha256']
            or image!=layout[:98304]or any(layout[98304:])or image!=(evidence/'firmware.bin').read_bytes().ljust(98304,b'\0')):
            raise ValueError('ROM96 actual physical storage/padding evidence changed')
    elif record.get('physical_storage')is not None or record['capacity']['rom_capacity_bytes']!=131072:
        raise ValueError('ROM128 cannot claim ROM96 physical composition')
    graph=json.loads((evidence/'runtime_callgraph_verification.json').read_text())
    review=json.loads((evidence/'runtime_indirect_review.json').read_text())
    if linked['runtime_callgraph_report_sha256']!=sha(evidence/'runtime_callgraph_verification.json'):
        raise ValueError('Classic runtime callback report changed')
    for name,h in graph['input_sha256'].items():
        path=evidence/'adapted'/name.removeprefix('external/adapted/')if name.startswith('external/adapted/')else root/name
        if sha(path)!=h:raise ValueError('Classic runtime adapted source drift: '+name)
    stack=call_chain_report(evidence,graph['compiler_stack_frames'],(evidence/'firmware.dis').read_text(),16384,
        reviewed_indirect_calls=review,input_sha256=graph['input_sha256'])
    if stack!=record['call_chain_stack']or stack!=graph['stack']or graph['reviewed_JALR_sites']!=record['reviewed_JALR_sites']:
        raise ValueError('Classic runtime complete actual callback chain changed')
    if any(record[x]for x in ['GeneralBonding_enabled','PCM_sustained_verified','measured_delay_valid']):
        raise ValueError('Classic runtime acceptance fabricated')
    if 'firmware_runtime.enabled=0;'not in (root/'firmware/ae350/classic_runtime.c').read_text():
        raise ValueError('Classic runtime durable backend gate removed')
    return graph
