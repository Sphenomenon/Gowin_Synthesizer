#!/usr/bin/env python3
"""Measure an unselected M recording-demand identity comparator experiment.

This runner extracts the exact maintained direct96 guard. The alternate
byte-group expression is an isolated experiment, not a production RTL input.
Require full mapped equivalence, a new explicit source profile, complete M
synthesis and same-constraint P&R before selecting it in the workstation.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib, json, os, re, subprocess, sys, time, xml.etree.ElementTree as ET
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from run_task3_phone_identity_compare import prove
from tools.workstation_runtime_pcm_cdc import Graph
from tools.workstation_synthesis_netlist import SynthesisNetlist
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_memory import clock_estimates
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--candidate',type=Path,required=True,help='Explicit immutable M reference with actual synthesis output')
parser.add_argument('--gowin',type=Path,default='/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/bin/gw_sh')
parser.add_argument('--gowin-lib',type=Path,default='/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/lib')
args=parser.parse_args()
out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
endpoint=root/'rtl/workstation/workstation_task3_m_bus_endpoint.sv'
source=endpoint.read_text();anchor='    wire demand_matches=rx_payload_i[95:0]==common;\n'
assert source.count(anchor)==1
alternative='''    (* syn_keep=1 *) wire [11:0] demand_byte_equal;
    for(genvar demand_byte=0;demand_byte<12;demand_byte=demand_byte+1)begin:g_demand_byte
        assign demand_byte_equal[demand_byte]=rx_payload_i[demand_byte*8+:8]==common[demand_byte*8+:8];
    end
    wire demand_matches=&demand_byte_equal;
'''
# This experiment changes no production input. Preserve the complete expression
# in the receipt; use the already reviewed 192-input Boolean proof unchanged.
paths=[endpoint,Path(__file__),root/'sim/workstation/run_task3_phone_identity_compare.py',root/'tools/workstation_task3_phone_batch_mapped_m.py',root/'tools/workstation_runtime_pcm_cdc.py',root/'tools/workstation_native_protocol_audit.py',root/'tools/workstation_synthesis_netlist.py']
candidate=args.candidate.resolve()
paths.extend(candidate/p for p in ('workstation_profile.json','integration_inputs.json','workstation/Prj1/impl/gwsynthesis/custom_138k_integration.vg'))
before={str(p):sha(p) for p in paths}
result=dict(schema=1,started_utc=datetime.now(timezone.utc).isoformat(),passed=False,input_sha256=before,
 scope='Isolated demand-identity experiment and exact original full-M mapped comparator proof; no selected source, CDC or routed improvement claim.',
 original_expression=anchor,proposed_expression=alternative,cases=[],board_accessed=False,hardware_tested=False,
 production_inputs_changed=False,physical_timing_verified=False)
try:
 env=dict(os.environ);lib=str(args.gowin_lib)
 for key in ('DYLD_LIBRARY_PATH','DYLD_FALLBACK_LIBRARY_PATH','DYLD_FRAMEWORK_PATH','DYLD_FALLBACK_FRAMEWORK_PATH'):env[key]=lib
 for label,block in [('direct96',anchor),('group8',alternative)]:
  folder=out/label;folder.mkdir()
  wrapper='''module demand_identity_probe(input wire clk_i,input wire [95:0] left_i,right_i,output reg match_o);
reg [95:0] received_r,current_r;
wire [255:0] rx_payload_i={160'd0,received_r};wire [95:0]common=current_r;
always @(posedge clk_i)begin received_r<=left_i;current_r<=right_i;match_o<=demand_matches;end
'''+block+'\nendmodule\n'
  (folder/'probe.sv').write_text(wrapper)
  (folder/'clocks.sdc').write_text('create_clock -name clk_i -period 10.000 [get_ports {clk_i}]\n')
  (folder/'run.tcl').write_text('''set root [file normalize [file dirname [info script]]]
cd $root
set_device GW5AST-LV138PG484AC2/I1 -device_version C
set_option -synthesis_tool gowinsynthesis
set_option -top_module demand_identity_probe
set_option -output_base_name demand_identity_probe
set_option -verilog_std sysv2017
set_option -timing_driven 1
set_option -frequency 100
add_file -type verilog [file join $root probe.sv]
add_file -type sdc [file join $root clocks.sdc]
run syn
''')
  command=[str(args.gowin),str(folder/'run.tcl')]
  start=time.monotonic()
  with (folder/'synthesis.log').open('w') as log:
   completed=subprocess.run(command,cwd=folder,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
  if completed.returncode:raise ValueError('synthesis failed: '+label)
  stage=folder/'impl/gwsynthesis';vg=stage/'demand_identity_probe.vg'
  n=SynthesisNetlist(vg.read_text(),'demand_identity_probe');g=Graph(n)
  def reg(stem):
   found=[p for p in g.regs if re.fullmatch(re.escape(stem)+r'_s\d+',p)]
   if len(found)!=1:raise ValueError('probe register absent/ambiguous: '+stem)
   return found[0]
  proof=prove(n,[n.pin(reg('received_r_'+str(i)),'Q') for i in range(96)],
    [n.pin(reg('current_r_'+str(i)),'Q') for i in range(96)],n.pin(reg('match_o'),'D'),equality=True)
  xml=ET.parse(stage/'demand_identity_probe_syn_rsc.xml').getroot()
  row=dict(case=label,command=command,cwd=str(folder),exit_code=completed.returncode,duration_seconds=time.monotonic()-start,
    probe_sha256=sha(folder/'probe.sv'),tcl_sha256=sha(folder/'run.tcl'),sdc_sha256=sha(folder/'clocks.sdc'),log_sha256=sha(folder/'synthesis.log'),
    netlist_path=str(vg),netlist_sha256=sha(vg),proof=proof,
    resources={k.removeprefix('T_'):int(v.split('(')[0]) for k,v in xml.attrib.items() if k.startswith('T_')},
    synthesis_clock_estimates=clock_estimates(stage/'demand_identity_probe_syn.rpt.html'))
  result['cases'].append(row);print(dict(case=label,levels=proof['max_unit_weight_stages'],alu=proof['max_serial_ALU_stages'],clocks=row['synthesis_clock_estimates']),flush=True)
 from tools import workstation_profile as profiles
 artifact=profiles.verify(root,candidate)
 assert artifact['configuration']['demo_role']=='M'
 assert artifact['configuration']['phone_batch_policy']=='full_key_atomic_owner_snapshot_command_v1'
 assert (candidate/'workstation/Prj1/rtl/workstation/workstation_task3_m_bus_endpoint.sv').read_bytes()==endpoint.read_bytes()
 vg=candidate/'workstation/Prj1/impl/gwsynthesis/custom_138k_integration.vg'
 n=protocol_netlist(vg.read_text(),mapping='synthesis');g=Graph(n);scope='u_task3_m_endpoint'
 left=[n.canonical(scope,'task3_pair_rx_payload['+str(i)+']') for i in range(96)];right=[]
 for name in ('generation','session','local_boot'):
  formal='task3_pair_'+name
  assert n.frames[scope]['ports'].get(formal)==formal+'[31:0]'
  right.extend(n.canonical(scope,formal+'['+str(i)+']') for i in range(32))
 chains=[(None,[])]
 for bit,(x,y) in enumerate(zip(left,right)):
  next_chains=[]
  for target,chain in chains:
   found={p for p,pin,_ in g.fan[x] if n.cells[p]['kind']=='ALU' and n.cells[p]['parameters'].get('ALU_MODE')=='3' and
    n.scopes[p]==scope and {n.pin(p,'I0'),n.pin(p,'I1')}=={x,y} and
    (n.pin(p,'CIN') in g.low if target is None else n.pin(p,'CIN')==target)}
   for path in sorted(found):next_chains.append((n.pin(path,'COUT'),chain+[path]))
  if not next_chains:raise ValueError('actual96-bit comparison missing at bit '+str(bit))
  chains=next_chains
 # Media capabilities compare the same low96bits and then another128bits.
 # Select only a complete96-bit chain, never its intermediate COUT tap.
 exact=[]
 for target,chain in chains:
  continuation=[p for p,pin,_ in g.fan[target] if pin=='CIN' and n.cells[p]['kind']=='ALU' and n.cells[p]['parameters'].get('ALU_MODE')=='3']
  if not continuation:exact.append((target,chain))
 if len(exact)!=1:raise ValueError('full96-bit demand guard not unique: '+str(exact))
 target,chain=exact[0]
 result['original_full_M']=prove(n,left,right,target,equality=False)
 result['original_full_M'].update(candidate_identity=json.loads((candidate/'workstation_profile.json').read_text())['candidate_identity'],
  serial_ALU_cells=chain,netlist_path=str(vg),netlist_sha256=sha(vg),reference_candidate_verified=True,
  independent_chain_selection='Exact low96 operand pairs,grounded initial carry,no further NE carry continuation')
 result['passed']=True
except Exception as exc:
 result['error']=repr(exc)
 raise
finally:
 result.update(inputs_unchanged=before=={str(p):sha(p) for p in paths},finished_utc=datetime.now(timezone.utc).isoformat())
 (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
if not result['inputs_unchanged']:raise ValueError('proof inputs changed')
print(dict(passed=result['passed'],inputs_unchanged=result['inputs_unchanged'],evidence=str(out/'verification.json')),flush=True)
