#!/usr/bin/env python3
"""Native SPI/FAT/WAV -> LAST FIFO -> real final router/PCM bridge/I2S oracle."""
from pathlib import Path
import argparse,collections,concurrent.futures,hashlib,importlib.util,json,re,subprocess
ROOT=Path(__file__).resolve().parents[2];SIM=ROOT/'sim/tf_audio';RTL=ROOT/'rtl'
spec=importlib.util.spec_from_file_location('native_wire_fixture',SIM/'run_workstation_tf_direct_native_wire.py')
NATIVE=importlib.util.module_from_spec(spec);spec.loader.exec_module(NATIVE)
SOURCES=[*NATIVE.SOURCES,RTL/'tf_audio/workstation_tf_frame_bridge_v2.sv',RTL/'tf_audio/workstation_tf_physical_tail_v1.sv',RTL/'audio/workstation_final_pcm_router.sv',RTL/'audio/workstation_pcm_frame_bridge.sv',RTL/'audio/workstation_i2s_serializer.sv',RTL/'audio/workstation_pcm_observation_bridge.sv',RTL/'music/music_async_fifo.sv',RTL/'migration/workstation_runtime_counter_cdc.sv']
TB=SIM/'workstation_tf_physical_native_tb.sv';CARD=SIM/'workstation_tf_file_wire_card.sv'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def no_DDR(binary):
    text=binary.read_text();counts=collections.Counter(re.findall(r'\.scope module, "[^"]+" "([^"]+)"',text))
    counts.pop('tb_workstation_tf_physical_native');counts.pop('workstation_tf_file_wire_card')
    expected=collections.Counter({p.stem:1 for p in SOURCES});expected['gw138k_counter_cdc']=3;expected.pop('workstation_runtime_counter_cdc');expected['music_async_fifo']=2
    if counts!=expected:raise ValueError('unexpected physical closure/request source '+str(counts))
    ports=re.findall(r'\.port_info[^\n]*"([^"]+)"',text)
    forbidden=[p for p in ports if re.search(r'(?:^|_)ddr(?:_|$)|(?:^|_)app_(?:addr|cmd)|memory_request',p,re.I)]
    if forbidden:raise ValueError('DDR API in actual composed closure '+str(forbidden))
    return dict(module_counts=dict(counts),DDR_ports=[],DDR_request_sources=0,VVP_sha256=sha(binary),whole_workstation_owner4_trace_verified=False)
def scenarios():
    result=[]
    for rate in (48000,44100):
        for fs,part in ((16,False),(32,True)):
            result.append((f'physical_fat{fs}_{rate}',rate,fs,part,0,97))
        for mode,name in ((2,'cancel_in_LAST_FIFO'),(3,'cancel_on_LAST_admission'),(4,'cancel_after_router_tail'),(5,'cancel_during_serial_tail'),(8,'missing_last_PCM_return')):
            result.append((f'{name}_{rate}',rate,16,False,mode,97))
        result.append((f'physical_pause_head_{rate}',rate,16,False,1,97))
    result.append(('physical_source_drop_prefix',48000,16,False,7,97))
    result.append(('physical_FAST12_supply_failure',48000,16,False,9,11000))
    return result
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--case',action='append');args=ap.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    helpers=[Path(__file__).resolve(),SIM/'run_workstation_tf_direct_native_wire.py',SIM/'run_workstation_tf_direct_ingress.py']
    contracts=[RTL/'tf_audio'/name for name in ('WORKSTATION_TF_DIRECT_NATIVE_V1_CONTRACT.md','WORKSTATION_TF_DIRECT_INGRESS_V1_CONTRACT.md','WORKSTATION_TF_FRAME_BRIDGE_V2_CONTRACT.md','WORKSTATION_TF_PHYSICAL_TAIL_V1_CONTRACT.md','workstation_tf_frame_bridge_v2.provenance.json','provenance/workstation_tf_frame_bridge_v2.patch')]
    inputs=[*SOURCES,TB,CARD,*helpers,*contracts];hashes={str(p):sha(p) for p in inputs}
    result=dict(schema=1,passed=False,input_sha256=hashes,cases={},real_SPI_FAT_WAV_PCM_I2S=True,source_autonomous_sample_tick=False,actual_serializer_requests=True,profile_selected=False,whole_workstation_owner4_trace_verified=False,physical_CDC_verified=False,hardware_operated=False,deployment_allowed=False)
    def execute(case):
        name,rate,fs,partition,mode,count=case;folder=out/name
        disk=NATIVE.disk(folder,fs,partition,rate,count,97,0)
        compile_cmd=['iverilog','-g2012','-s','tb_workstation_tf_physical_native','-o',str(folder/'sim.vvp'),'-Ptb_workstation_tf_physical_native.RATE='+str(rate),'-Ptb_workstation_tf_physical_native.MODE='+str(mode),'-Ptb_workstation_tf_physical_native.FRAMES0='+str(count),*map(str,[*SOURCES,TB,CARD])]
        if mode==9:compile_cmd.insert(8,'-Ptb_workstation_tf_physical_native.FAST_DIV=12')
        p=subprocess.run(compile_cmd,capture_output=True,text=True,timeout=60);(folder/'compile.log').write_text(p.stdout+p.stderr)
        if p.returncode:raise ValueError(name+' compile '+p.stdout+p.stderr)
        closure=no_DDR(folder/'sim.vvp');(folder/'scope.json').write_text(json.dumps(closure,sort_keys=True,indent=2)+'\n')
        command=['vvp',str(folder/'sim.vvp'),'+IMAGE='+str(folder/'image.hex'),'+LBAS='+str(folder/'lbas.hex'),'+ORACLE0='+str(folder/'oracle0.hex'),'+ORACLE1='+str(folder/'oracle1.hex')]
        p=subprocess.run(command,capture_output=True,text=True,timeout=480);log=p.stdout+p.stderr;(folder/'run.log').write_text(log)
        if p.returncode or 'PASS tf_physical_native' not in log:raise ValueError(name+' failed '+log)
        print('PASS '+name,flush=True)
        return name,dict(passed=True,disk=disk,no_DDR_closure=closure,metrics={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',log)},compile_argv=compile_cmd,run_argv=command,compile_log_sha256=sha(folder/'compile.log'),run_log_sha256=sha(folder/'run.log'))
    try:
        cases=[c for c in scenarios() if args.case is None or c[0] in args.case]
        assert cases,'empty case selection'
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            for name,record in pool.map(execute,cases):result['cases'][name]=record
        assert hashes=={str(p):sha(p) for p in inputs},'input drift';result['passed']=True
    finally:(out/'verification.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    print(json.dumps(dict(passed=True,cases=len(result['cases']))))
if __name__=='__main__':main()
