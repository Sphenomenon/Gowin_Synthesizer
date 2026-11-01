#!/usr/bin/env python3
"""Full stereo analysis: frozen default parity, real PCM XY and finite history."""
import argparse,hashlib,json,math,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def raster(points):
 result=set();previous=None
 for x,y,active in points:
  if not active:previous=None;continue
  if previous is None:result.add(y*256+x)
  else:
   x0,y0=previous;dx=abs(x-x0);sx=1 if x0<x else -1;dy=-abs(y-y0);sy=1 if y0<y else -1;error=dx+dy
   while True:
    result.add(y0*256+x0)
    if (x0,y0)==(x,y):break
    twice=2*error
    if twice>=dy:error+=dy;x0+=sx
    if twice<=dx:error+=dx;y0+=sy
  previous=(x,y)
 return result

def fixtures():
 frames=[]
 for frame in range(7):
  values=[]
  for i in range(2048):
   if frame==0:l=round(24576*math.sin(2*math.pi*7*i/2048));r=round(18000*math.sin(2*math.pi*5*i/2048+0.3))
   elif frame==1:l=round(24576*math.sin(2*math.pi*3*i/2048+0.6));r=round(18000*math.sin(2*math.pi*11*i/2048))
   elif frame==2:l,r=24576,15000
   elif frame in (3,4):l,r=0,0
   elif frame==5:l=round(1536*math.sin(2*math.pi*9*i/2048));r=round(1100*math.sin(2*math.pi*2*i/2048))
   else:l=round(1536*math.sin(2*math.pi*2*i/2048+0.4));r=round(1100*math.sin(2*math.pi*13*i/2048+0.7))
   values.append((l,r))
  frames.append(values)
 return frames

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--root',type=Path,default=ROOT);ap.add_argument('--negative',choices=('missing_history','wrong_pcm_mapping'));args=ap.parse_args();root=args.root.resolve();sys.path.insert(0,str(root));from tools.workstation_baselines import load_baseline
 out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);owner=root/'rtl/display_data/output_audio_analysis.v';trace=root/'rtl/display_data/workstation_xy_trace.sv';tb=Path(__file__).with_name('tb_workstation_xy_analysis.sv');inputs={str(p):sha(p)for p in (owner,trace,tb,Path(__file__).resolve())}
 # The immutable M26 source is the reference; only module names are changed.
 repo=root.parents[3];relative='projects/138k/push2_workstation/usb_a/rtl/display_data/output_audio_analysis.v';reference=subprocess.check_output(['git','show','168d2a0b:'+relative],cwd=repo)
 assert hashlib.sha256(reference).hexdigest()=='5c4929314c548d0ab97d6274e6ceb3ef59a76be739c5fb0a1d48564aa011dbdc'
 frozen=out/'reference.v';frozen.write_text(reference.decode().replace('output_audio_analysis','reference_output_audio_analysis').replace('gw138k_spectrum_column_rom','reference_spectrum_column_rom'))
 sources=[]
 for p in (owner,trace,tb):
  dest=out/p.name;dest.write_bytes(p.read_bytes());sources.append(dest)
 if args.negative:
  path=sources[1]if args.negative=='missing_history'else sources[0];s=path.read_text();old,new=(('keep_history<=history_valid && history_gain==gain_i;',"keep_history<=1'b0;")if args.negative=='missing_history'else('.point_x_i(image_x),.point_y_i(image_y)', '.point_x_i(image_y),.point_y_i(image_y)'));assert s.count(old)==1;path.write_text(s.replace(old,new))
 baseline=load_baseline(root,'resource_rework_route0')
 for name in ('output_audio_capture.v','audio_analysis_rom.v'):
  dest=out/name;dest.write_bytes(baseline.read_bytes('src/video/'+name));sources.append(dest)
 sources.append(frozen);frames=fixtures();samples=[];expected_off=[];expected_on=[];peaks=[];gains=[];history=set();old_gain=None;coverage=[]
 for index,values in enumerate(frames):
  left=max(abs(l)for l,r in values);right=max(abs(r)for l,r in values);peak=max(left,right);gain=0
  for bit in range(7):
   if peak and peak<(16384>>bit):gain=bit+1
  pts=[(max(0,min(255,128+(l>>(9-gain)))),max(0,min(255,128-(r>>(9-gain)))),l!=0 or r!=0)for l,r in values];point_bitmap={y*256+x for x,y,valid in pts if valid};raw=raster(pts);image=raw|history if old_gain==gain and index!=6 else raw
  samples.extend(((l&65535)<<16)|(r&65535)for l,r in values);expected_off.extend(int(i in point_bitmap)for i in range(65536));expected_on.extend(int(i in image)for i in range(65536));peaks.append((left<<16)|right);gains.append(gain);coverage.append(dict(frame=index,gain=gain,raw_pixels=len(raw),point_pixels=len(point_bitmap),published_pixels=len(image),reset=index==6));history=raw;old_gain=gain
 for name,values,width in [('samples',samples,8),('off',expected_off,1),('on',expected_on,1),('peaks',peaks,8),('gains',gains,1)]:
  (out/(name+'.mem')).write_text(''.join(format(v,'0'+str(width)+'x')+'\n'for v in values))
 execution={str(p):sha(p)for p in [*sources,*out.glob('*.mem')]};report=dict(schema=1,passed=False,input_sha256=inputs,execution_sha256=execution,reference_git='168d2a0b:'+relative,reference_sha256=hashlib.sha256(reference).hexdigest(),negative_control=args.negative,coverage=coverage,baseline=baseline.evidence(),hardware_tested=False,full_analysis_tested=True,scope='Three actual full2048 stereo analysis instances; default-off public cycle parity, on/off stereo FFT and metadata, real PCM-independent XY oracle, immutable front, reset/gain retirement and counted overrun')
 try:
  argv=['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module','tb_workstation_xy_analysis','--Mdir',str(out/'obj'),*map(str,sources)];report['compile_argv']=argv
  with(out/'compile.log').open('w')as f:subprocess.run(argv,cwd=out,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=180)
  warnings=re.findall(r'^%Warning-([^:]+): (.*)',(out/'compile.log').read_text(),re.M);report['warnings']=warnings
  report['fixture_warnings']=[(k,m)for k,m in warnings if '/tb_workstation_xy_analysis.sv:' in m and k!='TIMESCALEMOD']
  report['trace_leaf_warnings']=[(k,m)for k,m in warnings if '/workstation_xy_trace.sv:' in m and k!='TIMESCALEMOD']
  assert not report['fixture_warnings'] and not report['trace_leaf_warnings'],'new fixture/leaf warning'
  assert not any(k=='UNOPTFLAT'for k,m in warnings),'combinational loop warning'
  with(out/'run.log').open('w')as f:p=subprocess.run([str(out/'obj/Vtb_workstation_xy_analysis')],cwd=out,stdout=f,stderr=subprocess.STDOUT,timeout=180)
  log=(out/'run.log').read_text();print(log,end='')
  if args.negative:assert p.returncode!=0 and 'XY analysis bitmap mismatch'in log;report['negative_control_rejected']=True
  else:
   assert p.returncode==0,log[-2000:];match=re.search(r'PASS xy_analysis frames=(\d+) off_cycles=(\d+) pixels=(\d+) stereo_fft_columns=(\d+) stalls=(\d+) skip=(\d+)',log);assert match;report['metrics']=dict(zip(('frames','off_cycle_checks','pixel_checks','stereo_fft_columns','stalled_read_checks','skipped_samples'),map(int,match.groups())))
  assert all(sha(Path(p))==h for p,h in inputs.items());assert all(sha(Path(p))==h for p,h in execution.items());report['passed']=True
 finally:
  report['logs']={p.name:sha(p)for p in(out/'compile.log',out/'run.log')if p.exists()};(out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
