#!/usr/bin/env python3
"""Actual UI snapshots, D numeric pixels, safe mode bounds and analysis retention."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
F=ROOT/'firmware/ae350'
HOST=Path(__file__).with_name('ae350_ui_truth_host.c')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(output):
 output.mkdir(parents=True,exist_ok=False);source=output/'source';source.mkdir()
 inputs=[F/'ui_main.c',F/'ui_render.c',*sorted(F.glob('*.h')),HOST,Path(__file__).resolve()]
 hashes={str(p):sha(p) for p in inputs}
 for p in inputs[:-2]:(source/p.name).write_bytes(p.read_bytes())
 audio=(source/'audio_services.h').read_text();a=audio.index('static inline void a138_fence(void)');b=audio.index('static inline int a138_probe(',a)
 adapted='''uint32_t ui_host_read(uintptr_t,uint32_t);
void ui_host_write(uintptr_t,uint32_t,uint32_t);
void ui_host_fence(void);
static inline void a138_fence(void){ui_host_fence();}
static inline uint32_t a138_read(uintptr_t base,uint32_t off){return ui_host_read(base,off);}
static inline void a138_write(uintptr_t base,uint32_t off,uint32_t value){ui_host_write(base,off,value);}
'''
 (source/'audio_services.h').write_text(audio[:a]+adapted+audio[b:])
 p=source/'firmware_checks.h';s=p.read_text()
 old='static volatile uint32_t *const diagnostic=(volatile uint32_t *)UINT32_C(0xf8000000);'
 assert s.count(old)==1;s=s.replace(old,'extern volatile uint32_t ui_host_diagnostic[8];\nstatic volatile uint32_t *const diagnostic=ui_host_diagnostic;')
 old='''static void fail(uint32_t reason) {
    diagnostic[1]=reason;
    for(;;) { __asm__ volatile("nop"); }
}'''
 assert s.count(old)==1;s=s.replace(old,'void ui_host_fail(uint32_t);\nstatic void fail(uint32_t reason){ui_host_fail(reason);}')
 p.write_text(s)
 cc=shutil.which('clang');assert cc
 result=dict(passed=False,input_sha256=hashes,validation_stage='offline-actual-ui-snapshot-and-pixels',hardware_tested=False,physical_service_interval_verified=False,cases={})
 try:
  for role in ('M','W'):
   for sanitize in (False,True):
    name=role+('-asan' if sanitize else '-native');flags=['-DA138_SINGLE_BLE_RECORDING'] if role=='W' else []
    if sanitize:flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    cmd=[cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function','-I',str(source),*flags,str(HOST),'-o',str(output/name)]
    compiled=subprocess.run(cmd,capture_output=True,text=True);(output/(name+'-compile.log')).write_text(compiled.stdout+compiled.stderr);compiled.check_returncode()
    p=subprocess.run([str(output/name)],capture_output=True,text=True);log=p.stdout+p.stderr;(output/(name+'.log')).write_text(log)
    if p.returncode:raise RuntimeError(log)
    assert 'PASS ui_truth ' in log
    result['cases'][name]=dict(passed=True,result=log.strip(),compile_argv=cmd);print(log.strip(),flush=True)
  assert hashes=={str(p):sha(p) for p in inputs};result['passed']=True
 finally:
  (output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);run(p.parse_args().output.resolve())
