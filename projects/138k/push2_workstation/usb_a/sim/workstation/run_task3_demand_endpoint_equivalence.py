#!/usr/bin/env python3
"""Cycle-compare every public M output with the exact sealed v19 endpoint."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools import workstation_task3_demand_identity_compare as demand

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 source=(ROOT/demand.ENDPOINT).read_text();reference=demand.restore_endpoint(source)
 reference=reference.replace('module workstation_task3_m_bus_endpoint #(','module demand_reference #(',1)
 (out/'reference.sv').write_text(reference)
 bench_path=ROOT/'sim/workstation/tb_task3_m_record_demand.sv';bench=bench_path.read_text()
 header=source.split(') (',1)[1].split('\n);',1)[0];ports=[];direction=width=''
 for item in header.split(','):
  item=item.strip();match=re.fullmatch(r'(input|output)\s+(?:wire|reg)\s*(\[[^]]+\])?\s*(\w+)',item)
  if match:direction,width,name=match[1],match[2] or '',match[3]
  else:
   if not re.fullmatch(r'\w+',item):raise ValueError('unreviewed endpoint port declaration: '+item)
   name=item
  ports.append((direction,width,name))
 assert len(ports)==len(set(n for _,_,n in ports))
 instance=re.search(r'workstation_task3_m_bus_endpoint\s*#\(\.RECORD_DEMAND_TIMEOUT_CYCLES\(30\)\)\s*dut\((.*?)\);',bench,re.S)
 assert instance is not None
 bindings=dict(re.findall(r'\.(\w+)\(([^()]*)\)',instance[1]));connections=[];declarations=[];comparisons=[]
 for direction,width,name in ports:
  if direction=='input':
   assert name in bindings,'missing explicit input '+name
   connections.append('.'+name+'('+bindings[name]+')')
  else:
   declarations.append('wire '+width+' shadow_'+name+';')
   connections.append('.'+name+'(shadow_'+name+')')
   comparisons.append('if(dut.'+name+' !== shadow_'+name+')$fatal(1,"endpoint difference: '+name+'");')
 comparison='\n'.join(declarations)+'''\ninteger equivalence_cycles=0;
defparam dut.DEMAND_IDENTITY_COMPARE_GROUP_BITS=8;
demand_reference #(.RECORD_DEMAND_TIMEOUT_CYCLES(30)) shadow(
'''+',\n'.join(connections)+''');
always @(posedge clk)begin #1;if(reset)begin
'''+ '\n'.join(comparisons)+'''
equivalence_cycles=equivalence_cycles+1;
end end
'''
 bench=bench[:instance.start()]+'reg tx_allow=1;reg [255:0] held_packet;\n'+bench[instance.start():instance.end()]+comparison+bench[instance.end():]
 bench=bench.replace(".tx_ready_i(1'b1)",'.tx_ready_i(tx_allow)').replace('if(reset && txvalid)','if(reset && txvalid && tx_allow)',1)
 # Exercise every identity bit at the public interface before any ARM can be
 # live. They must all be consumed as stale and must not fabricate a context.
 anchor='  demand(0);tick(4);if(armed || txcount)'
 assert bench.count(anchor)==1
 checks='''  for(integer bit_index=0;bit_index<96;bit_index=bit_index+1)begin
   send(`TASK3_PAIR_CH_RECORD_DEMAND,`TASK3_PAIR_RECORD_DEMAND_BYTES,{158'd0,2'd0,COMMON^(96'd1<<bit_index)});
   tick(1);if(armed || dut.record_demand_pending || txcount)$fatal(1,"partial demand identity accepted bit%0d",bit_index);
   checks=checks+1;
  end
  if(stale!=96)$fatal(1,"all identity mismatches not classified stale");
'''
 bench=bench.replace(anchor,checks+anchor,1).replace('if(stale!=1 || txcount!=7)','if(stale!=97 || txcount!=7)',1)
 extra='''
  link=1;tick(5);frame(80);tx_allow=0;demand(0);tick(8);
  if(!txvalid || txchannel!=`TASK3_PAIR_CH_RECORD)$fatal(1,"held ARM missing");
  held_packet=txpayload;repeat(4)begin tick(1);if(!txvalid || txpayload!==held_packet)$fatal(1,"backpressure changed held TX");end
  panic=1;tick(1);if(txvalid || armed)$fatal(1,"PANIC did not revoke held TX and exporter");
  panic=0;tx_allow=1;tick(6);if(txvalid || armed)$fatal(1,"PANIC replayed old ARM");checks=checks+3;
'''
 bench=bench.replace('  $display("PASS task3_m_record_demand',extra+'  $display("PASS task3_m_record_demand',1)
 bench=bench.replace('  $display("PASS task3_m_record_demand', '  if(equivalence_cycles<100)$fatal(1,"equivalence fixture inactive");\n  $display("PASS demand_endpoint_equivalence cycles=%0d outputs='+str(len(comparisons))+'",equivalence_cycles);\n  $display("PASS task3_m_record_demand',1)
 (out/'bench.sv').write_text(bench)
 sources=[demand.ENDPOINT,'rtl/workstation/workstation_task3_pcm_block_tx.sv','rtl/music/workstation_task3_tf_analysis_source.sv','rtl/music/workstation_task3_score_commit_m.sv',
  'rtl/workstation/workstation_task3_final_tap_export.sv','rtl/workstation/workstation_task3_phone_command_ingress.sv']
 inputs=[ROOT/s for s in sources]+[bench_path,Path(__file__),ROOT/demand.TOOL]
 sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();before={str(p):sha(p) for p in inputs}
 result=dict(schema=1,passed=False,input_sha256=before,compared_public_outputs=[n for d,_,n in ports if d=='output'],
  production_source_changed=False,hardware_tested=False,physical_CDC_accepted=False,whole_endpoint_formal_proof=False)
 try:
  cmd=['iverilog','-g2012','-I'+str(ROOT),'-s','tb_task3_m_record_demand','-o',str(out/'simulation.vvp'),str(out/'bench.sv'),str(out/'reference.sv'),*[str(ROOT/s) for s in sources]]
  for name,argv in [('compile',cmd),('simulation',['vvp',str(out/'simulation.vvp')])]:
   r=subprocess.run(argv,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=60)
   (out/(name+'.log')).write_text(r.stdout)
   result[name]=dict(argv=argv,exit_code=r.returncode,log_sha256=sha(out/(name+'.log')))
   if r.returncode:raise ValueError(name+' failed: '+r.stdout)
  match=re.search(r'PASS demand_endpoint_equivalence cycles=(\d+) outputs=(\d+)',r.stdout)
  assert match
  result.update(passed=True,cycles=int(match[1]),outputs=int(match[2]),missing_identity_bit_cases=96,held_TX_and_PANIC_verified=True,
   exact_reference_inverse=True,generated_reference_sha256=sha(out/'reference.sv'),generated_bench_sha256=sha(out/'bench.sv'),
   scope='Directed actual exporter/endpoint regression,all public outputs each active clock,96 single-bit identity mismatches;full guard all-state mapping is a separate proof.')
 except Exception as exc:result['error']=repr(exc);raise
 finally:
  result['inputs_unchanged']=before=={str(p):sha(p) for p in inputs}
  (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
 assert result['inputs_unchanged']
 print({k:result[k] for k in ('passed','cycles','outputs','missing_identity_bit_cases')})
if __name__=='__main__':main()
