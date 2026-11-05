#!/usr/bin/env python3
"""Build/audit the isolated headless task3 W-media firmware, no profile overlay.

The inherited review manifests remain immutable. A separate source review pins
the actual media root and traces the capacity extension to its reviewed parent;
every reachable JALR and stack frame is checked in this newly linked ELF.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.prepare_ae350_sbc import prepare
from tools.stage_usb_firmware import compiler_prefix
from tools.ae350_rom_split import split_memory_report
from tools.ae350_local_memory import call_chain_report,direct_long_calls,symbol_values,ILM_BASE
from tools.ae350_rom_split_audit import verify_tables
from tools.workstation_recording_format_provenance import original_identity, parent_source
from tools.workstation_task3_w_media import firmware_capacity_flag,recording_geometry

POLICY='task3_w_headless_media_single_recording_60s_v1'
PAIRED_POLICY='task3_w_paired_media_single_recording_60s_v1'
PHONE_BATCH_POLICY='task3_w_paired_phone_batch_single_recording_60s_v1'
REVIEW='tools/workstation_task3_w_media_firmware_review.json'
SOURCES=('start.S','worker_media_main.c','ui_runtime.c','audio_clock_service.c',
         'recording_service.c','business_mailbox.c','ble_business_owner.c',
         'classic_service.c','sbc_decoder_service.c','classic_security.c',
         'hci_transport.c','classic_runtime.c','pcm_media.c')
HEADERS=('audio_services.h','audio_clock_service.h','recording_service.h',
         'business_mailbox.h','ble_business_owner.h','classic_service.h',
         'sbc_decoder_service.h','classic_security.h','hci_transport.h',
         'classic_runtime.h','pcm_media.h','start_ilm_dlm.inc',
         'boot_ilm_dlm_rom128_split.ld')
FLAGS=('-march=rv32im_zicsr_zifencei','-mabi=ilp32','-msmall-data-limit=0','-O2',
       '-ffreestanding','-fno-builtin','-fno-pic','-fno-stack-protector','-fno-common',
       '-fno-jump-tables','-fstack-usage','-fcallgraph-info=su','-Wall','-Wextra',
       '-Werror','-Wno-unused-parameter','-DA138_ILM64K_DLM64K',
       '-DA138_CLASSIC_RUNTIME','-DA138_SINGLE_BLE_RECORDING','-DA138_BLE_BUSINESS',
       '-DA138_WORKER_MEDIA')

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def batch_artifacts(out):
    """Bind the ELF and the actual compiler/decoder evidence consumed by audit."""
    out=Path(out)
    paths=[out/name for name in ('firmware.elf','firmware.bin','firmware.size',
        'firmware.nm','firmware.dis','boot.mem','undefined.log')]
    paths.extend(p for pattern in ('*.su','*.ci','*.o') for p in sorted(out.glob(pattern)))
    return {str(p.relative_to(out)):sha(p)for p in paths}

def adapted_inputs(out):
    out=Path(out)/'adapted'
    return {str(p.relative_to(out)):sha(p)for p in sorted(out.rglob('*'))if p.is_file()}

def verify_sources(root,phone_batch=False):
    root=Path(root)
    expected={f'firmware/ae350/{name}' for name in (*SOURCES,*HEADERS)}
    batch_lineage={}
    if phone_batch:
        from tools import workstation_task3_w_paired_firmware as paired
        review,batch_lineage=paired.verify_phone_batch_sources(root,expected)
    else:
        review=json.loads((root/REVIEW).read_text())
        if review.get('policy')!=POLICY or set(review.get('input_sha256',{}))!=expected:
            raise ValueError('W-media source review policy/inventory drift')
        for rel,value in review['input_sha256'].items():
            parent,_=parent_source(root,Path(rel).name,(root/rel).read_bytes())
            if hashlib.sha256(parent).hexdigest()!=value:raise ValueError('W-media reviewed source drift: '+rel)
    old=json.loads((root/'tools/ae350_worker_recording_indirect_review.json').read_text())
    lineage={}
    for rel,wanted in old['input_sha256'].items():
        payload=(root/rel).read_bytes()
        if rel in batch_lineage:payload=paired.disabled_phone_batch_source(payload)
        original,adaptation=original_identity(root,Path(rel).name,payload)
        if adaptation is not None:lineage[rel]=adaptation
        if rel=='firmware/ae350/classic_runtime.c':
            text=payload.decode()
            for body in ('#include "ble_business_owner.h"','    a138_ble_business_firmware_init();',
                         '    a138_ble_business_firmware_pump();'):
                guarded='#ifndef A138_WORKER_AUDIO_ONLY\n'+body+'\n#endif'
                if text.count(guarded)!=1:raise ValueError('inherited audio-only guard drift')
                text=text.replace(guarded,body,1)
            original=hashlib.sha256(text.encode()).hexdigest()
        if original!=wanted:raise ValueError('W-media inherited source lineage drift: '+rel)
    legacy=json.loads((root/'tools/ae350_ble_business_indirect_review.json').read_text())
    for name in ('audio_clock_service.c','recording_service.c','business_mailbox.c'):
        rel='firmware/ae350/'+name
        original,_=original_identity(root,name,(root/rel).read_bytes())
        if original!=legacy['input_sha256'][rel]:raise ValueError('inherited MMIO callbacks drift')
    if phone_batch:lineage['phone_batch_disabled_parent']=batch_lineage
    return review,lineage

def audit(output,root=ROOT):
    out,root=Path(output),Path(root)
    d=json.loads((out/'verification.json').read_text())
    phone_batch=d.get('policy')==PHONE_BATCH_POLICY
    reviewed,lineage=verify_sources(root,phone_batch=phone_batch)
    paired_source=d.get('policy')in (PAIRED_POLICY,PHONE_BATCH_POLICY)
    if (d.get('policy')not in (POLICY,PAIRED_POLICY,PHONE_BATCH_POLICY) or
        d.get('phone_batch',False)is not phone_batch or
        d.get('source_text_overlay')is not paired_source or d.get('link_returncode')!=0):
        raise ValueError('new actual media ELF required')
    if phone_batch:
        # verify_sources has checked the frozen review through exact lineage.
        # The build receipt must bind the actual current bytes, including the
        # opt-in format backend, rather than substituting those parent hashes.
        if any(d.get('input_sha256',{}).get(rel)!=sha(root/rel) for rel in reviewed['input_sha256']):
            raise ValueError('phone-batch actual source inventory drift')
        if d.get('phone_batch_artifacts_sha256')!=batch_artifacts(out):
            raise ValueError('phone-batch actual ELF/compiler evidence drift')
        if d.get('adapted_inputs_sha256')!=adapted_inputs(out):
            raise ValueError('phone-batch actual adapted decoder drift')
        capacity=split_memory_report((out/'firmware.size').read_text(),
            (out/'firmware.nm').read_text(),(out/'firmware.bin').read_bytes(),
            out/'firmware.elf',headless_worker=True)
        if capacity!=d.get('capacity'):
            raise ValueError('phone-batch actual ELF memory capacity drift')
    if paired_source:
        from tools import workstation_task3_w_paired_firmware as paired
        paired.verify(root,out,d.get('paired_record_source_adaptation'))
    elif d.get('paired_record_source_adaptation')is not None:raise ValueError('unexpected paired REC_START adaptation')
    for name in (*SOURCES,*HEADERS):
        if paired_source and 'firmware/ae350/'+name==paired.SOURCE:continue
        if sha(out/name)!=sha(root/('firmware/ae350/'+name)):
            raise ValueError('W-media actual compiled source drift: '+name)
    wanted=[*SOURCES,*('adapted/decoder/srce/'+p.name for p in sorted((out/'adapted/decoder/srce').glob('*.c')))]
    if d['compiled_sources']!=wanted:raise ValueError('W-media compiled-source inventory drift')
    if phone_batch:
        compile_commands=[cmd for cmd in d['commands']if cmd['name'].startswith('compile-')]
        if len(compile_commands)!=len(wanted):
            raise ValueError('phone-batch actual per-TU command inventory drift')
        for name,cmd in zip(wanted,compile_commands):
            argv=cmd['argv']
            if (argv[-4:]!=['-c',str(out/name),'-o',str(out/(Path(name).stem+'.o'))] or
                cmd.get('returncode')!=0 or cmd['name']!='compile-'+Path(name).stem):
                raise ValueError('phone-batch actual per-TU source command drift')
    for cmd in d['commands']:
        if cmd['name'].startswith('compile-'):
            batch_flags=[arg for arg in cmd['argv'] if arg.startswith('-DA138_TASK3_PHONE_BATCH')]
            if (not {*FLAGS,firmware_capacity_flag(root)}<=set(cmd['argv']) or
                '-DA138_WORKER_AUDIO_ONLY' in cmd['argv'] or
                batch_flags!=(['-DA138_TASK3_PHONE_BATCH']if phone_batch else [])):
                raise ValueError('W-media real per-TU flags drift')
    for rel,value in d['input_sha256'].items():
        if sha(root/rel)!=value:raise ValueError('W-media build input changed: '+rel)
    inputs=dict(d['input_sha256'])
    for p in (out/'adapted').rglob('*'):
        if p.is_file():inputs['external/adapted/'+str(p.relative_to(out/'adapted'))]=sha(p)
    dis=(out/'firmware.dis').read_text()
    prior=json.loads((root/'tools/ae350_ble_business_indirect_review.json').read_text())
    targets={}
    for site in prior['sites']:
        previous=targets.setdefault(site['caller'],site['targets'])
        if previous!=site['targets']:raise ValueError('inherited callback target disagreement')
    targets.update(reviewed['callback_targets'])
    long=direct_long_calls(dis);sites=[];all_sites=[];caller=None
    for line in dis.splitlines():
        match=re.match(r'^[0-9a-f]+ <([^>]+)>:',line)
        if match:caller=match[1]
        insn=re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+',line)
        if insn and int(insn[2],16)&0x7f==0x67 and int(insn[2],16)!=0x8067 and int(insn[1],16)not in long:
            row=dict(caller=caller,address='0x'+insn[1],instruction=insn[2]);all_sites.append(row)
            if caller in targets:sites.append(dict(**row,targets=targets[caller]))
    machine_review=dict(schema=1,input_sha256=inputs,
        disassembly_sha256=hashlib.sha256(dis.encode()).hexdigest(),
        source_target_review=reviewed['source_target_review'],sites=sites)
    (out/'media_indirect_review.json').write_text(json.dumps(machine_review,indent=2)+'\n')
    frames=[]
    for p in sorted(out.glob('*.su')):
        for line in p.read_text().splitlines():
            fn,n,kind=line.split('\t');frames.append(dict(function=fn,bytes=int(n),kind=kind))
    stack=call_chain_report(out,frames,dis,16384,reviewed_indirect_calls=machine_review,input_sha256=inputs)
    required={'services_main','a138_classic_runtime_firmware_init','a138_classic_runtime_firmware_pump',
              'a138_ble_business_firmware_init','a138_ble_business_firmware_pump',
              'a138_record_data_probe','a138_record_data_submit','a138_record_data_poll',
              'a138_classic_runtime_init_session','a138_hci_step','a138_sbc_decode','OI_CODEC_SBC_DecodeFrame'}
    if not required<=set(stack['reachable_functions']):
        raise ValueError('actual W-media roots missing: '+str(required-set(stack['reachable_functions'])))
    if phone_batch:
        required_batch={'a138_pcm_media_init_paired','paired_poll','paired_submit','paired_cancel','paired_transaction'}
        if not required_batch<=set(stack['reachable_functions']):
            raise ValueError('actual W phone-batch callbacks missing: '+str(required_batch-set(stack['reachable_functions'])))
        if {'pcm_poll','pcm_submit','pcm_cancel'} & set(stack['reachable_functions']):
            raise ValueError('legacy PCM callbacks entered phone-batch firmware graph')
    forbidden={'ui_service_step','ui_render_rows','a138_record_probe','a138_record_command','a138_record_create',
               'unavailable_load','unavailable_replace','unavailable_delete'}
    if forbidden & set(stack['reachable_functions']):raise ValueError('retired UI/R00/durable root reachable')
    symbols=symbol_values((out/'firmware.nm').read_text())
    if any(name.startswith('ui_') and name not in ('ui_runtime',) for name in symbols):
        raise ValueError('W-media graph UI symbol linked')
    for name in ('a138_ble_business_firmware_init','a138_ble_business_firmware_pump'):
        if not ILM_BASE<=symbols[name]<d['capacity']['symbols']['__ilm_end']:
            raise ValueError('W-media hot business escaped ILM')
    if (out/'undefined.log').read_text().strip():raise ValueError('W-media undefined ELF symbol')
    tables=verify_tables(out)
    negative=[]
    for name,change,capacity in (
        ('missing-machine-site',lambda r:r['sites'].pop(),16384),
        ('unknown-target',lambda r:r['sites'][0].update(targets=['unreviewed_target']),16384),
        ('source-drift',lambda r:r['input_sha256'].update({next(iter(inputs)):'0'*64}),16384),
        ('stack-overflow',lambda r:None,1)):
        mutated=copy.deepcopy(machine_review);change(mutated)
        try:call_chain_report(out,frames,dis,capacity,reviewed_indirect_calls=mutated,input_sha256=inputs)
        except ValueError as error:negative.append(dict(name=name,rejected=True,error=str(error)))
        else:raise ValueError('W-media callback negative control survived: '+name)
    result=dict(schema=1,passed=True,policy=d['policy'],stack=stack,capacity=d['capacity'],
        source_review_sha256=sha(root/(paired.BATCH_REVIEW if phone_batch else REVIEW)),capacity_lineage=lineage,
        actual_callback_tables=tables,actual_machine_sites=all_sites,reviewed_JALR_sites=len(sites),
        negative_controls=negative,ELF_sha256=sha(out/'firmware.elf'),boot_sha256=sha(out/'boot.mem'),
        recording_capacity_frames=2880000,graph_ui_compiled=False,single_C_BLE_recording_owner=True,
        R00_backend_selected=False,source_text_overlay=paired_source,per_TU_capacity_define_verified=True,
        native_candidate_selected=False,CPU_cycles_measured=False,hardware_watermark=False,
        radio_audio_acceptance=False,hardware_operated=False)
    if phone_batch:result['phone_batch']=True
    if paired_source:result['paired_record_source_adaptation']=d['paired_record_source_adaptation']
    (out/'media_callgraph_verification.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

def build(output,prefix=None,root=ROOT,paired_source=False,phone_batch=False):
    out,root=Path(output).resolve(),Path(root)
    if phone_batch and not paired_source:raise ValueError('phone-batch requires explicit paired W firmware')
    review,lineage=verify_sources(root,phone_batch=phone_batch)
    out.mkdir(parents=True,exist_ok=False)
    prefix=compiler_prefix(prefix)
    if not Path(prefix).is_absolute():
        executable=shutil.which(prefix+'-gcc')
        if executable is None:raise ValueError('W-media RISC-V compiler not found')
        prefix=executable.removesuffix('-gcc')
    inputs={}
    for name in (*SOURCES,*HEADERS):
        rel='firmware/ae350/'+name;shutil.copyfile(root/rel,out/name);inputs[rel]=sha(root/rel)
    paired_adaptation=None
    if paired_source:
        from tools import workstation_task3_w_paired_firmware as paired
        paired_adaptation=paired.apply(root,out)
        inputs[paired.TOOL]=sha(root/paired.TOOL)
    tools=('tools/workstation_task3_w_media_firmware.py',REVIEW,'tools/workstation_recording_capacity_provenance.py',
           'tools/workstation_recording_format_provenance.py','firmware/ae350/recording_formats.lineage.json',
           'firmware/ae350/ble_business_owner.capacity_lineage.json','tools/ae350_local_memory.py',
           'tools/ae350_rom_split.py','tools/ae350_rom_split_audit.py','tools/prepare_ae350_sbc.py',
           'tools/ae350_ble_business_indirect_review.json','tools/ae350_worker_recording_indirect_review.json',
           'tools/workstation_task3_w_media.py','rtl/ddr_address_map.vh')
    for name in tools:inputs[name]=sha(root/name)
    if phone_batch:inputs[paired.BATCH_REVIEW]=sha(root/paired.BATCH_REVIEW)
    adaptation=prepare(root,out/'adapted')
    adapted_before=adapted_inputs(out)if phone_batch else None
    for p in(root/'firmware/ae350/third_party/sbc_oi').rglob('*'):
        if p.is_file():inputs[str(p.relative_to(root))]=sha(p)
    (out/'stdlib.h').write_text('#include <stddef.h>\n')
    (out/'string.h').write_text('#include <stddef.h>\nvoid *memset(void *,int,size_t);\nvoid *memcpy(void *,const void *,size_t);\nint memcmp(const void *,const void *,size_t);\n')
    flags=[*FLAGS,firmware_capacity_flag(root),'-I'+str(out),'-I'+str(out/'adapted/decoder/include'),'-I'+str(out/'adapted/decoder/srce')]
    if phone_batch:flags.append('-DA138_TASK3_PHONE_BATCH')
    commands=[]
    def run(argv,name,check=True):
        p=subprocess.run(list(map(str,argv)),cwd=out,text=True,capture_output=True)
        (out/(name+'.log')).write_text(p.stdout+p.stderr)
        commands.append(dict(name=name,argv=list(map(str,argv)),returncode=p.returncode))
        if check and p.returncode:raise RuntimeError(name+' failed: '+str(out/(name+'.log')))
        return p
    compiled=[*SOURCES,*('adapted/decoder/srce/'+p.name for p in sorted((out/'adapted/decoder/srce').glob('*.c')))]
    objects=[]
    record=dict(schema=1,policy=PHONE_BATCH_POLICY if phone_batch else PAIRED_POLICY if paired_source else POLICY,passed=False,input_sha256=inputs,capacity_lineage=lineage,
        source_text_overlay=paired_source,
        compiled_sources=compiled,commands=commands,no_GC=True,no_LTO=True,
        headless_media=True,recording_capacity_frames=2880000,native_candidate_selected=False,hardware_operated=False,
        recording_geometry=recording_geometry(root),
        tool_sha256={tool:sha(prefix+'-'+tool) for tool in ('gcc','objcopy','size','nm','objdump')})
    if paired_source:record['paired_record_source_adaptation']=paired_adaptation
    if phone_batch:record['phone_batch']=True
    if phone_batch:record['adapted_inputs_sha256']=adapted_before
    try:
        for name in compiled:
            target=out/(Path(name).stem+'.o')
            if target in objects:raise ValueError('duplicate W-media object name')
            run([prefix+'-gcc',*flags,'-c',out/name,'-o',target],'compile-'+Path(name).stem);objects.append(target)
        link=run([prefix+'-gcc','-march=rv32im_zicsr_zifencei','-mabi=ilp32','-msmall-data-limit=0',
            '-nostdlib','-nostartfiles','-Wl,--build-id=none,--defsym=__boot_rom_bytes=131072,-Map=firmware.map,-T,boot_ilm_dlm_rom128_split.ld',
            *objects,'-lgcc','-o','firmware.elf'],'link',False)
        record['link_returncode']=link.returncode
        if link.returncode:raise RuntimeError('W-media link failed: '+str(out/'link.log'))
        run([prefix+'-objcopy','-O','binary','firmware.elf','firmware.bin'],'objcopy')
        size=run([prefix+'-size','firmware.elf'],'size').stdout
        syms=run([prefix+'-nm','-n','firmware.elf'],'nm').stdout
        (out/'firmware.size').write_text(size);(out/'firmware.nm').write_text(syms)
        (out/'firmware.dis').write_text(run([prefix+'-objdump','-d','firmware.elf'],'objdump').stdout)
        raw=(out/'firmware.bin').read_bytes()
        record['capacity']=split_memory_report(size,syms,raw,out/'firmware.elf',headless_worker=True)
        padded=raw.ljust(131072,b'\0')
        (out/'boot.mem').write_text(''.join(f'{int.from_bytes(padded[i:i+4],"little"):08x}\n'for i in range(0,131072,4)))
        run([prefix+'-nm','-S','--size-sort','firmware.elf'],'nm-size')
        run([prefix+'-nm','-u','firmware.elf'],'undefined')
        if any(sha(root/name)!=value for name,value in inputs.items()):raise ValueError('source changed during W-media build')
        if phone_batch:
            if adapted_before!=adapted_inputs(out):raise ValueError('adapted decoder changed during phone-batch build')
            record['phone_batch_artifacts_sha256']=batch_artifacts(out)
        (out/'verification.json').write_text(json.dumps(record,indent=2)+'\n')
        graph=audit(out,root)
        record.update(passed=True,callgraph_sha256=sha(out/'media_callgraph_verification.json'),
                      conservative_stack_bytes=graph['stack']['conservative_peak_bytes'])
    finally:(out/'verification.json').write_text(json.dumps(record,indent=2)+'\n')
    return record

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--riscv-prefix')
    p.add_argument('--audit-only',action='store_true')
    p.add_argument('--paired-source',action='store_true')
    p.add_argument('--phone-batch',action='store_true')
    a=p.parse_args()
    result=audit(a.output)if a.audit_only else build(a.output,a.riscv_prefix,paired_source=a.paired_source,phone_batch=a.phone_batch)
    print(json.dumps({k:v for k,v in result.items()if k in ('passed','policy','conservative_stack_bytes','reviewed_JALR_sites')},indent=2))
