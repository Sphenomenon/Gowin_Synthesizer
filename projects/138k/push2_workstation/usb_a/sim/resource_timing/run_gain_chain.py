#!/usr/bin/env python3
"""Compare actual pre/post timing effect chains under changing gain targets."""
from pathlib import Path
import argparse,subprocess,hashlib,json
ROOT=Path(__file__).resolve().parents[2];BASE=ROOT/'results/resource_rework_final_route0_20261020_041042/Prj1'
def main():
 p=argparse.ArgumentParser();p.add_argument('build',type=Path);a=p.parse_args();build=a.build.resolve();stage=build/'Prj1';out=build/'gain_chain_ab';out.mkdir(exist_ok=True)
 original=(ROOT/'out/resource_effect_chain/tb.sv').read_text()
 original=original.replace('integer frames=0,maxlat=0,latency=0;', '''reg[15:0] sg=8192,pg=8192;integer fd;
integer frames=0,maxlat=0,latency=0;''')
 original=original.replace(".synth_gain_i(16'd8192),.pcm_gain_i(16'd8192)", '.synth_gain_i(sg),.pcm_gain_i(pg)')
 original=original.replace('  if($isunknown({ol,orr,clip}))', '  $fdisplay(fd,"%08h %08h %b",ol,orr,clip);\n  if($isunknown({ol,orr,clip}))')
 original=original.replace('synth=$signed(seed)>>>5;', "sg=seed[15:0]>>1;pg=seed[31:16]>>1;synth=$signed(seed)>>>5;")
 original=original.replace('mask=0;for(integer n=0;n<128;', 'mask=0;sg=8192;pg=8192;for(integer n=0;n<300;')
 original=original.replace(' orders[0]=', ' fd=$fopen("TRACEFILE","w");\n orders[0]=',1)
 common=['legacy/rtl/audio/audio_math_pkg.sv','rtl/memory/workstation_sdp.sv','rtl/memory/workstation_sdp_banked.sv','rtl/audio/serial_spatial_reverb.sv','legacy/rtl/audio/stereo_effects.sv','rtl/audio/delay_ddr/serial_delay_effect_ddr.sv','rtl/audio/delay_ddr/delay_ddr_dma.sv','rtl/music/music_async_fifo.sv']
 inputs=set();results=[]
 for label,root in [('before',BASE),('after',stage)]:
  tb=out/(label+'.sv');tb.write_text(original.replace('TRACEFILE',str(out/(label+'.hex'))));sources=[root/x for x in common]+[tb];sources+=[root/'rtl/audio/spatial_room_preset.svh'];inputs.update(sources)
  cmd=['verilator','--binary','--timing','--build-jobs','4','-Wno-fatal','-I'+str(root),'--top-module','tb_effect_chain','--Mdir',str(out/(label+'_obj'))]+[str(x) for x in sources if x.suffix=='.sv']
  for step,c in [('build',cmd),('run',[str(out/(label+'_obj/Vtb_effect_chain'))])]:
   with (out/(label+'_'+step+'.log')).open('w') as f:r=subprocess.run(c,cwd=root,stdout=f,stderr=subprocess.STDOUT)
   if r.returncode:raise RuntimeError((out/(label+'_'+step+'.log')).read_text()[-4000:])
  print(label,(out/(label+'_run.log')).read_text()[:300]);results.append((out/(label+'.hex')).read_bytes())
 assert results[0]==results[1], 'pre/post effect samples or clipping flags differ'
 summary=dict(passed=True,frames=len(results[0].splitlines()),trace_sha256=hashlib.sha256(results[0]).hexdigest(),source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(inputs)},hardware_tested=False)
 (out/'verification.json').write_text(json.dumps(summary,indent=2)+'\n');print('PASS changing gains, six orders/eight masks, full stereo words/clip flags match:',summary['frames'])
if __name__=='__main__':main()
