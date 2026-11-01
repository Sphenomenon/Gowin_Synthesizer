#!/usr/bin/env python3
"""Real PANIC marker through the established 204-bit tuple and drop CDC."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.workstation_baselines import load_baseline
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
 owner=ROOT/'rtl/workstation/workstation_hdmi_display.sv';s=owner.read_text();start=s.index('module workstation_xy_panic_observation(');end=s.index('endmodule',start)+len('endmodule');leaf=s[start:end]+'\n'
 p=out/'marker.sv';p.write_text(leaf);tb=Path(__file__).with_name('tb_workstation_xy_panic.sv');frozen=out/tb.name;frozen.write_bytes(tb.read_bytes());counter=ROOT/'rtl/migration/workstation_runtime_counter_cdc.sv';cp=out/counter.name;cp.write_bytes(counter.read_bytes());baseline=load_baseline(ROOT,'resource_rework_route0');stream=out/'gw138k_stream_cdc.sv';stream.write_bytes(baseline.read_bytes('src/migration/gw138k_stream_cdc.sv'))
 inputs={str(x):sha(x)for x in (owner,tb,counter,Path(__file__))};records=[]
 for name in ('actual','no_epoch_marker','wrong_epoch_bit','uncounted_loss'):
  source=p;mail=stream
  if name!='actual':
   old,new={'no_epoch_marker':('trusted_i && !panic_changed','trusted_i'),'wrong_epoch_bit':('panic_epoch_i!=panic_epoch_q','panic_epoch_i[8:0]!=panic_epoch_q[8:0]'),'uncounted_loss':('else drop_count<=drop_count+1\'b1;','else drop_count<=drop_count;')}[name]
   source=out/(name+'.sv') if name!='uncounted_loss' else p;mail=out/(name+'.sv') if name=='uncounted_loss' else stream;base=stream.read_text()if name=='uncounted_loss' else leaf;assert base.count(old)==1;(mail if name=='uncounted_loss' else source).write_text(base.replace(old,new))
  argv=['iverilog','-g2012','-s','tb_workstation_xy_panic','-o',str(out/(name+'.vvp')),str(source),str(frozen),str(cp),str(mail)];p1=subprocess.run(argv,capture_output=True,text=True,timeout=60);(out/(name+'-compile.log')).write_text(p1.stdout+p1.stderr);assert p1.returncode==0,p1.stderr
  p1=subprocess.run(['vvp',str(out/(name+'.vvp'))],capture_output=True,text=True,timeout=60);log=p1.stdout+p1.stderr;(out/(name+'-run.log')).write_text(log);passed=p1.returncode==0 and 'PASS XY panic' in log;assert passed==(name=='actual'),(name,log);records.append(dict(name=name,expected_outcome_verified=True,exit_code=p1.returncode,log=log));print(name,log.strip(),flush=True)
 assert all(sha(Path(p))==h for p,h in inputs.items());d=dict(schema=1,passed=True,input_sha256=inputs,cases=records,baseline=baseline.evidence(),hardware_tested=False);(out/'verification.json').write_text(json.dumps(d,indent=2)+'\n')
if __name__=='__main__':main()
