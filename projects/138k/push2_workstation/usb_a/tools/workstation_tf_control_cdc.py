"""Explicit actual-VG TF level/toggle and held-control audit; no installed SDC.

A declared producer is selected before inspecting first-stage D. This new
scope does not weaken any existing scope, generate RTL or accept physical CDC.
"""
from pathlib import Path
from collections import Counter
import argparse
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from tools.workstation_usb2_owner_reset import OwnerResetNetlist
from tools.workstation_runtime_pcm_cdc import Graph, BooleanDiagram, TOP, COMB
from tools.workstation_recording_phase1_cdc import complete_closure
from tools.workstation_runtime_clock_audit import verify_synthesis_identity, VG_RELATIVE
from tools.workstation_ble_ddr_prefix_cdc_scope import validate_profile, CANDIDATE
from tools.workstation_ble_ddr_prefix_cdc_endpoints import validate_synthesis_binding

SCOPE='runtime-r00-no-local-panel-tf-control-v1'
ENDPOINTS='tools/workstation_tf_control_cdc_endpoints.json'
ENDPOINTS_SHA256='51c166a2b134f56166629d1292c74e226734144e984025ed73a7b3ca8ab51a2c'
SOURCE_SHA256={
 'rtl/tf_audio/workstation_tf_frame_bridge.sv':'eb5895b975dc699178a6e451f2f05d481f63424848ebe153c1402a21a63baf31',
 'rtl/tf_audio/workstation_tf_runtime_service.sv':'debe8ca8c0515ea0ef5b1c7c45c9835373a4720731df0cef97f11daddb467612',
}
T='u_tf_audio';F=T+'/frames'
# (id, declared scope/stem/optional bit, receiver scope/stem, clocks)
PAIRS=(
 ('quiet-publication',F,'quiet_published',None,F,'quiet_sync','audio_clk','clk_50m'),
 ('expected-generation-valid',F,'expected_generation_valid_o',None,F,'expected_valid_sync','audio_clk','clk_50m'),
 ('quiesce-return',F,'quiesce_sync',1,F,'quiesce_return_sync','audio_clk','clk_50m'),
 ('memory-stop',T,'memory_stop',None,T,'memory_gate_sync','clk_50m','memory_clk'),
 ('memory-quiet',T,'memory_quiet',None,T,'memory_quiet_sync','memory_clk','clk_50m'),
 ('control-request',T,'control_request',None,T,'request_sync','clk_50m','audio_clk'),
 ('control-ACK',T,'control_ack',None,T,'ack_sync','audio_clk','clk_50m'),
)


def require(ok,message):
 if not ok:raise ValueError('TF control CDC audit: '+message)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ExactTFDiagram(BooleanDiagram):
 """Exact LUT/INV plus only the observed vendor NE ALU_MODE3 primitive.

 Vendor gw5a prim_sim: S=I0 XOR NOT I1; C=1; SUM=S XOR CIN;
 COUT=S?CIN:C. Thus COUT=(I0 XOR I1) OR CIN. I3 must be tied0
 in this reviewed mapping. Other ALU modes remain unsupported and fail.
 """
 def net(self,graph,net,memo=None,active=()):
  memo={} if memo is None else memo
  if net in self.inputs or net in graph.high|graph.low or net in memo:
   return super().net(graph,net,memo,active)
  drivers=graph.drivers[net]
  if len(drivers)==1 and graph.n.cells[drivers[0][0]]['kind']=='ALU':
   p,out=drivers[0];n=graph.n;cell=n.cells[p]
   require(cell['parameters'].get('ALU_MODE')=='3' and n.pin(p,'I3') in graph.low,'unreviewed ALU primitive '+p)
   require(net not in active and out in ('COUT','SUM'),'ALU cycle/output '+p)
   i0,i1,cin=[self.net(graph,n.pin(p,pin),memo,(*active,net)) for pin in ('I0','I1','CIN')]
   different=self.different(i0,i1)
   value=self.either(different,cin) if out=='COUT' else self.different(self.invert(different),cin)
   memo[net]=value
   return value
  return super().net(graph,net,memo,active)


class Audit:
 def __init__(self,n):self.n,self.g=n,Graph(n)

 def ff(self,p,clock,unconditional=False):
  n,g,c=self.n,self.g,self.n.cells[p]
  require(c['kind']=='DFFCE' and c['parameters'].get('INIT',"1'b0")=="1'b0",'FF kind/zero INIT '+p)
  require(n.pin(p,'CLK')==clock and 'CLEAR' in c['ports'],'FF clock/CLEAR '+p)
  require(not unconditional or n.pin(p,'CE') in g.high,'conditional receiving CE '+p)
  require(g.drivers[n.pin(p,'Q')]==[(p,'Q')],'ambiguous registered producer '+p)
  return dict(path=p,kind=c['kind'],clock=clock,clear=n.pin(p,'CLEAR'),d=n.pin(p,'D'),q=n.pin(p,'Q'),ce=n.pin(p,'CE'))

 def cone(self,net):
  n,g=self.n,self.g;memo,active,cells,terminals={},set(),set(),{}
  def visit(value):
   if value in memo:return memo[value]
   require(value not in active,'combinational cycle '+value)
   if value in g.high|g.low:memo[value]=0;return 0
   drivers=g.drivers[value];require(len(drivers)<=1,'ambiguous cone driver '+value)
   if not drivers:terminals[value]=dict(kind='primary_or_opaque');memo[value]=0;return 0
   p,out=drivers[0];c=n.cells[p]
   if p in g.regs:
    terminals[value]=dict(path=p,kind=c['kind'],clock=n.pin(p,'CLK'),port=out);memo[value]=0;return 0
   require(c['kind'] in COMB,'unsupported cone primitive '+p)
   active.add(value);cells.add(p)
   ds=[visit(n.pin(p,pin)) for pin in c['ports'] if pin not in COMB[c['kind']]]
   active.remove(value);memo[value]=1+max(ds,default=0);return memo[value]
  depth=visit(net)
  return dict(root=net,primitive_depth=depth,primitive_cells={p:n.cells[p]['kind'] for p in sorted(cells)},terminals=terminals,
              terminal_clocks=dict(Counter(t.get('clock',t['kind']) for t in terminals.values())))

 def shared_assertion(self,records):
  require(len({x['clear'] for x in records})==1,'common runtime CLEAR differs')
  clear=records[0]['clear']
  return self.g.equivalent('TF common runtime reset',[clear,'reset_n','memory_guard_started'],lambda v:v[0]==int(not(v[1] and v[2])))

 def primitive_clocks(self,closure,clock):
  n,g=self.n,self.g;inventory={}
  associated={('SDPB','CEA'):('CLKA',),('RAM16SDP4','WRE'):('CLK',),('MULTALU27X18','A'):('CLK',)}
  for endpoint in closure['primitive_endpoints']:
   pth,port=endpoint.rsplit('/',1);cell=n.cells[pth];pins=associated.get((cell['kind'],port))
   require(pins is not None,'unreviewed primitive consumer/clock role '+endpoint)
   inventory[endpoint]={}
   for pin in pins:
    bits=[n.canonical(n.scopes[pth],b) for b in g.binding_bits(n.scopes[pth],cell['ports'][pin])]
    require(clock in bits and all(b in g.high|g.low|{clock} for b in bits),'primitive consumer foreign/absent associated clock '+endpoint)
    inventory[endpoint][pin]=bits
  return inventory

 def pair(self,row,inverted=False):
  key,scope,stem,bit,dscope,dstem,sc,dc=row;n,g=self.n,self.g
  # This declaration is independent of receiver D; missing names fail.
  p=g.register(scope,stem,bit);x,y=g.register(dscope,dstem,0),g.register(dscope,dstem,1)
  source,first,second=self.ff(p,sc),self.ff(x,dc,True),self.ff(y,dc,True)
  require(second['d']==first['q'],'declared strict two-FF shift '+key)
  if inverted:
   relation=g.equivalent('registered memory-open complement',[first['d'],source['q']],lambda v:v[0]==1-v[1])
  else:
   require(first['d']==source['q'],'declared publisher first-D '+key);relation=dict(direct_Q_to_D=True)
  assertion=self.shared_assertion([source,first,second])
  source_q,first_q,second_q=[complete_closure(n,g,[z]) for z in (p,x,y)]
  require(first_q==dict(ff_endpoints={y+'/D':dc},primitive_endpoints={},combinational_cells=0,top_output_endpoints={}), 'complete first-Q fanout '+key)
  foreign={ep:clock for ep,clock in source_q['ff_endpoints'].items() if clock!=sc}
  require(foreign=={x+'/D':dc} and not source_q['top_output_endpoints'],'source-Q has undeclared foreign FF/top consumers '+key)
  source_primitive_clocks=self.primitive_clocks(source_q,sc)
  second_foreign={end:clock for end,clock in second_q['ff_endpoints'].items() if clock!=dc}
  allowed={T+'/memory_open_sync_0_s0/D':'clk_50m'} if key=='memory-stop' else {}
  require(second_foreign==allowed,'second-Q undeclared foreign FF '+key)
  second_primitive_clocks=self.primitive_clocks(second_q,dc)
  source_d,source_ce=self.cone(source['d']),self.cone(source['ce'])
  require(all(t.get('clock')==sc for cone in (source_d,source_ce) for t in cone['terminals'].values()),'publisher D/CE has nonlocal or opaque sequential frontier '+key)
  return dict(id=key,declared_producer=source,first=first,second=second,
      publisher_to_first_relation=relation,second_Q_foreign_return_reviewed_separately=bool(second_foreign),second_primitive_clock_bits=second_primitive_clocks,
      source_D_cone=source_d,source_CE_cone=source_ce,common_assertion=assertion,
      source_Q_complete=source_q,source_primitive_clock_bits=source_primitive_clocks,first_Q_complete=first_q,second_Q_complete=second_q,
      strict_registered_single_bit_structure_verified=True,source_D_CE_upstream_CDC_not_accepted=True,
      physical_CDC_accepted=False)

 def held(self):
  n,g=self.n,self.g;h,c=[g.group(T,x,36) for x in ('held_control','compute_control')]
  req,ack,cap=[g.register(T,x) for x in ('control_request','control_ack','control_capture')]
  hrec=[self.ff(p,'clk_50m') for p in h];crec=[self.ff(p,'audio_clk') for p in c]
  reqrec,ackrec,caprec=self.ff(req,'clk_50m'),self.ff(ack,'audio_clk'),self.ff(cap,'audio_clk')
  assertion=self.shared_assertion(hrec+crec+[reqrec,ackrec,caprec])
  require(all(y['d']==x['q'] for x,y in zip(hrec,crec)),'held payload direct D binding')
  hq=[x['q'] for x in hrec];desired=[x['d'] for x in hrec];cq=[x['q'] for x in crec]
  rq=reqrec['q'];asq=n.pin(g.register(T,'ack_sync',1),'Q')
  inputs=list(dict.fromkeys([v for pair in zip(hq,desired) for v in pair]+[rq,asq]))
  b=ExactTFDiagram(inputs);diff=0
  for x,y in zip(hq,desired):diff=b.either(diff,b.different(b.net(g,x),b.net(g,y)))
  update=b.both(b.invert(b.different(b.net(g,rq),b.net(g,asq))),diff)
  nextq=lambda p:b.choose(b.net(g,n.pin(p,'CE')),b.net(g,n.pin(p,'D')),b.net(g,n.pin(p,'Q')))
  for p,q,d in zip(h,hq,desired):require(nextq(p)==b.choose(update,b.net(g,d),b.net(g,q)),'source held effective next-Q '+p)
  require(nextq(req)==b.different(b.net(g,rq),update),'source request toggle effective next-Q')
  source_proof=dict(variables=len(inputs),BDD_nodes=len(b.nodes),universally_verified=True,
      predicate='update=(ACK_sync1==request) AND (held!=desired); held_next=update?desired:held; request_next=request XOR update',
      input_cuts='Exact actual held Qs and declared desired payload D expressions; no logical vanished ports invented.')
  rs=n.pin(g.register(T,'request_sync',1),'Q');aq=ackrec['q'];cp=caprec['q']
  inputs=list(dict.fromkeys([v for pair in zip(hq,cq) for v in pair]+[rs,aq,cp]));b=ExactTFDiagram(inputs)
  for p,q,d in zip(c,cq,hq):require(nextq(p)==b.choose(b.net(g,cp),b.net(g,d),b.net(g,q)),'compute held effective next-Q '+p)
  require(nextq(ack)==b.choose(b.net(g,cp),b.net(g,rs),b.net(g,aq)),'compute ACK effective next-Q')
  require(nextq(cap)==b.both(b.invert(b.net(g,cp)),b.different(b.net(g,rs),b.net(g,aq))),'capture delay effective next-Q')
  dest_proof=dict(variables=len(inputs),BDD_nodes=len(b.nodes),universally_verified=True,
      predicate='compute_next=capture?held:compute; ACK_next=capture?request_sync1:ACK; capture_next=!capture AND (request_sync1!=ACK)')
  source_q=complete_closure(n,g,h);compute_q=complete_closure(n,g,c)
  foreign={ep:clock for ep,clock in source_q['ff_endpoints'].items() if clock!='clk_50m'}
  require(foreign=={p+'/D':'audio_clk' for p in c} and not source_q['primitive_endpoints'] and not source_q['top_output_endpoints'],'held-Q undeclared foreign consumers')
  require(all(v=='audio_clk' for v in compute_q['ff_endpoints'].values()) and not compute_q['top_output_endpoints'],'compute_control foreign FF/top consumer')
  primitive_clocks={}
  for ep in compute_q['primitive_endpoints']:
   pth=ep.rsplit('/',1)[0];cell=n.cells[pth]
   require(cell['kind']=='MULTALU27X18','unreviewed compute-control primitive '+ep)
   bits=[n.canonical(n.scopes[pth],v) for v in g.binding_bits(n.scopes[pth],cell['ports']['CLK'])]
   require('audio_clk' in bits and all(v in g.high|g.low|{'audio_clk'} for v in bits),'compute-control primitive foreign/absent clock '+ep)
   primitive_clocks[ep]=bits
  # Declare the actual live consumer gate, not the optimized-away RTL wire.
  # Generation decoding/transport remains a distinct contract: cut only at
  # the actual live tf_expected_generation bits and retain their full cones.
  gate='u_managed/n1033_s1';require(n.cells[gate]['kind']=='LUT3','declared mapped cancellation gate changed')
  generation=[n.canonical(T,'tf_expected_generation['+str(i)+']') for i in range(32)]
  valid=n.pin(g.register(F,'expected_generation_valid_o'),'Q')
  generation_cones=[self.cone(v) for v in generation]
  require(all(t.get('clock')=='audio_clk' for cone in generation_cones for t in cone['terminals'].values()),'generation gate boundary nonlocal frontier')
  inputs=[v for pair in zip(cq[4:],generation) for v in pair]+[cq[2],valid];b=ExactTFDiagram(inputs)
  equal=b.all([b.invert(b.different(b.net(g,x),b.net(g,y))) for x,y in zip(cq[4:],generation)])
  expected=b.both(b.net(g,cq[2]),b.both(b.net(g,valid),equal))
  require(b.net(g,n.pin(gate,'F'))==expected,'mapped cancellation generation gate effective Boolean function')
  cancellation=dict(declared_live_primitive=gate,output_port='F',actual_net=n.pin(gate,'F'),variables=len(inputs),BDD_nodes=len(b.nodes),
      universally_verified=True,predicate='active=compute_control[2] AND expected_valid AND (compute_control[35:4]==tf_expected_generation[31:0])',
      actual_generation_boundary_nets=generation,actual_generation_boundary_cones=generation_cones,
      generation_transport_accepted=False,vanished_RTL_formal_used=False)
  return dict(source=hrec,destination=crec,request=reqrec,ACK=ackrec,capture=caprec,common_assertion=assertion,
      source_effective_next_Q=source_proof,destination_effective_next_Q=dest_proof,
      source_Q_complete=source_q,destination_Q_complete=compute_q,capture_Q_complete=complete_closure(n,g,[cap]),
      primitive_clock_bits=primitive_clocks,mapped_cancellation_gate=cancellation,physical_payload_flight_or_setup_hold_verified=False,
      RTL_protocol_stopping_and_cancellation_tests_required=True,physical_CDC_accepted=False)


def inventory(n):
 audit=Audit(n);pairs={p[0]:audit.pair(p) for p in PAIRS};held=audit.held()
 pairs['memory-open-complement']=audit.pair(('memory-open-complement',T,'memory_gate_sync',1,T,'memory_open_sync','memory_clk','clk_50m'),inverted=True)
 closures={k:{key:v[key] for key in ('source_Q_complete','second_Q_complete')} for k,v in pairs.items()}
 closures['held-control']={key:held[key] for key in ('source_Q_complete','destination_Q_complete','capture_Q_complete')}
 return dict(pairs=pairs,held_control=held,endpoint_closures=closures)


def source_bundle(root,stage=None):
 root=Path(root)
 for rel,value in SOURCE_SHA256.items():
  require(sha(root/rel)==value,'maintained TF source identity '+rel)
  if stage is not None:require(sha(Path(stage)/rel)==value,'compiled TF source identity '+rel)
 return dict(scope=SCOPE,source_sha256=SOURCE_SHA256,direct_registered_pairs=7,registered_complement_return_pairs=1,payload_width=36,
     source_seen_edge_alias_accepted=False,combinational_source_quiesce_and_memory_ready_not_accepted=True,
     physical_CDC_accepted=False,complete_CDC_accepted=False)


def audit_netlist(root,n):
 source=source_bundle(root);r=inventory(n);path=Path(root)/ENDPOINTS
 require(sha(path)==ENDPOINTS_SHA256,'reviewed endpoint manifest bytes changed')
 declared=json.loads(path.read_text())
 require(declared['scope']==SCOPE and declared['candidate']==CANDIDATE and declared['endpoint_closures']==r['endpoint_closures'],'complete declared consumer closure changed')
 r.update(scope=SCOPE,source=source,passed=True,endpoint_manifest_sha256=ENDPOINTS_SHA256,
     physical_CDC_accepted=False,complete_CDC_accepted=False,routed_timing_verified=False,hardware_tested=False,
     constraints_installed=False,source_or_netlist_modified=False,deployment_allowed=False)
 return r


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--scope',choices=[SCOPE],required=True)
 p.add_argument('--stage',type=Path,required=True);p.add_argument('--process',type=Path,required=True)
 p.add_argument('--output',type=Path,required=True);args=p.parse_args()
 before=verify_synthesis_identity(args.stage,args.process)
 require(before['candidate_identity']==CANDIDATE,'unreviewed actual candidate')
 prepared=json.loads((args.stage.parents[1]/'workstation_profile.json').read_text())
 selection=validate_profile(ROOT,prepared,stage=args.stage);source_bundle(ROOT,args.stage)
 binding=validate_synthesis_binding(args.stage)
 # Seal the actual imported first-party implementation closure, including
 # parsers and transitive source-policy constants used by shared helpers.
 paths={Path(__file__).resolve(),(ROOT/ENDPOINTS).resolve(),*(ROOT/p for p in SOURCE_SHA256)}
 for module in list(sys.modules.values()):
  name=getattr(module,'__file__',None)
  if name and Path(name).resolve().is_relative_to(ROOT.resolve()):paths.add(Path(name).resolve())
 dependencies={str(path):sha(path) for path in sorted(paths)}
 r=audit_netlist(ROOT,OwnerResetNetlist((args.stage/VG_RELATIVE).read_text(),TOP))
 require(before==verify_synthesis_identity(args.stage,args.process),'synthesis inputs changed during audit')
 require(dependencies=={f:sha(f) for f in dependencies},'audit implementation changed during run')
 r.update(synthesis=before,selection=selection,synthesis_binding=binding,audit_inputs_sha256=dependencies,eda_invoked=False,
     first_D_proposal_only=[v['first']['path']+'/D' for v in r['pairs'].values()],SDC_emitted=False,
     remaining=['Complete TF FIFO/Gray, combinational inputs, source-loss and reset inventory remain separate.',
                'Held-payload flight bounds and physical setup/hold, reset/clock proof, routing and hardware acceptance remain separate.'])
 args.output.mkdir(parents=True,exist_ok=False);out=args.output/'review.json';out.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n')
 print(json.dumps(dict(passed=True,pairs=len(r['pairs']),payload_bits=36,report=str(out),sha256=sha(out))))


if __name__=='__main__':main()
