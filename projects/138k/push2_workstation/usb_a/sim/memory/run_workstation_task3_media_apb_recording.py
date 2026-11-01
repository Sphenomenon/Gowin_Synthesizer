#!/usr/bin/env python3
"""F807 software aperture -> bounded pacer -> actual maintained recorder oracle."""
from pathlib import Path
import argparse,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(out):
    out.mkdir(parents=True,exist_ok=False)
    rels=('rtl/services/workstation_task3_media_apb_service.sv','rtl/workstation/workstation_task3_record_ingress.sv',
          'rtl/bluetooth/cpu_owner/workstation_ble_record_data_engine.sv','sim/memory/tb_workstation_task3_media_apb_recording.sv')
    sources=[ROOT/r for r in rels];inputs={str(p):sha(p)for p in[*sources,Path(__file__).resolve()]}
    build=['verilator','--binary','--timing','--build-jobs','4','-Wno-fatal','--top-module',
           'tb_workstation_task3_media_apb_recording','--Mdir',str(out/'obj'),*map(str,sources)]
    result=dict(schema=1,passed=False,source_sha256=inputs,build_argv=build,actual_engine=True,
        actual_recorded_frames=16,selected_board_profile=False,LCD_link_ready=False,software_injection_only=True,hardware_operated=False)
    try:
        with(out/'build.log').open('w')as log:p=subprocess.run(build,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        result['build_exit']=p.returncode
        if p.returncode or 'UNOPTFLAT' in (out/'build.log').read_text():raise RuntimeError('APB recorder build/comb-loop audit failed: '+str(out/'build.log'))
        with(out/'run.log').open('w')as log:p=subprocess.run([str(out/'obj/Vtb_workstation_task3_media_apb_recording')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        text=(out/'run.log').read_text();print(text)
        result.update(run_exit=p.returncode,log=text,build_log_sha256=sha(out/'build.log'),run_log_sha256=sha(out/'run.log'))
        if p.returncode or 'PASS task3_media_APB_recording'not in text:raise RuntimeError('APB recorder failed')
        if inputs!={str(p):sha(p)for p in[*sources,Path(__file__).resolve()]}:raise ValueError('source changed')
        result['passed']=True
    finally:(out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);run(p.parse_args().output.resolve())
