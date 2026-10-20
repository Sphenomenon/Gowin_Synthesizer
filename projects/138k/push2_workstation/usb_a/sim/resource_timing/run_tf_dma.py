#!/usr/bin/env python3
"""Bind staged TF DMA to independent byte/ring oracle and actual buffered bus."""
from pathlib import Path
import sys,argparse,json,subprocess,hashlib
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
from test_cnn_tf_write_buffer_retime import buffered_native_tb,inflight_restart_tb,stalled_tb,zero_response_tb

def main():
 p=argparse.ArgumentParser();p.add_argument('build',type=Path);a=p.parse_args();build=a.build.resolve();stage=build/'Prj1';out=build/'tf_dma_timing';out.mkdir(exist_ok=True)
 src=stage/'src/storage/tf_audio_ddr_dma.v';bus=[stage/'rtl/timing/basic_pitch_ddr_arbiter_pipeline.sv',stage/'rtl/timing/basic_pitch_ddr_client_queues.sv',stage/'src/memory/tf_audio_ddr_command_buffer.sv']
 results=[];inputs=set([src,*bus,Path(__file__).resolve(),ROOT/'sim/tf_audio/tb_tf_audio_ddr_dma.sv'])
 for buffered,stalled,zero in [(True,False,False),(True,True,False),(False,False,False),(False,True,False),(False,False,True),(False,True,True)]:
  label=f'buffer{int(buffered)}_stall{int(stalled)}_zero{int(zero)}';tb='`timescale 1ns/1ps\n'+(ROOT/'sim/tf_audio/tb_tf_audio_ddr_dma.sv').read_text()
  if buffered:tb=inflight_restart_tb(buffered_native_tb(tb,stalled,True))
  elif zero:tb=zero_response_tb(tb,stalled)
  elif stalled:tb=stalled_tb(tb)
  path=out/(label+'.sv');path.write_text(tb);inputs.add(path);sources=[src,path]+(bus if buffered else []);log=''
  for cmd in [['iverilog','-g2012','-I',str(stage),'-s','tb_tf_audio_ddr_dma','-o',str(out/label)]+list(map(str,sources)),['vvp',str(out/label)]]:
   r=subprocess.run(cmd,cwd=stage,text=True,capture_output=True,timeout=60);log+=r.stdout+r.stderr
   if r.returncode:break
  passed=r.returncode==0 and 'PASS' in log;(out/(label+'.log')).write_text(log)
  print(label,log[-600:]);results.append(dict(label=label,passed=passed,buffered_native=buffered,stalled=stalled,zero_latency_return=zero))
  if not passed:break
 d=dict(passed=len(results)==6 and all(x['passed'] for x in results),cases=results,source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(inputs)},hardware_tested=False)
 (out/'verification.json').write_text(json.dumps(d,indent=2)+'\n')
 if not d['passed']:raise SystemExit(1)
if __name__=='__main__':main()
