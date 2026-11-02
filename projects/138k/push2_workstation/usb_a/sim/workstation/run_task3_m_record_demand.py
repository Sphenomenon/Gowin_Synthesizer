#!/usr/bin/env python3
"""Actual M endpoint/exporter; deterministic received typed transactions."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SOURCES=('rtl/workstation/workstation_task3_m_bus_endpoint.sv',
 'rtl/music/workstation_task3_tf_analysis_source.sv','rtl/music/workstation_task3_score_commit_m.sv',
 'rtl/workstation/workstation_task3_final_tap_export.sv','rtl/workstation/workstation_task3_phone_command_ingress.sv',
 'sim/workstation/tb_task3_m_record_demand.sv')
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 inputs=(*SOURCES,'rtl/workstation/task3_paired_channels.vh',str(Path(__file__).resolve().relative_to(ROOT)))
 d=dict(schema=1,passed=False,input_sha256={s:hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in inputs},
  actual_M_endpoint=True,actual_final_tap_exporter=True,actual_DAC=False,actual_LCD=False,physical_CDC_verified=False,hardware_operated=False,deployment_allowed=False)
 try:
  cmd=['iverilog','-g2012','-I'+str(ROOT),'-s','tb_task3_m_record_demand','-o',str(out/'simulation.vvp'),*[str(ROOT/s) for s in SOURCES]]
  d['compile_argv']=cmd;r=subprocess.run(cmd,cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);(out/'compile.log').write_text(r.stdout)
  if r.returncode:raise RuntimeError(r.stdout)
  r=subprocess.run(['vvp',str(out/'simulation.vvp')],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);(out/'simulation.log').write_text(r.stdout);print(r.stdout,end='')
  m=re.search(r'PASS task3_m_record_demand checks=(\d+) scenarios=(\d+)',r.stdout)
  if r.returncode or not m:raise RuntimeError('M record demand fixture failed')
  d.update(passed=True,checks=int(m[1]),scenarios=int(m[2]))
 except Exception as e:d['error']=str(e);raise
 finally:(out/'verification.json').write_text(json.dumps(d,indent=2,sort_keys=True)+'\n')
if __name__=='__main__':main()
