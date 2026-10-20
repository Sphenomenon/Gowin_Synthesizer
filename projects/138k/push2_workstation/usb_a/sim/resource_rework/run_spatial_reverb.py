#!/usr/bin/env python3
"""Bit-exact fixed point model, impulse, bypass, clear and saturation checks."""
from pathlib import Path
import json, subprocess, time, wave, struct, math, hashlib
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'out/resource_spatial_reverb'
BASE=ROOT/'results/timing_p27_uart_cdc_route1_20261018_142516_456857/Prj1'
def sat(x):return max(-2147483648,min(2147483647,x))
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    room=json.loads((ROOT/'rtl/audio/spatial_room_preset.json').read_text())
    lengths=room['fdn_delays'];taps=room['taps']
    # Wet gain settles, then an impulse plus two seconds of decay. Follow with
    # full-scale adversarial input, disabled tail, clear and dry bit-exact input.
    inputs=[(1,1,0,0)]+[(0,1,0,0)]*63+[(0,1,1<<30,1<<30)]+[(0,1,0,0)]*96000
    seed=1
    for n in range(8192):
        seed=(1664525*seed+1013904223)&0xffffffff
        l=2147483647 if seed&1 else -2147483648
        r=l if n&1 else -l-1
        inputs.append((0,1,l,r))
    inputs += [(0,0,0,0)]*128
    inputs += [(1,0,0,0)]+[(0,0,((n*1234567)&0x7fffffff),-((n*7654321)&0x7fffffff)) for n in range(2048)]
    expected=[];early=[0]*2048;lines=[[0]*n for n in lengths];damping=[0]*4;ptr=[0]*4;ep=frames=gain=0
    for clear,enabled,l,r in inputs:
        if clear:ptr=[0]*4;ep=frames=gain=0;damping=[0]*4
        gain=min(gain+128,8192) if enabled else max(0,gain-128)
        mono=(l+r)>>1;tail=[lines[k][ptr[k]] if frames>=lengths[k] else 0 for k in range(4)]
        damping=[sat((damping[k]+tail[k])>>1) for k in range(4)]
        a,b,c,d=damping;h=[(a+b+c+d)>>1,(a-b+c-d)>>1,(a+b-c-d)>>1,(a-b-c+d)>>1]
        feedback=[(mono>>3)+v-(v>>3) for v in h]
        el=er=0
        for k,tap in enumerate(taps):
            value=early[(ep-tap['delay'])%2048] if frames>=tap['delay'] else 0
            value=(value*tap['gain_q15'])>>15
            if k%2:er+=value
            else:el+=value
        a,b,c,d=tail;wl=sat(el+((a+b-c-d)>>2));wr=sat(er+((a-b+c-d)>>2))
        ml=l+((wl*gain)>>15);mr=r+((wr*gain)>>15)
        clipped=any(v!=sat(v) for v in feedback+[ml,mr])
        expected.append((sat(ml),sat(mr),int(clipped),int(enabled or gain!=0)))
        for k in range(4):lines[k][ptr[k]]=sat(feedback[k]);ptr[k]=(ptr[k]+1)%lengths[k]
        early[ep]=mono;ep=(ep+1)%2048;frames+=1
    (OUT/'input.mem').write_text(''.join(f'{(cl<<65)|(en<<64)|((l&0xffffffff)<<32)|(r&0xffffffff):017x}\n' for cl,en,l,r in inputs))
    (OUT/'expected.mem').write_text(''.join(f'{(ac<<65)|(clip<<64)|((l&0xffffffff)<<32)|(r&0xffffffff):017x}\n' for l,r,clip,ac in expected))
    tb=f'''`timescale 1ns/1ps
module tb_spatial;
reg clk=0,rst=0,clear=0,valid=0,en=0;reg signed[31:0] l=0,r=0;
wire ready,active,ov,clip;wire signed[31:0] ol,orr;
reg [65:0] stimulus[0:{len(inputs)-1}],expected[0:{len(inputs)-1}];
integer latency,maxlat=0,clips=0;
always #5 clk=~clk;
serial_spatial_reverb dut(clk,rst,clear,valid,en,l,r,ready,active,ov,ol,orr,clip);
initial begin
$readmemh("{OUT/'input.mem'}",stimulus);$readmemh("{OUT/'expected.mem'}",expected);
repeat(3)@(negedge clk);rst=1;
for(integer n=0;n<{len(inputs)};n=n+1)begin
  @(negedge clk);if(!ready)$fatal(1,"not ready at frame %0d",n);
  {{clear,en,l,r}}=stimulus[n];if(clear)begin @(negedge clk);clear=0;end
  valid=1;@(negedge clk);valid=0;latency=1;
  while(!ov)begin @(negedge clk);latency=latency+1;if(latency>96)$fatal(1,"late output");end
  if({{active,clip,ol,orr}}!==expected[n])$fatal(1,"frame=%0d got=%h expected=%h",n,{{active,clip,ol,orr}},expected[n]);
  if(latency>maxlat)maxlat=latency;if(clip)clips=clips+1;
end
// Aborting a sample must produce no late output and leave the unit ready.
@(negedge clk);valid=1;@(negedge clk);valid=0;repeat(7)@(negedge clk);clear=1;
@(negedge clk);clear=0;repeat(96)begin @(negedge clk);if(ov || !ready)$fatal(1,"clear did not abort");end
$display("PASS spatial: %0d bit-exact stereo frames, max_latency=%0d, clips=%0d",{len(inputs)},maxlat,clips);$finish;
end
endmodule
'''
    (OUT/'tb.sv').write_text(tb)
    sources=[BASE/'legacy/rtl/audio/audio_math_pkg.sv',ROOT/'rtl/memory/workstation_sdp.sv',ROOT/'rtl/memory/workstation_sdp_banked.sv',ROOT/'rtl/audio/serial_spatial_reverb.sv',OUT/'tb.sv']
    cmd=['verilator','--binary','--timing','--build-jobs','3','-Wno-fatal','--top-module','tb_spatial','--Mdir',str(OUT/'obj_dir'),'-I'+str(ROOT)]+list(map(str,sources))
    start=time.monotonic()
    with (OUT/'build.log').open('w') as log:p=subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    if p.returncode:raise RuntimeError((OUT/'build.log').read_text()[-5000:])
    with (OUT/'simulation.log').open('w') as log:p=subprocess.run([str(OUT/'obj_dir/Vtb_spatial')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    log=(OUT/'simulation.log').read_text();print(log,flush=True)
    if p.returncode or 'PASS spatial:' not in log:raise SystemExit(1)
    impulse=expected[64:96065]
    with wave.open(str(OUT/'room_impulse_stereo.wav'),'wb') as wav:
        wav.setnchannels(2);wav.setsampwidth(2);wav.setframerate(48000)
        wav.writeframes(b''.join(struct.pack('<hh',l>>16,r>>16) for l,r,_,_ in impulse))
    # Schroeder reverse-integrated energy: fit -5..-25 dB for extrapolated RT60.
    energy=[(l/(1<<31))**2+(r/(1<<31))**2 for l,r,_,_ in impulse[1:]]
    total=sum(energy);remaining=total;points=[]
    for n,e in enumerate(energy):
        db=10*math.log10(max(remaining,1e-40)/total)
        if -25<=db<=-5:points.append((n/48000,db))
        remaining=max(0,remaining-e)
    rt60=None
    if points:
        x=sum(t for t,d in points)/len(points);y=sum(d for t,d in points)/len(points)
        slope=sum((t-x)*(d-y) for t,d in points)/sum((t-x)**2 for t,d in points);rt60=-60/slope
    corr=sum(l*r for l,r,_,_ in impulse[1:])/math.sqrt(sum(l*l for l,_,_,_ in impulse[1:])*sum(r*r for _,r,_,_ in impulse[1:]))
    summary=dict(passed=True,frames=len(inputs),seconds=time.monotonic()-start,rt60_estimate_seconds=rt60,wet_interchannel_correlation=corr,
        final_100ms_peak_q31=max(max(abs(l),abs(r)) for l,r,_,_ in impulse[-4800:]),
        source_sha256={str(s):hashlib.sha256(s.read_bytes()).hexdigest() for s in sources+[ROOT/'rtl/audio/spatial_room_preset.svh']},hardware_tested=False)
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k!='source_sha256'},indent=2))
if __name__=='__main__':main()
