#!/usr/bin/env python3
"""Real FAST12/FAT/WAV/CRC/PCM oracle for the opt-in metadata sector cache.

Only a new evidence directory is written. Existing fixtures and RTL are read;
destructive source controls are copies within the evidence directory. Long
cases preserve FAST12=12, 4096-byte/4096-frame queues and 3072-frame prefill.
"""
from pathlib import Path
import argparse,binascii,collections,concurrent.futures,hashlib,importlib.util,json,re,subprocess

ROOT=Path(__file__).resolve().parents[2]
SIM=ROOT/'sim/tf_audio';RTL=ROOT/'rtl/tf_audio';STORAGE=RTL/'storage'
SOURCES=[RTL/'workstation_tf_direct_native_v1.sv',RTL/'workstation_tf_direct_ingress_v1.sv',
         STORAGE/'workstation_tf_file_reader.sv',STORAGE/'workstation_tf_sd_sector_reader.sv',
         STORAGE/'workstation_tf_spi_session.sv',STORAGE/'workstation_tf_wav_pcm_decoder_v1.sv',
         STORAGE/'workstation_tf_wav_chunk_parser_v1.sv',STORAGE/'workstation_tf_sd_crc16_v1.sv',
         STORAGE/'workstation_tf_fat_sector_cache_v1.sv']
TB=SIM/'tb_workstation_tf_fat_cache_wire.sv';CARD=SIM/'workstation_tf_sd_crc_wire_card.sv'
BUILDER=SIM/'run_workstation_tf_direct_native_wire.py'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def builder():
    spec=importlib.util.spec_from_file_location('fat_cache_wire_original_oracle',BUILDER)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m


def disk(folder,fs,rate,frames,stride):
    """Keep the original WAV/oracles; relocate file sectors and rebuild FAT.

    Sparse input is a normal supported FAT16/32 volume. Neither adjacency nor
    a cache-specific disk representation is communicated to the DUT.
    """
    original=builder().disk(folder,fs,False,rate,frames,97,0)
    image=bytes(int(x,16) for x in (folder/'image.hex').read_text().split())
    lbas=[int(x,16) for x in (folder/'lbas.hex').read_text().split()]
    blocks={lba:bytearray(image[i*512:(i+1)*512]) for i,lba in enumerate(lbas) if lba!=0xffffffff}
    spf=17 if fs==16 else 513;data_base=20 if fs==16 else 514
    chains=[];payloads=[]
    for index,length in enumerate(original['file_lengths']):
        count=(length+511)//512
        old=[3+index+i*4 for i in range(count)]
        payloads.append([blocks.pop(data_base+c-2) for c in old])
        chains.append([3+index+i*stride for i in range(count)])
    for lba in list(blocks):
        if 1<=lba<1+spf:del blocks[lba]
    width=2 if fs==16 else 4;end=0xfff9 if fs==16 else 0x0ffffff9
    def fat(cluster,value):
        offset=cluster*width;lba=1+offset//512
        target=blocks.setdefault(lba,bytearray(512))
        target[offset%512:offset%512+width]=value.to_bytes(width,'little')
    fat(0,end);fat(1,end)
    if fs==32:fat(2,end)
    for chain,pieces in zip(chains,payloads):
        for i,(cluster,payload) in enumerate(zip(chain,pieces)):
            assert cluster<(4096 if fs==16 else 65536)+2
            fat(cluster,chain[i+1] if i+1<len(chain) else end)
            lba=data_base+cluster-2
            assert lba not in blocks
            blocks[lba]=payload
    ordered=sorted(blocks);assert len(ordered)<=512
    image_out=bytearray(262144);lbas_out=[0xffffffff]*512
    for i,lba in enumerate(ordered):image_out[i*512:(i+1)*512]=blocks[lba];lbas_out[i]=lba
    (folder/'image.hex').write_text(''.join(f'{v:02x}\n' for v in image_out))
    (folder/'lbas.hex').write_text(''.join(f'{v:08x}\n' for v in lbas_out))
    crc=[binascii.crc_hqx(image_out[i*512:(i+1)*512],0) for i in range(512)]
    (folder/'crc16.hex').write_text(''.join(f'{v:04x}\n' for v in crc))
    expected_misses=len({1+(c*width)//512 for c in chains[0]})
    manifest=dict(original=original,cluster_stride=stride,chains=chains,sectors_per_cluster=1,
                  file0_data_sectors=len(chains[0]),file0_expected_FAT_CMD17=expected_misses,
                  file0_expected_cache_hits=len(chains[0])-expected_misses,
                  independent_CRC_oracle='Python binascii.crc_hqx(full sector, 0)',
                  image_sha256=sha(folder/'image.hex'),LBA_sha256=sha(folder/'lbas.hex'),CRC_sha256=sha(folder/'crc16.hex'))
    (folder/'cache_disk.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


def scope(binary):
    modules=collections.Counter(re.findall(r'\.scope module, "[^"]+" "([^"]+)"',binary.read_text()))
    required=[p.stem for p in SOURCES]+[CARD.stem,TB.stem]
    assert set(modules)==set(required),dict(modules)
    assert all(modules[n]==1 for n in required),dict(modules)
    return dict(actual_VVP_sha256=sha(binary),module_counts=dict(modules),
                exactly_one_native_file_sector_session_checker_cache=True)


def scenarios():
    return [dict(name='FAST12_48000_long',mode=0,fs=16,rate=48000,frames=11000,stride=4),
            dict(name='FAST12_44100_long',mode=0,fs=16,rate=44100,frames=11000,stride=4),
            dict(name='FAT16_fragmented_keys',mode=0,fs=16,rate=48000,frames=500,stride=260),
            dict(name='FAT32_fragmented_keys',mode=0,fs=32,rate=48000,frames=500,stride=260),
            dict(name='CRC_bad_FAT_fill',mode=1,fs=16,rate=48000,frames=500,stride=4),
            dict(name='STOP_during_FAT_fill',mode=2,fs=16,rate=48000,frames=500,stride=4),
            dict(name='STOP_during_cache_lookup',mode=3,fs=16,rate=48000,frames=500,stride=4)]


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--case',action='append')
    ap.add_argument('--no-negatives',action='store_true')
    args=ap.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    assert binascii.crc_hqx(b'123456789',0)==0x31c3
    inputs=[*SOURCES,TB,CARD,BUILDER,SIM/'run_workstation_tf_direct_ingress.py',Path(__file__).resolve()]
    before={str(p):sha(p) for p in inputs}
    result=dict(schema=1,passed=False,input_sha256=before,cases={},negative_controls={},
        real_SPI_FAT_WAV_PCM=True,public_DUT_ports_only=True,read_only_hierarchical_metrics=True,
        default_FAST12_preserved=True,default_3072_prefill_preserved=True,
        independent_continuous_50MHz_audio_deadlines=True,
        CRC_before_PCM_isolation_proven=False,arbitrary_fragmentation_thrash_supply_guarantee=False,
        physical_card_integrity_or_throughput_verified=False,synthesis=False,pnr=False,
        hardware_operated=False,sram_programmed=False,flash_written=False,
        release_ready=False,deployment_allowed=False)

    def execute(case,cache_source=None,expected_failure=None):
        folder=out/case['name'];manifest=disk(folder,case['fs'],case['rate'],case['frames'],case['stride'])
        params=dict(MODE=case['mode'],RATE=case['rate'],FRAMES0=case['frames'],
                    EXPECTED_FAT_MISSES=manifest['file0_expected_FAT_CMD17'],
                    EXPECT_CACHE_HITS=int(manifest['file0_expected_cache_hits']>0))
        selected=list(SOURCES)
        if cache_source:selected[-1]=cache_source
        command=['iverilog','-g2012','-s',TB.stem,'-o',str(folder/'sim.vvp')]
        command+=['-P'+TB.stem+'.'+k+'='+str(v) for k,v in params.items()]
        command+=list(map(str,[*selected,TB,CARD]))
        p=subprocess.run(command,capture_output=True,text=True,timeout=60)
        (folder/'compile.log').write_text(p.stdout+p.stderr)
        if p.returncode:raise ValueError(case['name']+' compile '+p.stdout+p.stderr)
        closure=scope(folder/'sim.vvp')
        argv=['vvp',str(folder/'sim.vvp'),'+IMAGE='+str(folder/'image.hex'),'+LBAS='+str(folder/'lbas.hex'),
              '+CRC16='+str(folder/'crc16.hex'),'+ORACLE0='+str(folder/'oracle0.hex'),'+ORACLE1='+str(folder/'oracle1.hex')]
        p=subprocess.run(argv,capture_output=True,text=True,timeout=600);log=p.stdout+p.stderr
        (folder/'run.log').write_text(log)
        if expected_failure:
            if p.returncode==0 or expected_failure not in log or 'timeout' in log:
                raise ValueError(case['name']+' negative escaped/unrelated '+log)
        elif p.returncode or 'PASS tf_fat_cache_wire' not in log:
            raise ValueError(case['name']+' failed '+log)
        metrics={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',log.split('PASS tf_fat_cache_wire')[-1])}
        data=[{k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',s)} for s in log.splitlines() if s.startswith('METRIC_DATA')]
        fat=[{k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',s)} for s in log.splitlines() if s.startswith('METRIC_FAT')]
        intervals=[b['cycle']-a['cycle'] for a,b in zip(data,data[1:])]
        interval_counts=dict(collections.Counter(intervals))
        if not expected_failure and case['mode']==0:
            assert len(fat)==manifest['file0_expected_FAT_CMD17']
            assert len(data)==manifest['file0_data_sectors']
            assert metrics['first_hits']==manifest['file0_expected_cache_hits']
        record=dict(passed=not bool(expected_failure),rejected=bool(expected_failure),parameters=params,
            disk=manifest,elaborated_scope=closure,source_sha256={str(p):sha(p) for p in selected},
            compile_argv=command,run_argv=argv,returncode=p.returncode,
            compile_log_sha256=sha(folder/'compile.log'),run_log_sha256=sha(folder/'run.log'),run_log=log,
            metrics=metrics,data_sector_requests=data,FAT_sector_requests=fat,
            data_request_interval_clock_histogram=interval_counts)
        if data and len(data)>1:
            record['finite_data_sector_rate_Bps']=(len(data)-1)*512*50000000/(data[-1]['cycle']-data[0]['cycle'])
        print(('PASS rejected ' if expected_failure else 'PASS ')+case['name'],flush=True)
        return case['name'],record

    try:
        selected=[c for c in scenarios() if args.case is None or c['name'] in args.case]
        if not selected:raise ValueError('empty FAT cache case selection')
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            for name,record in pool.map(execute,selected):result['cases'][name]=record
        if not args.no_negatives:
            by={c['name']:c for c in scenarios()};source=SOURCES[-1].read_text()
            controls=[('wrong_LBA_key','key_lba==lookup_lba_i',"1'b1",'FAT16_fragmented_keys','FAT cache supply/oracle completion failed'),
                      ('early_line_publication','valid<=0;fill_live<=1;', 'valid<=1;fill_live<=1;','CRC_bad_FAT_fill','unverified FAT fill published early'),
                      ('ignored_invalidation','else if(invalidate_i)begin',"else if(1'b0)begin",'STOP_during_FAT_fill','FAT cache STOP/error retained or republished line')]
            for name,old,new,basis,error in controls:
                if source.count(old)!=1:raise ValueError('FAT cache negative anchor drift '+name)
                copy=out/(name+'.sv');copy.write_text(source.replace(old,new))
                case=dict(by[basis]);case['name']='negative_'+name
                key,record=execute(case,copy,error);record['exact_mutation_anchor_count']=1
                result['negative_controls'][key]=record
        result['inputs_unchanged']=before=={str(p):sha(p) for p in inputs}
        if not result['inputs_unchanged']:raise ValueError('FAT cache wire source drift')
        result['passed']=True
    finally:(out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
