#!/usr/bin/env python3
"""Measure both actual RTL impulse responses; no claim of subjective preference."""
from pathlib import Path
import subprocess,json,hashlib,math,wave,struct
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'out/resource_reverb_comparison';REPORT=ROOT/'reports/resource_rework_20261020'
BASE=ROOT/'results/timing_p27_uart_cdc_route1_20261018_142516_456857/Prj1'
def main():
 OUT.mkdir(exist_ok=True,parents=True);REPORT.mkdir(exist_ok=True,parents=True)
 text=(BASE/'legacy/rtl/audio/stereo_effects.sv').read_text();old=text[text.index('module serial_reverb_effect #'):text.index('module stereo_effects #')];(OUT/'old.sv').write_text(old)
 tb=f'''`timescale 1ns/1ps
module tb_compare_room;
reg clk=0,rst=0,valid=0;reg signed[31:0] signal=0;always #5 clk=~clk;
wire ready0,ready1,v0,v1;wire signed[31:0] l0,r0,l1,r1;reg signed[31:0] a,b,c,d;integer f;
serial_reverb_effect old(.clk_i(clk),.rst_ni(rst),.clear_i(1'b0),.valid_i(valid),.enabled_i(1'b1),.left_i(signal),.right_i(signal),.ready_o(ready0),.valid_o(v0),.left_o(l0),.right_o(r0));
serial_spatial_reverb room(.clk_i(clk),.rst_ni(rst),.clear_i(1'b0),.valid_i(valid),.enabled_i(1'b1),.left_i(signal),.right_i(signal),.ready_o(ready1),.valid_o(v1),.left_o(l1),.right_o(r1));
always @(posedge clk)begin if(v0)begin a<=l0;b<=r0;end if(v1)begin c<=l1;d<=r1;end end
initial begin
 f=$fopen("{OUT/'response.txt'}","w");repeat(3)@(negedge clk);rst=1;
 for(integer n=0;n<96065;n=n+1)begin
  @(negedge clk);if(!ready0 || !ready1)$fatal(1,"IR ready");signal=n==64?32'sh40000000:0;valid=1;
  @(negedge clk);valid=0;repeat(127)@(negedge clk);
  if(n>=64)$fwrite(f,"%h %h %h %h\\n",a,b,c,d);
 end
 $fclose(f);$display("PASS actual RTL reverb comparison: stereo impulse, 96001 samples each");$finish;
end
endmodule
'''
 (OUT/'tb.sv').write_text(tb)
 sources=[BASE/'legacy/rtl/audio/audio_math_pkg.sv',ROOT/'rtl/memory/workstation_sdp.sv',ROOT/'rtl/memory/workstation_sdp_banked.sv',ROOT/'rtl/audio/serial_spatial_reverb.sv',OUT/'old.sv',OUT/'tb.sv']
 cmd=['verilator','--binary','--timing','--build-jobs','3','-Wno-fatal','-I'+str(ROOT),'--top-module','tb_compare_room','--Mdir',str(OUT/'obj_dir')]+list(map(str,sources))
 for label,command in [('build',cmd),('simulation',[str(OUT/'obj_dir/Vtb_compare_room')])]:
  with (OUT/(label+'.log')).open('w') as log:p=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
  if p.returncode:raise RuntimeError((OUT/(label+'.log')).read_text()[-5000:])
 data=np.array([[int(s,16) for s in l.split()] for l in (OUT/'response.txt').read_text().splitlines()],dtype=np.uint32).view(np.int32).astype(np.float64)/(1<<31)
 t=np.arange(len(data))/48000
 metrics={};fig,axes=plt.subplots(3,1,figsize=(10,9),layout='constrained')
 for name,x,color in [('Old dual comb',data[:,:2],'#a35d13'),('Spatial room + FDN',data[:,2:],'#1766a0')]:
  wet=x.copy();wet[0]=0;peak=np.abs(wet).max();energy=(wet**2).sum(axis=1);edc=np.cumsum(energy[::-1])[::-1];db=10*np.log10(np.maximum(edc,1e-40)/edc[0]);sel=(db<=-5)&(db>=-25)
  rt60=-60/np.polyfit(t[sel],db[sel],1)[0]
  first=np.flatnonzero(np.abs(wet).max(axis=1)>peak*1e-6)[0]/48
  # Count milliseconds containing any echo > -60dB relative to that IR's wet peak.
  occupied=(np.abs(wet[:96000]).reshape(-1,48,2).max(axis=(1,2))>peak*.001)
  density=float(occupied[50:500].mean())
  metrics[name]=dict(first_wet_ms=float(first),rt60_seconds=float(rt60),occupied_1ms_bins_50_to_500ms=density)
  axes[0].plot(t[:4800]*1000,wet[:4800,0],label=name,color=color,alpha=.8,lw=.8)
  rms=np.sqrt(np.mean(wet[:96000].reshape(-1,48,2)**2,axis=(1,2)))
  axes[1].plot(np.arange(len(rms)),20*np.log10(np.maximum(rms,1e-12)),label=name,color=color,lw=.8)
  axes[2].plot(t,db,label=name,color=color,lw=1.2)
  filename='old_comb_impulse.wav' if name.startswith('Old') else 'spatial_room_impulse.wav'
  pcm=np.clip(np.rint(x*32768),-32768,32767).astype('<i2')
  with wave.open(str(REPORT/filename),'wb') as wav:wav.setnchannels(2);wav.setsampwidth(2);wav.setframerate(48000);wav.writeframes(pcm.tobytes())
 axes[0].set(xlabel='Time (ms)',ylabel='Left wet signal',title='Actual RTL impulse responses, same 0.5 FS stereo impulse and settled 25% wet mix')
 axes[1].set(xlabel='Time (ms)',ylabel='Stereo 1 ms RMS (dBFS)',ylim=(-120,-20),xlim=(0,1000))
 axes[2].set(xlabel='Time (s)',ylabel='Integrated wet energy (dB)',ylim=(-80,1),xlim=(0,1.5))
 for ax in axes:ax.grid(alpha=.2);ax.legend(loc='upper right')
 fig.savefig(REPORT/'reverb_comparison.png',dpi=160);plt.close(fig)
 metrics['source_sha256']={str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in sources+[ROOT/'rtl/audio/spatial_room_preset.svh']};metrics['passed']=True;metrics['hardware_tested']=False;metrics['scope']='Objective IR characteristics of both RTL algorithms; no subjective listening evaluation'
 (REPORT/'reverb_comparison.json').write_text(json.dumps(metrics,indent=2)+'\n');print(json.dumps(metrics,indent=2))
if __name__=='__main__':main()
