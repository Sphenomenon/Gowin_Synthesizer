#!/usr/bin/env python3
"""Explicit source-stage PCM ingress through actual native effects and I2S."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess
from run_runtime_controlled import runtime_sources,ROOT

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--d-only',action='store_true');p.add_argument('--old-d-process',action='store_true');a=p.parse_args()
    project=a.project.resolve();out=a.output.resolve();out.mkdir(parents=True)
    if any(out.iterdir()):raise FileExistsError(out)
    tb=Path(__file__).with_name('tb_ae350_pcm_runtime.sv')
    sources=runtime_sources(project,tb)+[ROOT/'rtl/audio/workstation_ae350_pcm_owner.sv',ROOT/'rtl/audio/workstation_ae350_pcm_session.sv']
    original_source=ROOT/'rtl/audio/gw138k_event_workstation.sv'
    if a.old_d_process:
        assert a.d_only,'old numeric reference is only selected by the D regression'
        old=re.search(r'  function automatic signed \[31:0\] d_process_old_reference\(.*?  endfunction',
            (ROOT/'sim/audio/fixtures/d_process_before_exact_mask.svh').read_text(),re.S)[0].replace('d_process_old_reference','d_process')
        assert hashlib.sha256(old.encode()).hexdigest()=='11247717c12f218bd37fe96d399cc6a6e1ae6b7aa6228388bd3c9a6d414742e2'
        text=original_source.read_text();match=re.search(r'  function automatic signed \[31:0\] d_process\(.*?  endfunction',text,re.S)
        reference=out/'gw138k_event_workstation_old_numeric.sv';reference.write_text(text[:match.start()]+old+text[match.end():])
        sources=[reference if x==original_source else x for x in sources]
    inputs=list(dict.fromkeys(sources+[Path(__file__).resolve(),Path(__file__).with_name('run_runtime_controlled.py'),
        ROOT/'rtl/audio/runtime_spatial_room_preset.svh',ROOT/'tools/workstation_runtime_counter.py',
        ROOT/'sim/audio/fixtures/d_process_before_exact_mask.svh',original_source]))
    for path in ('sim/data','sim/matlab/output','rtl/audio/scope_vec/data'):inputs+=sorted((project/path).rglob('*.mem'))
    inputs+=[project/'rtl/audio/spatial_room_preset.svh']
    hashes={str(p):sha(p) for p in inputs}
    record=dict(schema=1,stage='actual-runtime-source-simulation',passed=False,input_sha256=hashes,
        hardware_accepted=False,synthesis_verified=False,physical_timing_verified=False,sustained_verified=False,
        measured_total_delay_valid=False,d_only=a.d_only,old_d_process_reference=a.old_d_process,limits='Ideal clocks and ordered DDR model; no HCI/SBC runtime integration, physical timing or hardware')
    try:
        argv=['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module','tb_ae350_pcm_runtime','--Mdir',str(out/'obj'),'-I'+str(ROOT),'-I'+str(project),*map(str,sources)]
        if a.d_only:argv+=['-GD_ONLY_MODE=1']
        record['compile_argv']=argv
        with (out/'compile.log').open('w') as f:subprocess.run(argv,cwd=project,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=300)
        with (out/'run.log').open('w') as f:subprocess.run([str(out/'obj/Vtb_ae350_pcm_runtime')],cwd=project,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=240)
        log=(out/'run.log').read_text();assert ('PASS D real APB/CDC owner' if a.d_only else 'PASS AE350 PCM real APB/CDC') in log,log
        assert all(sha(Path(p))==v for p,v in hashes.items()),'input drift during simulation'
        record['passed']=True;print(log)
    finally:(out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
if __name__=='__main__':main()
