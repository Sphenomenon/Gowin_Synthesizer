from pathlib import Path
import sys,json,hashlib,re,z3
import argparse
u=Path(__file__).resolve().parents[2];sys.path.insert(0,str(u))
parser=argparse.ArgumentParser(description='Source-bound four-state native fault diagnostic proof')
parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
read=lambda rel:(u/rel).read_text()
def eq(s,name,kind='wire'):
 m=re.search(r'\b'+kind+r'\s*(?:\[[^]]+\]\s*)?'+name+r'\s*=([^;]+);',s);assert m,name;return ' '.join(m[1].split())
a=read('rtl/memory/workstation_recording_ddr_arbiter_pipeline.sv');m=read('rtl/memory/workstation_media_memory.sv');r=read('rtl/memory/workstation_ble_raw_ddr_store.sv');bridge=(u/'rtl/memory/workstation_recording_ddr_native_bridge.sv').read_text()
expected={
 'core.app_en':(eq(a,'app_en','assign'),'reset_n && command_full && app_ready && (!command_write || app_write_ready) && (command_write || read_room)'),
 'core.native_probe':(eq(a,'native_fault_probe'),'reset_n && command_full && app_ready_fault_probe_i && (!command_write || app_write_ready) && (command_write || read_room)'),
 'media.client_ready':(eq(m,'client_ready_o','assign'),'client_reset_no && bist_done && !bist_failed && !transport_fault_o'),
 'media.response_probe':(eq(m,'recording_response_fault_probe_o','assign'),'client_reset_no && bist_done && !bist_failed && recording_response'),
 'bridge.ready':(eq(bridge,'native_ready_o','assign'),'native_accept_i && submitted_o'),
 'bridge.protocol':(eq(bridge,'protocol_fault_now'),'(native_accept_i && (!submitted_o || !published_valid_i)) || (submitted_o && !published_valid_i)'),
 'bridge.fault':(eq(bridge,'transport_fault_o','assign'),'transport_fault_i || protocol_fault_o || protocol_fault_now'),
 'raw.probe_ready':(eq(r,'probe_native_ready'),'native_fault_probe_i && unused_submitted'),
 'raw.probe_protocol':(eq(r,'probe_protocol_fault'),'(native_fault_probe_i && (!unused_submitted || !published_valid)) || (unused_submitted && !published_valid)'),
 'raw.probe_bridge':(eq(r,'bridge_without_transport'),'native_protocol_fault_o || probe_protocol_fault'),
 'raw.command':(eq(r,'probe_command_expired'),'published_valid && !probe_native_ready && command_wait>=COMMAND_TIMEOUT_CYCLES-1'),
 'raw.read':(eq(r,'probe_read_expired'),'read_outstanding && !response_fault_probe_i && read_wait>=READ_TIMEOUT_CYCLES-1'),
 'raw.response':(eq(r,'probe_response_bad'),'response_fault_probe_i && !read_outstanding && !probe_native_read_commit'),
 'raw.fault':(eq(r,'fault_without_transport'),'bridge_without_transport || probe_command_expired || probe_read_expired || probe_response_bad'),
}
assert all(got==want for got,want in expected.values()),expected
for row in ['assign native_accept_o[client]=app_en && command_owner==4\'(client);','assign native_fault_probe_o[client]=native_fault_probe && command_owner==4\'(client);']:assert a.count(row)==1
for row in ['.app_ready_fault_probe_i(app_ready_i),','.app_ready(app_ready_i && !transport_fault_o),','assign recording_response_o=client_ready_o && recording_response;']:assert m.count(row)==1
for row in ["1'b0,1'b1:begin",'bridge_fault=transport_fault_i || bridge_without_transport;','memory_fault_now=transport_fault_i || fault_without_transport;','default:begin end']:assert row in r
# Bind the conditional equality proof through the actual queues and W root.
q=read('rtl/memory/workstation_recording_ddr_client_queues.sv')
w=read('rtl/workstation/workstation_task3_w_paired.sv')
from tools import workstation_native_fault_cofactor as repair
for source in repair.manifest()['sources']:repair.restore(source,read(source))
for row in ['.app_ready_fault_probe_i(app_ready_fault_probe_i),', '.native_fault_probe_o(native_fault_probe_o),']:
 assert q.count(row)==1,('queue diagnostic wiring',row)
for row in ['.recording_native_fault_probe_o(recording_native_fault_probe),',
 '.recording_response_fault_probe_o(recording_response_fault_probe),',
 '.native_fault_probe_i(recording_native_fault_probe),',
 '.response_fault_probe_i(recording_response_fault_probe),',
 '.slot_valid_o(recording_valid),.slot_ready_i(recording_ready),.native_accept_i(native_accept_o[8]),',
 '.read_response_i(recording_response),.read_data_i(response_data_o),.transport_fault_i(transport_fault_o),']:
 assert w.count(row)==1,('W authority/diagnostic wiring',row)
assert m.count('assign recording_native_fault_probe_o=native_fault_probe[8];')==1

# Exact Verilog logical operators over 0/1/X/Z, encoded as two bits.
v=lambda n:z3.BitVec(n,2)
c0=z3.BitVecVal(0,2);c1=z3.BitVecVal(1,2);cx=z3.BitVecVal(2,2)
def NOT(x):return z3.If(x==0,c1,z3.If(x==1,c0,cx))
def AND(*xs):return z3.If(z3.Or(*[x==0 for x in xs]),c0,z3.If(z3.And(*[x==1 for x in xs]),c1,cx))
def OR(*xs):return z3.If(z3.Or(*[x==1 for x in xs]),c1,z3.If(z3.And(*[x==0 for x in xs]),c0,cx))
def check(label,assertion,assumptions=(),want='unsat'):
 s=z3.Solver();s.add(*assumptions,assertion);result=s.check();assert str(result)==want,(label,result,s.model()if result==z3.sat else '')
 return dict(result=str(result),counterexample=str(s.model())if result==z3.sat else None)
# Real upstream cofactor: state and counter predicates are unrestricted, including X/Z.
reset,full,ready,write,wready,room,owner,T,br,bd,bf,rsp=[v(n)for n in ('reset','full','ready','write','wready','room','owner_eq','T','bist_reset','bist_done','bist_failed','response')]
actual_en=AND(reset,full,AND(ready,NOT(T)),OR(NOT(write),wready),OR(write,room));probe_en=AND(reset,full,ready,OR(NOT(write),wready),OR(write,room))
actual_accept=AND(actual_en,owner);probe_accept=AND(probe_en,owner);actual_response=AND(br,bd,NOT(bf),NOT(T),rsp);probe_response=AND(br,bd,NOT(bf),rsp)
results={}
results['enclosing_conditional_probe_equality_all_four_state']=check('enclosing equality',z3.Or(actual_accept!=probe_accept,actual_response!=probe_response),[T==0])
results['real_native_command_and_response_still_vetoed_same_edge']=check('same edge veto',z3.Or(actual_en!=0,actual_accept!=0,actual_response!=0),[T==1])
A,R,AP,RP,S,V,P,O,W,C,D=[v(n)for n in ('accept','response','accept_probe','response_probe','submitted','published','protocol_sticky','read_outstanding','write','command_limit','read_limit')]
def protocol(a):return OR(AND(a,OR(NOT(S),NOT(V))),AND(S,NOT(V)))
def faults(a,b):
 nr=AND(a,S);commit=AND(V,nr);return OR(P,protocol(a)),OR(AND(V,NOT(nr),C),AND(O,NOT(b),D),AND(b,NOT(O),NOT(AND(commit,NOT(W)))))
old_bridge_part,old_local=faults(A,R);new_bridge_part,new_local=faults(AP,RP);old_bridge=OR(T,old_bridge_part);old_fault=OR(old_bridge,old_local)
known=z3.Or(T==0,T==1);new_bridge=z3.If(known,OR(T,new_bridge_part),old_bridge);new_fault=z3.If(known,OR(T,new_bridge_part,new_local),old_fault);assume=[z3.Implies(T==0,z3.And(AP==A,RP==R))]
results['complete_raw_bridge_and_fault_equations_all_four_state']=check('raw equality',z3.Or(old_bridge!=new_bridge,old_fault!=new_fault),assume)
# Destructive controls establish that both the branch contract and X/Z fallback matter.
wrong_ready=v('wrong_ready');wrong_owner=v('wrong_owner')
results['reject_wrong_native_readiness']=check('bad ready',actual_accept!=AND(reset,full,wrong_ready,OR(NOT(write),wready),OR(write,room),owner),[T==0],want='sat')
results['reject_wrong_owner']=check('bad owner',actual_accept!=AND(probe_en,wrong_owner),[T==0],want='sat')
results['reject_probe_used_as_acceptance_authority']=check('authority leak',probe_accept!=0,[T==1],want='sat')
results['reject_removed_unknown_transport_fallback']=check('bad X/Z fallback',old_fault!=OR(T,new_bridge_part,new_local),assume,want='sat')
results['reject_missing_immediate_transport_dominance']=check('missing transport',old_fault!=OR(new_bridge_part,new_local),assume,want='sat')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();d=dict(passed=True,scope='All four-state combinational equations under exact upstream conditional equality; no reachable-state restrictions or timing claim',proofs=results,source_equations={k:a for k,(a,b)in expected.items()},inputs={str(p):sha(p)for p in [u/'rtl/memory/workstation_native_fault_cofactor_v1.adaptation.json',Path(__file__),u/'rtl/memory/workstation_recording_ddr_native_bridge.sv']},z3_version=z3.get_version_string(),board_accessed=False)
(out/'boundary-proof.json').write_text(json.dumps(d,indent=2)+'\n');print({k:r['result']for k,r in results.items()})
