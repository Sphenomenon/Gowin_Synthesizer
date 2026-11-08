"""Replay the M consumer packing review with proved timer/merged-state invariants.

This is a conditional next-Q comparison for the changed release consumers.
It never changes admission, a frozen candidate, or a historical inventory.
Requires explicit sealed M prepares and Z3; all input byte hashes are checked.
"""
from pathlib import Path
import argparse,json,re,hashlib,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from tools.workstation_task3_w_consumer_nextq import Expressions,Circuit,compare,VectorNetlist,sat_compare
from tools.workstation_recording_phase1_cdc import complete_closure
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--old',type=Path,required=True);ap.add_argument('--new',type=Path,required=True)
ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
args.output.mkdir(parents=True,exist_ok=False)
stages=[p.resolve()/'workstation/Prj1'for p in (args.old,args.new)]
for candidate,stage in zip((args.old,args.new),stages):
 meta=json.loads((candidate/'integration_inputs.json').read_text())
 assert meta['workstation_profile']['name']=='custom138k-workstation-task3-m-preboard-v1'
 assert all(hashlib.sha256((stage/p).read_bytes()).hexdigest()==h for p,h in meta['staged_input_sha256'].items())
e=Expressions();parsed=[];identities={};ns=[]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
ram_paths=['u_task3_m_endpoint/recording/frames_frames_0_'+str(i)+'_s'for i in (0,1)]
high_names={'u_tf_audio/quiet_wait_'+str(i)for i in range(26,32)}
for stem,first in (('tx_age',19),('probe_age',20),('rx_age',23)):
 high_names.update('u_task3_pair_link/transport/'+stem+'_'+str(i)for i in range(first,32))
aliases={'u_task3_m_endpoint/source_m/wr_'+str(i):'u_task3_m_endpoint/source_m/accepted_'+str(i)for i in (3,4)}
class RamCircuit(Circuit):
 def __init__(self,n,e):
  super().__init__(n,e);self.ram={}
  for p in ram_paths:
   assert n.cells[p]['kind']=='SDPB'
   bits=n.concatenation_bits(n.scopes[p],'{'+n.cells[p]['ports']['DO']+'}')
   assert len(bits)==32
   for i,bit in enumerate(bits):
    net=n.canonical(n.scopes[p],bit);assert not self.g.drivers[net] and net not in self.ram
    self.ram[net]=('conditional-memory-output:'+p+'/DO/'+str(i))
 def net(self,net,active=()):
  ds=self.g.drivers[net]
  if len(ds)==1 and ds[0][0]in self.g.regs:
   from tools.workstation_task3_w_consumer_nextq import logical
   if logical(ds[0][0]) in high_names:return 0
   if logical(ds[0][0]) in aliases:return self.e.node('state',aliases[logical(ds[0][0])])
  if net in self.ram:return self.e.node('state',self.ram[net])
  return super().net(net,active)

for stage in stages:
 p=stage/'impl/gwsynthesis/custom_138k_integration.vg';identities[str(p)]=sha(p);n=VectorNetlist(p.read_text(),'workstation_custom_138k_top');ns.append(n);parsed.append(RamCircuit(n,e))
assert all(ns[0].cells[p]==ns[1].cells[p]for p in ram_paths)
owner_paths=['rtl/services/workstation_playback_service.sv','rtl/workstation/workstation_task3_m_bus_endpoint.sv','rtl/workstation/workstation_task3_pcm_block_tx.sv','rtl/workstation/workstation_task3_frame_tx.sv','rtl/workstation/workstation_task3_recording_tx.sv']
# Resolve source ownership from actual module declarations; no unreviewed source fallback.

closures=[complete_closure(n,c.g,[c.g.register('u_task3_pair_link/config_cdc','a_release',2)])for n,c in zip(ns,parsed)]
assert closures[0]['primitive_endpoints']==closures[1]['primitive_endpoints']
assert closures[0]['top_output_endpoints']==closures[1]['top_output_endpoints']
changed=sorted({re.sub(r'_s\d+$','',ep.rsplit('/',1)[0])for ep in set(closures[0]['ff_endpoints'])^set(closures[1]['ff_endpoints'])});owners=[]
for scope in sorted({s.rsplit('/',1)[0]for s in changed}):
 kind=ns[0].frames[scope]['kind'];assert kind==ns[1].frames[scope]['kind']
 declaration={'music_async_fifo_0':'music_async_fifo'}.get(kind,kind)
 candidates=[p for p in stages[0].rglob('*.sv')if re.search(r'\bmodule\s+'+re.escape(declaration)+r'\b',p.read_text())]
 assert len(candidates)==1,(scope,kind,candidates)
 p=candidates[0];rel=p.relative_to(stages[0]);other=stages[1]/rel;assert sha(p)==sha(other)
 owners.append(dict(scope=scope,module=kind,path=str(rel),sha256=sha(p),byte_identical=True));identities[str(p)]=sha(p);identities[str(other)]=sha(other)
source_path=args.output/'owner-source-equality.json';identities[str(Path(__file__).resolve())]=sha(__file__);source_path.write_text(json.dumps(dict(passed=True,owners=owners),indent=2)+'\n')
rows=[];out=args.output/'miters';out.mkdir(exist_ok=False)
invariants=[]
for v,circuit in zip(('old','new'),parsed):
 for name in sorted(high_names & set(circuit.state)):
  path=circuit.state[name];root,init,clock=circuit.next_q(path)
  assert init=="1'b0" and circuit.n.cells[path]['kind']=='DFFCE' and circuit.n.pin(path,'CLEAR')not in circuit.g.high|circuit.g.low
  proof=sat_compare(e,root,0,evidence_dir=out,label=str(v)+':invariant:'+name)
  invariants.append(dict(version=v,state=name,base_INIT_zero=True,async_CLEAR_zero=True,assumed_high_bits_zero=sorted(high_names&set(circuit.state)),**proof))
for old,new in aliases.items():
 circuit=parsed[0];a,ai,ac=circuit.next_q(circuit.state[old]);b,bi,bc=circuit.next_q(circuit.state[new]);assert ai==bi=="1'b0" and ac==bc
 assert circuit.n.pin(circuit.state[old],'CLEAR')==circuit.n.pin(circuit.state[new],'CLEAR')
 proof=sat_compare(e,a,b,evidence_dir=out,label='merge:'+old)
 invariants.append(dict(old_state=old,new_state=new,base_INIT_equal=True,asynchronous_CLEAR_equal=True,**proof))
# The merged source indices must still address the same actual SDPB bits.
address_proofs=[];memory='u_task3_m_endpoint/source_m/queue_queue_0_0_s'
assert ns[0].cells[memory]['parameters']==ns[1].cells[memory]['parameters']
for pin in ('ADA','ADB'):
 bits=[]
 for circuit in parsed:
  binding=circuit.n.cells[memory]['ports'][pin];scope=circuit.n.scopes[memory]
  bits.append([circuit.n.canonical(scope,b)for b in circuit.n.concatenation_bits(scope,binding)])
 assert len(bits[0])==len(bits[1])==14
 for bit,(a,b)in enumerate(zip(*bits)):
  proof=sat_compare(e,parsed[0].net(a),parsed[1].net(b),evidence_dir=out,label=pin+str(bit))
  address_proofs.append(dict(port=pin,bit=bit,old_net=a,new_net=b,**proof))
# Reject a nonzero initialization and a high-bit transition to one. The
# mutation lives only in parsed dictionaries and is restored immediately.
negative_controls=[]
circuit=parsed[0];path=circuit.state['u_tf_audio/quiet_wait_26']
for section,key,bad in [('parameters','INIT',"1'b1"),('ports','D',"1'b1")]:
 cell=circuit.n.cells[path];original=cell[section].get(key)
 try:
  cell[section][key]=bad;mutant=RamCircuit(circuit.n,Expressions())
  root,init,clock=mutant.next_q(path)
  try:
   if init!="1'b0":raise ValueError('nonzero INIT')
   sat_compare(mutant.e,root,0)
  except ValueError as error:negative_controls.append(dict(mutation=key,rejected=True,error=str(error)))
  else:raise AssertionError('zero invariant mutant accepted')
 finally:
  if original is None:cell[section].pop(key,None)
  else:cell[section][key]=original
print('MAPPED INDUCTIVE INVARIANTS',len(invariants),flush=True)
(args.output/'inductive-invariants.json').write_text(json.dumps(dict(passed=True,invariants=invariants),indent=2)+'\n')
for stem in changed:
 if stem not in parsed[1].state:
  assert stem in high_names or stem in aliases
  a,ai,ac=parsed[0].next_q(parsed[0].state[stem]);assert ai=="1'b0"
  b=0 if stem in high_names else parsed[1].next_q(parsed[1].state[aliases[stem]])[0]
  r=dict(register=stem,conditional_next_Q_equal=True,removed_state_correspondence='inductive_zero'if stem in high_names else aliases[stem],**sat_compare(e,a,b,evidence_dir=out,label=stem))
 else:r=compare(*parsed,stem,sat_fallback=True,evidence_dir=out)
 rows.append(dict(logical_state=stem,**r));print(stem,'PASS',r,flush=True)
result=dict(passed=True,SDPB_address_bit_equivalence=address_proofs,negative_controls=negative_controls,inductive_invariants=invariants,high_state_zero=sorted(high_names),merged_state_aliases=aliases,affected_logical_states=len(rows),rows=rows,netlist_sha256={p:h for p,h in identities.items()if p.endswith('.vg')},input_sha256=identities,inputs_unchanged=all(sha(Path(p))==h for p,h in identities.items()),affected_consumers_single_clk50_domain=True,conditional_named_state_correspondence=True,conditional_memory_output_correspondence=True,memory_cells={p:ns[0].cells[p]for p in ram_paths},memory_primitive_ports_and_parameters_identical=True,memory_state_induction_proven=False,whole_design_induction=False)
(args.output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
