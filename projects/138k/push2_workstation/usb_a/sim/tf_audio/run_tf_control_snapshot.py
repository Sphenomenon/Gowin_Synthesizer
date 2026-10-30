#!/usr/bin/env python3
"""Audit-only exact source control block: hold/ACK/cancel/stopped-clock tests."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.workstation_tf_control_cdc import SOURCE_SHA256,require,sha
SOURCE='rtl/tf_audio/workstation_tf_runtime_service.sv'


def protocol_wrapper(payload):
 text=payload.decode();start=text.index('    reg [CTRL_BITS-1:0] held_control,compute_control;')
 end=text.index('    assign paused_o=',start)
 block=text[start:end]
 gate=text[text.index('    wire control_active='):];gate=gate[:gate.index(';')+1]
 require(text.count('    localparam CTRL_BITS=36;')==1,'declared36-bit protocol width')
 header='''`timescale 1ns/1ps
// AUDIT ONLY: exact maintained always blocks, with abstract boundary inputs.
// Never a production source or a replacement TF runtime service.
module tf_control_snapshot_exact(input wire clk_50m_i,compute_clk_i,rst_ni,
 input wire [35:0] desired_control,input wire [31:0] expected_generation_o,
 input wire expected_valid,output wire control_pending_o,active_o);
    localparam CTRL_BITS=36;
'''
 return header+block+gate+'\n    assign active_o=control_active;\nendmodule\n',block,gate


def run(output):
 output=Path(output);output.mkdir(parents=True,exist_ok=False)
 source=ROOT/SOURCE;payload=source.read_bytes();require(sha(source)==SOURCE_SHA256[SOURCE],'exact protocol source identity')
 wrapper,block,gate=protocol_wrapper(payload);path=output/'exact_protocol_audit_wrapper.sv';path.write_text(wrapper)
 tb=ROOT/'sim/tf_audio/tb_tf_control_snapshot.sv';inputs={str(p):sha(p) for p in (source,tb,Path(__file__),ROOT/'tools/workstation_tf_control_cdc.py')}
 runs=[]
 def execute(label,text,source_half,compute_half,phase,negative=None):
  work=output/label;work.mkdir();v=work/'audit.sv';v.write_text(text);binary=work/'simulation.vvp'
  cmd=['iverilog','-g2012','-Wall','-s','tb_tf_control_snapshot','-Ptb_tf_control_snapshot.SOURCE_HALF='+str(source_half),
       '-Ptb_tf_control_snapshot.COMPUTE_HALF='+str(compute_half),'-Ptb_tf_control_snapshot.COMPUTE_PHASE='+str(phase),'-o',str(binary),str(v),str(tb)]
  c=subprocess.run(cmd,capture_output=True,text=True,timeout=30);(work/'compile.log').write_text(c.stdout+c.stderr)
  require(c.returncode==0 and not c.stderr,'protocol compile/warnings '+label+c.stdout+c.stderr)
  r=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=30);(work/'run.log').write_text(r.stdout+r.stderr)
  if negative is None:require(r.returncode==0 and 'PASS exact TF control snapshot' in r.stdout,'protocol run '+label+r.stdout+r.stderr)
  else:require(r.returncode!=0 and negative in r.stdout+r.stderr,'protocol fault escaped '+label+r.stdout+r.stderr)
  runs.append(dict(name=label,clock_half_periods_ns=[source_half,compute_half],phase_ns=phase,passed=negative is None,rejected=negative is not None,
      returncode=r.returncode,compile_log_sha256=sha(work/'compile.log'),run_log_sha256=sha(work/'run.log'),wrapper_sha256=sha(v),log=r.stdout+r.stderr))
  print(r.stdout.strip(),flush=True)
 for index,ratio in enumerate(((3,5,1),(7,3,2),(11,13,3))):execute('nominal'+str(index),wrapper,*ratio)
 controls=[('overwrite_unACKed','ack_sync[1]==control_request && held_control!=desired_control','held_control!=desired_control','source overwrote unACKed'),
           ('skip_capture_delay','if(control_capture)begin compute_control<=held_control;','if(request_sync[1]!=control_ack)begin compute_control<=held_control;','capture/ACK delay'),
           ('remove_generation_fence','compute_control[35:4]==expected_generation_o && expected_valid','expected_valid','stale generation control became active')]
 for label,before,after,error in controls:
  require(wrapper.count(before)==1,'negative protocol anchor '+label);execute(label,wrapper.replace(before,after),3,5,1,error)
 require(inputs=={p:sha(p) for p in inputs},'protocol inputs changed')
 report=dict(schema=1,passed=True,input_sha256=inputs,source_protocol_block_sha256=hashlib.sha256(block.encode()).hexdigest(),
     source_consumer_gate_sha256=hashlib.sha256(gate.encode()).hexdigest(),runs=runs,
     scope='Exact production source blocks with abstract desired/expected-generation boundary inputs; audit wrapper is never used in production.',
     physical_delay_metastability_and_pulse_width_not_modelled=True,hardware_tested=False,physical_CDC_accepted=False,deployment_allowed=False)
 out=output/'verification.json';out.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps(dict(passed=True,report=str(out),sha256=sha(out))))


if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);run(p.parse_args().output)
