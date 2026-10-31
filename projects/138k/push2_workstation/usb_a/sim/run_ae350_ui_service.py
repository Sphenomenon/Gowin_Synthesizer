#!/usr/bin/env python3
"""Actual ui_main bounded services, maintained full-render pixels, and real APB replay."""
from pathlib import Path
import argparse,hashlib,json,re,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1]
F=ROOT/'firmware/ae350';HOST=Path(__file__).with_name('ae350_ui_service_host.c');TB=Path(__file__).with_name('tb_ae350_ui_service_replay.sv')
MAP=ROOT/'rtl/ddr_address_map.vh'
APB=ROOT/'baselines/objects/60dae3b5e3be5888511639ea033a5e9fd71c1e16009bcaf3aa73a289873b906d.sv'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(output):
 output.mkdir(parents=True,exist_ok=False)
 inputs=[F/n for n in ('ui_main.c','ui_render.c','ui_render.h','ui_model.h','audio_services.h','firmware_checks.h','audio_clock_service.h')]+[HOST,TB,APB,MAP,Path(__file__).resolve()]
 hashes={str(p):sha(p) for p in inputs};assert sha(APB)==APB.stem
 result=dict(schema=1,passed=False,input_sha256=hashes,actual_ui_main=True,actual_UI_APB_replay=True,reference_policy='maintained full renderer compiled independently',reference_sha256=sha(F/'ui_render.c'),host_low_level_IO_adapted=True,CPU_cycles_measured=False,physical_service_interval_verified=False,hardware_operated=False,EDA_invoked=False,release_ready=False,deployment_allowed=False,cases={})
 def execute(argv,folder,name,expect=True):
  p=subprocess.run(argv,cwd=folder,capture_output=True,text=True,timeout=120);log=p.stdout+p.stderr;(folder/(name+'.log')).write_text(log)
  if expect and p.returncode:raise ValueError(name+' failed '+log[-5000:])
  return p,log
 try:
  source=output/'source';source.mkdir()
  for p in inputs[:7]:(source/p.name).write_bytes(p.read_bytes())
  include=source/'src/memory';include.mkdir(parents=True);(include/'ddr_address_map.vh').write_bytes(MAP.read_bytes())
  audio=(source/'audio_services.h').read_text();start=audio.index('static inline void a138_fence(void)');end=audio.index('static inline int a138_probe(',start)
  old=audio[start:end]
  adapted='''uint32_t ui_host_read(uintptr_t,uint32_t);
void ui_host_write(uintptr_t,uint32_t,uint32_t);
void ui_host_fence(void);
static inline void a138_fence(void){ui_host_fence();}
static inline uint32_t a138_read(uintptr_t base,uint32_t off){a138_fence();uint32_t v=ui_host_read(base,off);a138_fence();return v;}
static inline void a138_write(uintptr_t base,uint32_t off,uint32_t value){a138_fence();ui_host_write(base,off,value);a138_fence();}
'''
  assert audio.count(old)==1;(source/'audio_services.h').write_text(audio.replace(old,adapted,1))
  checks=(source/'firmware_checks.h').read_text()
  old='static volatile uint32_t *const diagnostic=(volatile uint32_t *)UINT32_C(0xf8000000);'
  new='extern volatile uint32_t ui_host_diagnostic[8];\nstatic volatile uint32_t *const diagnostic=ui_host_diagnostic;'
  assert checks.count(old)==1;checks=checks.replace(old,new,1)
  old='''static void fail(uint32_t reason) {
    diagnostic[1]=reason;
    for(;;) { __asm__ volatile("nop"); }
}'''
  assert checks.count(old)==1;checks=checks.replace(old,'void ui_host_fail(uint32_t);\nstatic void fail(uint32_t reason){ui_host_fail(reason);}',1)
  (source/'firmware_checks.h').write_text(checks)
  reference=(source/'ui_render.c').read_bytes()
  result['reference_policy']='maintained full renderer compiled independently'
  result['reference_sha256']=hashlib.sha256(reference).hexdigest()
  (source/'reference_ui_render.c').write_bytes(reference)
  cc=shutil.which('clang');assert cc
  common=[cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function','-I',str(source)]
  for name,sanitize in [('native',False),('san',True)]:
   folder=output/name;folder.mkdir();flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if sanitize else[]
   execute([*common,*flags,'-Dui_render=reference_ui_render','-Dui_patch=reference_ui_patch','-Dui_render_rows=reference_ui_render_rows','-Dui_patch_rows=reference_ui_patch_rows','-c',str(source/'reference_ui_render.c'),'-o','reference.o'],folder,'reference')
   execute([*common,*flags,str(HOST),str(source/'ui_render.c'),'reference.o','-o','host'],folder,'compile')
   _,log=execute([str(folder/'host'),str(folder/'trace.txt')],folder,'run');assert 'PASS ui_service ' in log
   execute(['iverilog','-g2012','-I',str(source),'-s','tb_ae350_ui_service_replay','-o','replay.vvp',str(APB),str(TB)],folder,'APB_compile')
   _,replay=execute(['vvp',str(folder/'replay.vvp'),'+TRACE='+str(folder/'trace.txt')],folder,'APB_run');assert 'PASS actual_ui_APB_replay' in replay
   result['cases'][name]=dict(passed=True,metrics={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',log)},APB_metrics={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',replay)})
  original=(source/'ui_main.c').read_text()
  mutants={
   'publish_before_final_slice':('if(j->row>=UI_FRAME_ROWS)','if(j->row>=UI_SLICE_ROWS)'),
   'lose_frozen_model':('.old=pages[back],.target=*m,.active=1','.old=pages[back],.target=pages[back],.active=1'),
   'front_before_real_ACK':('int result=present_step(&j->present);if(result<=0)return result;','*front=j->page;int result=present_step(&j->present);if(result<=0)return result;'),
   'erase_accepted_publication':('if(j->present.active)j->cancelled=1;','if(j->present.active){valid[j->page]=0;j->active=0;}'),
   'lose_later_model_update':('if(!r->drawing.active && r->revision!=r->shown)','if(!r->drawing.active && r->revision!=r->shown && r->shown==1)'),
   'ignore_capture_drain_budget':('if(!--j->left){j->error=1;j->state=4;}','if(0){j->error=1;j->state=4;}'),
   'skip_real_voice_release':('if(state[0])return','if(0)return'),
   'resurrect_gate_after_PANIC':('if(j->active)j->target.gate=0;','if(j->active)j->target.gate=1;'),
   'apply_control_before_observed_PANIC':('        if(control_step(&r->control)<0)fail(0xbad03002);',''),
   'hide_PANIC_on_torn_touch':('unsigned panic=r->model.panic_epoch,changed=(unsigned)read_model(&r->model);','unsigned panic=r->model.panic_epoch,changed=0; if(ur(40)==ur(40))changed=(unsigned)read_model(&r->model);'),
   'hide_PANIC_on_torn_audio_snapshot':('unsigned changed=ui_panic(m,pitch>>22);\n changed|=read_clock_model(m);\n if(sequence!=a138_read(AUDIO_BASE,0x1a0))return (int)changed;','if(sequence!=a138_read(AUDIO_BASE,0x1a0))return 0;\n unsigned changed=ui_panic(m,pitch>>22);'),
   'draw_whole_patch_in_one_step':('ui_patch_rows(frame[j->page],&j->old,&j->target,j->old_touch,j->touch,j->row,UI_SLICE_ROWS);','ui_patch(frame[j->page],&j->old,&j->target,j->old_touch,j->touch);'),
  }
  result['negative_controls']={}
  for name,(old,new) in mutants.items():
   assert original.count(old)==1,(name,'anchor drift');folder=output/name;folder.mkdir()
   mutant=folder/'ui_main.c';changed=original.replace(old,new,1)
   if name=='apply_control_before_observed_PANIC':
    anchor='        diagnostic[5]=0x55490000u';assert changed.count(anchor)==1
    changed=changed.replace(anchor,old+'\n'+anchor,1)
   mutant.write_text(changed)
   flags=[cc,*common[1:-2],'-Wno-unused-parameter','-I',str(folder),'-I',str(source)]
   execute([*flags,str(HOST),str(source/'ui_render.c'),str(output/'native/reference.o'),'-o','host'],folder,'compile')
   process,log=execute([str(folder/'host'),str(folder/'trace.txt')],folder,'run',False)
   assert process.returncode!=0 and ('FAIL ' in log or 'firmware fail ' in log),name+' escaped '+log
   result['negative_controls'][name]=dict(rejected=True,exit_code=process.returncode,source_sha256=sha(mutant),reason=log.strip())
   print('REJECTED '+name,flush=True)
  result['host_adapted_sha256']={str(p.relative_to(source)):sha(p) for p in source.rglob('*') if p.is_file()}
  result['compiler_path']=cc;result['compiler_sha256']=sha(cc)
  assert hashes=={str(p):sha(p)for p in inputs};result['passed']=True
 finally:
  result['output_sha256']={str(p.relative_to(output)):sha(p) for p in output.rglob('*') if p.is_file() and p.name!='verification.json'}
  (output/'verification.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
 print(json.dumps({k:result[k] for k in ('passed','cases','actual_ui_main','actual_UI_APB_replay')}))
if __name__=='__main__':
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('--output',type=Path,required=True);run(a.parse_args().output.resolve())
