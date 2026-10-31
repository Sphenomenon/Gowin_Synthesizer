#!/usr/bin/env python3
"""Build an unselected ROM128/ILM64/DLM64 experiment with all real source live.

No section GC, LTO, EDA, board access or production-profile changes.
The default budget experiment retains its two exact private-copy anchors.
Explicit --runtime-owner instead links the versioned cooperative CPU owner,
without text overlays; durable bonds and physical media acceptance remain absent.
"""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.stage_ae350_firmware import selected_sources,selected_inputs,compiler_prefix
from tools.prepare_ae350_sbc import prepare
from tools.ae350_rom_split import split_memory_report
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

def build(output,prefix=None,root=ROOT,*,runtime_owner=False):
    out=Path(output).resolve()
    if out.exists():raise ValueError('experiment output must not exist')
    out.mkdir(parents=True)
    prefix=prefix or compiler_prefix()
    source=root/'firmware/ae350';inputs={};commands=[]
    for name in selected_inputs(True,'ilm64k_dlm64k',True):
        shutil.copyfile(source/name,out/name);inputs['firmware/ae350/'+name]=sha(source/name)
    extra=['classic_service.c','classic_service.h','sbc_decoder_service.c','sbc_decoder_service.h']
    if runtime_owner:extra += ['classic_security.c','classic_security.h','hci_transport.c','hci_transport.h',
        'classic_runtime.c','classic_runtime.h','pcm_media.c','pcm_media.h']
    for name in extra:
        shutil.copyfile(source/name,out/name);inputs['firmware/ae350/'+name]=sha(source/name)
    inputs['tools/prepare_ae350_sbc.py']=sha(root/'tools/prepare_ae350_sbc.py')
    adaptation=prepare(root,out/'adapted')
    for path in (source/'third_party/sbc_oi').rglob('*'):
        if path.is_file():inputs[str(path.relative_to(root))]=sha(path)
    if not runtime_owner:
        shutil.copyfile(root/'sim/fixtures/ae350_combined_budget_adapter.c',out/'combined_budget_adapter.c')
    for name in ['firmware/ae350/boot_ilm_dlm_rom128_split.ld',
            'sim/fixtures/ae350_combined_budget_adapter.c',
            'sim/fixtures/ae350_budget_abi_witness.c',
            'sim/fixtures/ae350_sbc_reference.json', 'sim/ae350_rv32_startup.py',
            'sim/ae350_probe_rv32.py', 'sim/ae350_split_rv32.py', 'sim/ae350_rom_split_checks.py',
            'sim/test_ae350_rom_split.py',
            'tools/ae350_local_memory.py', 'tools/ae350_rom_split.py',
            'tools/ae350_rom_split_audit.py', 'tools/experiment_ae350_rom_split.py',
            'tools/stage_ae350_firmware.py', 'tools/stage_usb_firmware.py',
            'tools/workstation_baselines.py', 'tools/ae350_ble_business_indirect_review.json']:
        inputs[name]=sha(root/name)
    if runtime_owner:inputs['tools/ae350_classic_runtime_audit.py']=sha(root/'tools/ae350_classic_runtime_audit.py')
    shutil.copyfile(source/'boot_ilm_dlm_rom128_split.ld',out/'boot_ilm_dlm_rom128_split.ld')
    main=out/'ui_main.c'
    if runtime_owner:
        overlay=dict(source='firmware/ae350/ui_main.c',source_sha256=inputs['firmware/ae350/ui_main.c'],
            output_sha256=sha(main),changes=[],policy='No source text overlay: versioned A138_CLASSIC_RUNTIME composition calls the actual cooperative owner; durable bond and physical media backends absent, BR/EDR fail-closed.')
    else:
        before=main.read_text();old='void services_main(void) {'
        new='void a138_combined_budget_init(void);\nvoid a138_combined_budget_step(void);\n'+old+'\n    a138_combined_budget_init();'
        assert before.count(old)==1
        old_loop='for(;;)ui_service_step(&runtime);'
        new_loop='for(;;){ui_service_step(&runtime);a138_combined_budget_step();}'
        assert before.count(old_loop)==1
        main.write_text(before.replace(old,new).replace(old_loop,new_loop))
        overlay=dict(source='firmware/ae350/ui_main.c',source_sha256=inputs['firmware/ae350/ui_main.c'],
            output_sha256=sha(main),changes=[dict(old=old,new=new,count=1),dict(old=old_loop,new=new_loop,count=1)],
            policy='Budget-only two exact anchor overlay; retains all existing startup/services and adds actual classic/decoder roots. Not production integration.')
    (out/'overlay.json').write_text(json.dumps(overlay,indent=2)+'\n')
    (out/'stdlib.h').write_text('#include <stddef.h>\n')
    (out/'string.h').write_text('#include <stddef.h>\nvoid *memset(void *,int,size_t);\nvoid *memcpy(void *,const void *,size_t);\nint memcmp(const void *,const void *,size_t);\n')
    flags=['-march=rv32im_zicsr_zifencei','-mabi=ilp32','-msmall-data-limit=0','-O2','-ffreestanding',
        '-fno-builtin','-fno-pic','-fno-stack-protector','-fno-common','-fno-jump-tables',
        '-fstack-usage','-fcallgraph-info=su','-Wall','-Wextra','-Werror','-Wno-unused-parameter',
        '-DA138_ILM64K_DLM64K','-DA138_BLE_BUSINESS','-I'+str(out),'-I'+str(out/'adapted/decoder/include'),
        '-I'+str(out/'adapted/decoder/srce')]
    if runtime_owner:flags += ['-DA138_CLASSIC_RUNTIME']
    def run(argv,name,check=True):
        p=subprocess.run(list(map(str,argv)),cwd=out,text=True,capture_output=True)
        (out/(name+'.log')).write_text(p.stdout+p.stderr)
        commands.append(dict(name=name,argv=list(map(str,argv)),returncode=p.returncode))
        if check:assert p.returncode==0,(name,p.stdout,p.stderr)
        return p
    objects=[]
    sources=[out/name for name in selected_sources(True,True)]
    sources += [out/'classic_service.c',out/'sbc_decoder_service.c']
    sources += [out/name for name in ['classic_security.c','hci_transport.c','classic_runtime.c','pcm_media.c']] if runtime_owner else [out/'combined_budget_adapter.c']
    sources += sorted((out/'adapted/decoder/srce').glob('*.c'))
    for path in sources:
        target=out/(path.stem+'.o');assert target not in objects
        run([prefix+'-gcc',*flags,'-c',path,'-o',target],'compile-'+path.stem)
        objects.append(target)
    shutil.copyfile(root/'sim/fixtures/ae350_budget_abi_witness.c',out/'ae350_budget_abi_witness.c')
    run([prefix+'-gcc',*flags,'-c',out/'ae350_budget_abi_witness.c','-o',out/'ae350_budget_abi_witness.o'],
        'compile-unlinked-abi-witness')
    run([prefix+'-nm','-S','--size-sort',out/'ae350_budget_abi_witness.o'],'abi-witness-size')
    common=[prefix+'-gcc','-march=rv32im_zicsr_zifencei','-mabi=ilp32','-msmall-data-limit=0',
        '-nostdlib','-nostartfiles','-Wl,--build-id=none,--defsym=__boot_rom_bytes=131072,-Map=firmware.map,-T,boot_ilm_dlm_rom128_split.ld',
        *objects,'-lgcc','-o','firmware.elf']
    linked=run(common,'link',False)
    record=dict(schema=1,scope='isolated ROM128 split executable placement experiment; not production/runtime closure',
        input_sha256=inputs,overlay=overlay,commands=commands,compiled_sources=[str(p.relative_to(out)) for p in sources],
        no_gc_sections=True,no_LTO=True,selected_in_production=False,hardware_operated=False,cache_enabled=False,
        linked_translation_units=len(sources),unlinked_abi_witness='ae350_budget_abi_witness.o',
        link_returncode=linked.returncode,tool_sha256={str(Path(prefix+'-'+x)):sha(prefix+'-'+x) for x in ['gcc','objcopy','size','nm','objdump']})
    if runtime_owner:
        record.update(scope='actual versioned cooperative CPU root, explicitly fail-closed without durable bond and physical media backends; isolated ROM128 link, not native/phone/hardware acceptance',
            runtime_owner=True,source_text_overlay=False,persistent_bond_backend=False,physical_media_backend=False,
            callback_call_chain_audit=False,decode_cycles_measured=False,native_transport_integrated=False)
    if linked.returncode==0:
        run([prefix+'-objcopy','-O','binary','firmware.elf','firmware.bin'],'objcopy')
        size=run([prefix+'-size','firmware.elf'],'size').stdout
        syms=run([prefix+'-nm','-n','firmware.elf'],'nm').stdout
        (out/'firmware.size').write_text(size);(out/'firmware.nm').write_text(syms)
        dis=run([prefix+'-objdump','-d','firmware.elf'],'objdump').stdout
        (out/'firmware.dis').write_text(dis)
        raw=(out/'firmware.bin').read_bytes()
        capacity=split_memory_report(size,syms,raw,out/'firmware.elf')
        record.update(capacity=capacity)
        padded=raw.ljust(131072,b'\0')
        (out/'boot.mem').write_text(''.join(f'{int.from_bytes(padded[i:i+4], "little"):08x}\n' for i in range(0,131072,4)))
        run([prefix+'-size','-A','firmware.elf'],'size-sections')
        run([prefix+'-nm','-S','--size-sort','firmware.elf'],'nm-size')
        run([prefix+'-nm','-u','firmware.elf'],'undefined')
    for name,h in inputs.items():assert sha(root/name)==h,name
    record['commands']=commands
    (out/'verification.json').write_text(json.dumps(record,indent=2)+'\n')
    return record

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--riscv-prefix')
    p.add_argument('--runtime-owner',action='store_true',help='link the actual versioned fail-closed CPU root; no budget text overlay')
    a=p.parse_args()
    r=build(a.output,a.riscv_prefix,runtime_owner=a.runtime_owner)
    if r['link_returncode']:
        raise ValueError('explicit ROM128 link failed; immutable diagnostics in '+str(a.output/'link.log'))
    if a.runtime_owner:
        from tools.ae350_classic_runtime_audit import analyze
        graph=analyze(a.output,ROOT)
        r.update(callback_call_chain_audit=True,
            runtime_callgraph_report_sha256=sha(a.output/'runtime_callgraph_verification.json'))
        (a.output/'verification.json').write_text(json.dumps(r,indent=2)+'\n')
        print(json.dumps({k:v for k,v in r['capacity'].items() if k not in ('symbols','elf_image_validation')},indent=2))
        print(json.dumps(dict(conservative_stack_bytes=graph['stack']['conservative_peak_bytes'],reviewed_JALR_sites=graph['reviewed_JALR_sites']),indent=2))
        print('Actual cooperative runtime linked; native/backend/cycles/hardware acceptance remain incomplete.')
        return
    from tools.ae350_rom_split_audit import analyze,verify_tables
    sys.path.insert(0,str(ROOT/'sim'))
    from ae350_rom_split_checks import run_model_checks
    graph=analyze(a.output,ROOT)
    tables=verify_tables(a.output)
    model=run_model_checks(a.output,ROOT)
    print(json.dumps({k:v for k,v in r['capacity'].items() if k not in ('symbols','elf_image_validation')},indent=2))
    print(json.dumps(dict(stack_bound_bytes=graph['stack']['conservative_peak_bytes'],
        resolved_direct_long_calls=len(graph['stack']['resolved_direct_long_calls']),
        reviewed_indirect_calls=graph['reviewed_reachable_JALR_sites'],
        actual_callback_tables=len(tables), model_scalar_samples=model['scalar_samples'],
        maximum_lsb_error=model['maximum_lsb_error']),indent=2))

if __name__=='__main__':main()
