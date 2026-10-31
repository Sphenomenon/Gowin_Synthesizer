"""Audit actual split machine calls; preserve complete source points-to closure."""
from pathlib import Path
import collections,hashlib,json,re,struct
from tools.ae350_local_memory import call_chain_report,direct_long_calls
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

def verify_tables(output):
    """Resolve the four actual ELF callback tables, word for word."""
    out=Path(output)
    raw=(out/'firmware.elf').read_bytes()
    eh=struct.unpack_from('<16sHHIIIIIHHHHHH',raw)
    sections=[struct.unpack_from('<IIIIIIIIII',raw,eh[6]+i*eh[11]) for i in range(eh[12])]
    symbols={}
    for line in (out/'nm-size.log').read_text().splitlines():
        row=line.split()
        if len(row)==4:symbols[row[3]]=dict(address=int(row[0],16),bytes=int(row[1],16),kind=row[2])
    def at(address,count):
        candidates=[s for s in sections if s[1]!=8 and s[3]<=address and address+count<=s[3]+s[5]]
        if len(candidates)!=1:raise ValueError('ambiguous ELF table placement')
        section=candidates[0];offset=section[4]+address-section[3]
        return raw[offset:offset+count]
    tables={}
    for name,targets in {
        'balloc':['monoBitAllocation','dualBitAllocation','stereoBitAllocation','stereoBitAllocation'],
        'SpecializedReadSamples':['OI_SBC_ReadSamplesJoint4','OI_SBC_ReadSamplesJoint8'],
        'SynthFrame4SB':[None,'OI_SBC_SynthFrame_4SB','OI_SBC_SynthFrame_4SB'],
        'SynthFrame8SB':[None,'OI_SBC_SynthFrame_80','OI_SBC_SynthFrame_80']}.items():
        s=symbols[name]
        values=list(struct.unpack('<'+'I'*len(targets),at(s['address'],4*len(targets))))
        if values != [0 if target is None else symbols[target]['address'] for target in targets]:
            raise ValueError('actual ELF callback table mismatch: '+name)
        tables[name]=dict(**s,targets=targets,actual_words=[hex(v) for v in values],
            raw_sha256=hashlib.sha256(at(s['address'],s['bytes'])).hexdigest())
    (out/'actual_callback_tables.json').write_text(json.dumps(tables,indent=2)+'\n')
    return tables

def analyze(output,root):
    out=Path(output)
    d=json.loads((out/'verification.json').read_text());dis=(out/'firmware.dis').read_text()
    legacy=json.loads((root/'tools/ae350_ble_business_indirect_review.json').read_text())
    prior_by_caller={}
    for site in legacy['sites']:
        prior_by_caller.setdefault(site['caller'],[]).append(site)
    for caller,rows in prior_by_caller.items():
        assert len({tuple(x['targets']) for x in rows})==1,caller
    # Existing C callback configuration is unchanged; the source-TU identities of
    # those callback owners are checked before carrying the source points-to sets.
    for name in ['audio_clock_service.c','recording_service.c','business_mailbox.c','ble_business_owner.c']:
        rel='firmware/ae350/'+name
        assert legacy['input_sha256'][rel]==d['input_sha256'][rel],rel
    review_targets={name:rows[0]['targets'] for name,rows in prior_by_caller.items()}
    # Source table bounds and non-null choices, all measured assembly targets.
    # DecodeBody inlines OI_SBC_ReadSamplesJoint; it therefore contains the same
    # SpecializedReadSamples[0..1] call and has its own actual JALR site.
    review_targets.update({
        'OI_SBC_ComputeBitAllocation':['monoBitAllocation','dualBitAllocation','stereoBitAllocation'],
        'DecodeBody.part.0':['OI_SBC_ReadSamplesJoint4','OI_SBC_ReadSamplesJoint8'],
        'OI_SBC_SynthFrame':['OI_SBC_SynthFrame_4SB','OI_SBC_SynthFrame_80']})
    long_calls=direct_long_calls(dis)
    sites=[];all_sites=[];current=None
    for line in dis.splitlines():
        h=re.match(r'^[0-9a-f]+ <([^>]+)>:',line)
        if h:current=h[1]
        m=re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+',line)
        if m and int(m[2],16)&0x7f==0x67 and int(m[2],16)!=0x8067 and int(m[1],16) not in long_calls:
            row=dict(caller=current,address='0x'+m[1],instruction=m[2]);all_sites.append(row)
            if current in review_targets:sites.append(dict(**row,targets=review_targets[current]))
    counts=collections.Counter(s['caller'] for s in sites)
    for caller,rows in prior_by_caller.items():
        assert counts[caller]==len(rows),(caller,counts[caller],len(rows))
        actual=[s['instruction'] for s in sites if s['caller']==caller]
        assert actual==[s['instruction'] for s in rows],caller
    inputs=dict(d['input_sha256'])
    inputs['external/overlay/ui_main.c']=sha(out/'ui_main.c')
    inputs['external/combined_budget_adapter.c']=sha(out/'combined_budget_adapter.c')
    for path in (out/'adapted').rglob('*'):
        if path.is_file():inputs['external/adapted/'+str(path.relative_to(out/'adapted'))]=sha(path)
    review=dict(schema=1,input_sha256=inputs,disassembly_sha256=hashlib.sha256(dis.encode()).hexdigest(),
        source_target_review='''Budget-only actual combined firmware points-to audit. Maintained clock/record/business callback C owners have unchanged exact input identities versus the reviewed second-batch firmware; each original caller retains the same count and ordered JALR instruction bytes, with shifted actual addresses. Their sole installed bus objects target mmio_read/write, record_mmio_read/write or business_mmio_read/write as recorded. SBC bitalloc-sbc.c balloc[] contains monoBitAllocation,dualBitAllocation,stereoBitAllocation; a138_sbc format mode0..3 is checked before decode. decoder-sbc.c SpecializedReadSamples[] contains OI_SBC_ReadSamplesJoint4/8 and is used for4/8subbands; O2 inlines this table call into DecodeBody.part.0. synthesis-sbc.c SynthFrame4SB/8SB tables contain their respective4SB/80 routines for channel1/2; a138_sbc_decode validates negotiated format and the decoder derives those valid channel/subband counts. The two actual SynthFrame JALR sites conservatively include both non-null routines. Tablebytes and source identities are sealed. Unknown/unbounded frames, recursion, direct/tail calls not in the graph or any other reachable JALR fail closed. Interrupts are still disabled. This source/assembly budget does not prove DMA visibility, arbitrary memory corruption, protocol completeness, actual CPU cycles or hardware acceptance.''',sites=sites)
    (out/'combined_indirect_review.json').write_text(json.dumps(review,indent=2)+'\n')
    frames=[]
    for path in sorted(out.glob('*.su')):
        for line in path.read_text().splitlines():
            fn,n,kind=line.split('\t');frames.append(dict(function=fn,bytes=int(n),kind=kind))
    stack=call_chain_report(out,frames,dis,16384,reviewed_indirect_calls=review,input_sha256=inputs)
    required=['a138_combined_budget_init','a138_combined_budget_step','a138_classic_init',
        'a138_classic_begin','a138_classic_cancel','a138_classic_event','a138_classic_acl',
        'a138_classic_tick','a138_classic_delay_update',
        'a138_classic_tx_peek','a138_classic_tx_result','a138_classic_audio_ready',
        'a138_classic_frame_pop','a138_sbc_init','a138_sbc_begin','a138_sbc_cancel','a138_sbc_decode',
        'OI_CODEC_SBC_DecodeFrame','OI_CODEC_SBC_DecoderReset','OI_SBC_ComputeBitAllocation',
        'OI_SBC_ReadSamplesJoint4','OI_SBC_ReadSamplesJoint8','OI_SBC_SynthFrame_4SB','OI_SBC_SynthFrame_80',
        'a138_ble_business_firmware_init','a138_ble_business_firmware_pump']
    assert set(required)<=set(stack['reachable_functions']),set(required)-set(stack['reachable_functions'])
    assert not (out/'undefined.log').read_text().strip()
    # Read sizes from the actual RV32 ELF symbol table, including real alignment.
    objects={}
    for line in (out/'nm-size.log').read_text().splitlines():
        a=line.split()
        if len(a)==4 and a[3].startswith('budget_'):
            objects[a[3]]=dict(address=int(a[0],16),bytes=int(a[1],16),kind=a[2])
    # Compare the actual linked objects with a separately compiled, unlinked
    # C sizeof witness from the same public headers and RV32 compiler.
    witness={}
    for line in (out/'abi-witness-size.log').read_text().splitlines():
        row=line.split()
        if len(row)==4:witness[row[3]]=int(row[1],16)
    assert not re.search(r'\babi_\w+\s*$', (out/'firmware.nm').read_text(), re.M), 'ABI witness leaked into image'
    buffers=('classic','decoder','frame','tx','packet','pcm')
    controls=('operation','link_epoch','generation','rate','input_bytes','status',
              'decode_status','slot','now_ms','delay_tenths_ms')
    assert set(objects)=={'budget_'+n for n in (*buffers,*controls)}
    assert set(witness)=={'abi_'+n for n in (*buffers,'pcm_slot','u32')}
    for name in buffers:
        assert objects['budget_'+name]['bytes']==witness['abi_'+name],name
    for name in controls:
        assert objects['budget_'+name]['bytes']==witness['abi_u32'],name
    assert objects['budget_pcm']['bytes']==4*witness['abi_pcm_slot']
    assert d['linked_translation_units']==25 and len(d['compiled_sources'])==25
    assert d['unlinked_abi_witness']=='ae350_budget_abi_witness.o'
    result=dict(schema=1,verified=True,scope='retained ROM128 split executable and conservative service callgraph only',
        capacity=d['capacity'],stack=stack,required_live_roots=required,rv32_objects=objects,
        linked_undefined_symbols=0,all_nonreturn_JALR_sites=len(all_sites),reviewed_reachable_JALR_sites=len(sites),
        compiler_stack_frames=frames,original_service_callback_sites=len(legacy['sites']),
        budget_adapter_bytes=sum(x['bytes'] for x in objects.values()),
        rv32_abi_witness=witness,linked_translation_units=25,unlinked_witness_not_in_image=True,
        source_identity=hashlib.sha256(json.dumps(inputs,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        input_sha256=inputs,elf_sha256=sha(out/'firmware.elf'),binary_sha256=sha(out/'firmware.bin'),
        cache_policy='unchanged cache-off loader; no cache enable instructions added',
        no_gc_sections=True,no_LTO=True,selected_in_production=False,hardware_watermark_verified=False,
        runtime_protocol_closed=False,cycles_measured=False,synthesis_performed=False,hardware_operated=False)
    (out/'callgraph_verification.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
