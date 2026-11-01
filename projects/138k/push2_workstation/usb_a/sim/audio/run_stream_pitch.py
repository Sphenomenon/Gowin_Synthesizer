from pathlib import Path
import subprocess,json,math,random,hashlib,argparse,sys,shutil
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser(description="Execute the actual continuous stereo pitch module against an independent fixed-point history model and dual-rate spectra.")
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--vendor',type=Path,help="Exact Gowin prim_sim.v for physical SDPB latency and bit mapping")
parser.add_argument('--source',type=Path,default=ROOT/'rtl/audio/workstation_stream_pitch.sv',help="Verification source override for explicit negative controls only")
parser.add_argument('--negative-controls',action='store_true')
args=parser.parse_args();OUT=args.output.resolve();OUT.mkdir(parents=True,exist_ok=False)
module_source=args.source.resolve()
bench_source=Path(__file__).with_name('tb_workstation_stream_pitch.sv')
shutil.copy2(bench_source,OUT/'tb.sv')
rows=[];expected=[];groups=[]
phase=ptr=filled=wet=0;hist=[(0,0)]*2048
rng=random.Random(0x138025)
def reset():
 global phase,ptr,filled,wet
 phase=ptr=filled=wet=0;rows.append((0,0,0,0,0,0,0,0));expected.append(('C',))
def sample(left,right,ratio=1048576,enable=1,clear=0,gap=0,overrun=0):
 global phase,ptr,filled,wet
 ratio=max(524288,min(2097152,ratio));p=phase
 def head(pos):
  loc=((ptr<<16)-(16<<16)-pos)%(2048<<16);a=loc>>16;f=loc&65535;age=(ptr-a)%2048
  v=hist[a] if age<=filled else (0,0)
  v1=hist[(a+1)%2048] if age-1<=filled else (0,0)
  return tuple(x+((y-x)*f//65536) for x,y in zip(v,v1))
 a=head(p);b=head((p+(512<<16))%(1024<<16));weight=min(p,(1024<<16)-p)//512
 out=tuple(y+(x-y)*weight//65536 for x,y in zip(a,b))
 wet=min(64,wet+1) if enable and ratio!=1048576 else max(0,wet-1)
 out=tuple(d+(x-d)*(wet*1024)//65536 for x,d in zip(out,(left,right)))
 rows.append((1,ratio,enable,left,right,clear,gap,overrun))
 hist[ptr]=(left,right);ptr=(ptr+1)%2048;filled=min(2048,filled+1);phase=(phase+65536-(ratio>>4))%(1024<<16)
 if clear:expected.append(('X',));phase=ptr=filled=wet=0
 else:expected.append(('R',*out,40,overrun))
reset()
for n in range(4096):sample(rng.randint(-2147483648,2147483647),rng.randint(-2147483648,2147483647),1048576,n%2,gap=rng.randrange(3))
for ratio in (524288,934175,1048576,1176999,2097152):
 for n in range(2048):sample(rng.randint(-2147483648,2147483647),rng.randint(-2147483648,2147483647),ratio,1,gap=n%3)
for age in range(1,40):
 for n in range(40):sample(0x7fffffff,-0x80000000,1176999,1)
 sample(0x7fffffff,-0x80000000,1176999,1,clear=age)
 for n in range(40):sample(0,0,1176999,1)
reset();sample(123456789,-234567890,1176999,1,overrun=1);reset()
for n in range(6000):
 if n%701==0:reset()
 sample(rng.randint(-2147483648,2147483647),rng.randint(-2147483648,2147483647),rng.randrange(524288,2097153),n%7!=0,gap=rng.randrange(3))
for fs in (48000,44100):
 for ratio in (round(2**(-2/12)*1048576),round(2**(2/12)*1048576)):
  reset();start=len(rows)
  for n in range(16000):sample(round(math.sin(2*math.pi*997*n/fs)*1200000000),round(math.sin(2*math.pi*1499*n/fs)*700000000),ratio,1)
  groups.append({'rate':fs,'ratio_q20':ratio,'start':start,'count':16000,'frequencies':[997,1499]})
with (OUT/'input.txt').open('w') as f:
 for row in rows:f.write(' '.join(str(int(x)) for x in row)+'\n')
compile_args=['iverilog','-g2012','-s','tb','-o',str(OUT/'sim'),str(OUT/'tb.sv'),str(module_source),str(ROOT/'rtl/memory/workstation_sdp_banked.sv'),str(ROOT/'rtl/memory/workstation_sdp.sv')]

if args.vendor:compile_args[1:1]=['-DWORKSTATION_SDP_VENDOR_SIM'];compile_args.append(str(args.vendor.resolve()))
r=subprocess.run(compile_args,capture_output=True,text=True);(OUT/'compile.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stderr
r=subprocess.run(['vvp',str(OUT/'sim')],cwd=OUT,capture_output=True,text=True);(OUT/'run.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr
observed=[];index=0;latencies=set()
for line,exp in zip((OUT/'output.txt').read_text().splitlines(),expected,strict=True):
 values=line.split();assert values[0]==exp[0],(index,values,exp)
 if values[0]=='R':
  got=tuple(map(int,values[2:]));assert got==exp[1:],(index,got,exp);observed.append(tuple(map(int,values[2:4])));latencies.add(int(values[4]))
 else:observed.append(None)
 index+=1
for g in groups:
 y=np.array(observed[g['start']+4096:g['start']+g['count']],dtype=np.float64)
 results=[]
 for ch,freq in enumerate(g['frequencies']):
  values=y[:,ch];fft=np.abs(np.fft.rfft(values*np.hanning(len(values)),n=131072));frequencies=np.fft.rfftfreq(131072,1/g['rate']);peak=float(frequencies[int(np.argmax(fft))]);target=freq*g['ratio_q20']/1048576
  assert abs(peak-target)<4.5,(g,ch,peak,target)
  results.append({'channel':ch,'input_hz':freq,'target_hz':target,'measured_peak_hz':peak})
 g['results']=results
source_inputs=[module_source,bench_source,Path(__file__).resolve(),ROOT/'rtl/memory/workstation_sdp_banked.sv',ROOT/'rtl/memory/workstation_sdp.sv']
if args.vendor:source_inputs.append(args.vendor.resolve())
evidence={'passed':True,'scope':'actual maintained continuous stereo pitch module; complete W integration and hardware remain separate','vendor_SD PB':bool(args.vendor),'requests':sum(r[0]==1 for r in rows),'cancelled_pipeline_edges':39,'exact_fixed_point_reference':True,'settled_dry_bit_exact':True,'wet_ramp_frames':64,'busy_overrun_fault_and_clear':True,'maximum_response_cycles':max(latencies)+1,'spectral_cases':groups,'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_inputs},'hardware_tested':False,'integrated':False}
if args.negative_controls:
 source=module_source.read_text();negative=[]
 edits={
  'reverse_phase_direction':("phase<=phase+26'd65536-{8'd0,ratio[21:4]};","phase<=phase-26'd65536+{8'd0,ratio[21:4]};"),
  'unsigned_negative_product':("sum=$signed({{18{addend[32]}},addend})+(product>>>16);","sum={{18{addend[32]}},addend}+(product>>>16);"),
  'stale_history_after_cancel':("state<=IDLE;write_pointer<=0;filled<=0;phase<=0;\n                left_o", "state<=IDLE;write_pointer<=0;phase<=0;\n                left_o"),
  'lost_second_head':("second_phase=phase ^ 26'h2000000;","second_phase=phase;"),
 }
 for name,(before,after) in edits.items():
  assert source.count(before)==1,name
  mutant=OUT/(name+'.sv');mutant.write_text(source.replace(before,after))
  command=[sys.executable,str(Path(__file__).resolve()),'--source',str(mutant),'--output',str(OUT/name)]
  result=subprocess.run(command,capture_output=True,text=True)
  (OUT/(name+'.log')).write_text(result.stdout+result.stderr)
  assert result.returncode!=0 and 'AssertionError: (' in result.stderr,(name,result.stdout,result.stderr)
  assert 'PASS stream pitch' in (OUT/name/'run.log').read_text(),name
  negative.append({'name':name,'actual_execution_rejected':True,'source_sha256':hashlib.sha256(mutant.read_bytes()).hexdigest()})
 evidence['negative_controls']=negative
(OUT/'verification.json').write_text(json.dumps(evidence,indent=2)+'\n')
print(json.dumps({'passed':True,'requests':evidence['requests'],'cancelled_pipeline_edges':39,'maximum_response_cycles':evidence['maximum_response_cycles'],'spectral_cases':len(groups),'negative_controls':len(evidence.get('negative_controls',[])),'vendor':bool(args.vendor)}))
