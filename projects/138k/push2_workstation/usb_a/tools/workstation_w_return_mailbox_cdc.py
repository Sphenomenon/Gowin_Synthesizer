"""W-only held return mailbox: exact mapped protocol and finite payload bounds.

Only the explicit W timing revision selects this helper. This checks actual
VG/VO cells; it neither changes RTL nor certifies whole-project CDC, routed
slack, native-response reachability, or hardware acceptance.
"""
from pathlib import Path
from functools import lru_cache
import bisect, fnmatch, hashlib, re
from tools.workstation_bluetooth_ddr import RAW_STORE_PATH, RAW_STORE_SHA256
from tools.workstation_runtime_pcm_cdc import Graph
from tools.workstation_recording_phase1_cdc import complete_closure
from tools.workstation_synthesis_netlist import IDENTIFIER

TOOL = 'tools/workstation_w_return_mailbox_cdc.py'
POLICY = 'w-demo-held-return-mailbox-v1'
B = 'recording_ble_store'
TOP = 'workstation_custom_138k_top'

def require(ok, message):
 if not ok: raise ValueError('W return mailbox CDC: ' + message)

def digest(path):
 return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def constraints():
 # return_ack_s*/CE also selects return_ack_sync_s0/CE. The exact reviewed
 # ACK FF suffix is intentional; every new mapping must resolve these pins.
 targets = ' '.join((B+'/return_ack_s0/CE', B+'/unpack_active_s*/D',
     B+'/unpack_data_*_s*/CE', B+'/unpack_generation_*_s*/CE',
     B+'/unpack_word_*_s*/CE', B+'/unpack_index_0_s*/CE',
     B+'/unpack_index_1_s*/CE', B+'/unpack_index_2_s*/CE'))
 path = '-from [get_pins {'+B+'/return_generation_*_s*/Q}] -to [get_pins {'+targets+'}]'
 return 'set_max_delay 10.000 '+path+'\nset_false_path -hold '+path+'\n'

def selection_metadata(stage):
 stage=Path(stage)
 require(digest(stage/RAW_STORE_PATH)==RAW_STORE_SHA256,'selected raw source identity changed')
 return dict(policy=POLICY, source=TOOL, source_sha256=digest(stage/TOOL),
     raw_source=RAW_STORE_PATH, raw_source_sha256=RAW_STORE_SHA256,
     logical_return_bits=299, mapped_live_return_bits=296,
     generation_qualification_endpoints=301, setup_budget_ns=10.0,
     hold_only_waiver=True, setup_falsepaths_added=0,
     clocks_or_resets_changed=False, actual_mapped_audit_required=True,
     physical_CDC_accepted=False)

def verify_selection(stage,evidence):
 require(evidence==selection_metadata(stage),'sealed source selection changed')
 return evidence

def lexical_mapping(n,text,mapping):
 require(mapping in ('synthesis','routed'),'unknown mapping')
 if mapping=='synthesis':
  result=getattr(n,'lexical_connection_audit',None)
  require(result is not None and result['original_text_sha256']==hashlib.sha256(text.encode()).hexdigest(),'complete original synthesis named-port parse absent')
  return result
 require(len(n.frames)==1,'routed mapping is not flat')
 expected={p for p,c in n.cells.items() if p.startswith(B+'/') and c['kind'] not in n.modules}
 instances=re.compile(r'^[ \t]*('+IDENTIFIER+r')[ \t]+('+IDENTIFIER+r')[ \t]*\((.*?)\);',re.M|re.S)
 ports=re.compile(r'\.(?:(\\[^\s]+)[ \t]+|([A-Za-z_$][A-Za-z0-9_$]*))\s*\(\s*([^()]*?)\s*\)')
 seen=set();count=0
 for m in instances.finditer(text):
  p=m[2].removeprefix('\\')
  if p not in expected:continue
  require(p not in seen,'duplicate routed raw primitive');seen.add(p);bindings={}
  for port in ports.finditer(m[3]):
   key=(port[1] or port[2]).removeprefix('\\');require(key not in bindings,'duplicate routed raw port');bindings[key]=port[3].strip();count+=1
  require(not ports.sub('',m[3]).strip(' \t\r\n,'),'unparsed routed raw named port')
  require(bindings==n.cells[p]['ports'],'routed raw lexical/parser mismatch')
 require(seen==expected,'incomplete routed raw lexical inventory')
 return dict(raw_primitives=len(seen),named_ports=count,original_bytes_rewritten=False)

def audit(n, *, stage, sdc, mapping, netlist_text):
 selected=selection_metadata(stage)
 lexical=lexical_mapping(n,netlist_text,mapping)
 g=Graph(n);r=lambda stem,bit=None:g.register(B,stem,bit);q=lambda stem,bit=None:n.pin(r(stem,bit),'Q')
 normclk=lambda p:n.canonical('',n.pin(p,'CLK'))
 source_clock=normclk(r('return_pending'));dest_clock=normclk(r('return_ack'))
 require(source_clock=='memory_clk' and dest_clock=='clk_50m','mapped memory/control clock alias changed')
 source_clear=n.pin(r('return_pending'),'CLEAR');dest_clear=n.pin(r('return_ack'),'CLEAR')
 def ff(p,domain):
  c=n.cells[p];require(c['kind']=='DFFCE' and normclk(p)==domain and c['parameters'].get('INIT',"1'b0")=="1'b0",'FF kind/clock/init drift: '+p)
  require(n.pin(p,'CLEAR')==(source_clear if domain==source_clock else dest_clear),'local shared reset drift: '+p)
 def chain(source,first,second,sc,dc):
  a,b,c=(r(s) for s in (source,first,second))
  for p,d in ((a,sc),(b,dc),(c,dc)):ff(p,d)
  require(n.pin(b,'CE') in g.high and n.pin(c,'CE') in g.high,'conditional sync receiving CE')
  require(n.pin(b,'D')==n.pin(a,'Q') and n.pin(c,'D')==n.pin(b,'Q'),'sync bypass/disconnect')
  cl=complete_closure(n,g,[b]);require(cl['ff_endpoints']=={c+'/D':n.pin(c,'CLK')} and not cl['primitive_endpoints'] and not cl['top_output_endpoints'] and cl['combinational_cells']==0,'sync first Q extra consumer')
  return dict(source=a+'/Q',first=b+'/D',second=c+'/D',first_Q=b+'/Q',source_clock=sc,destination_clock=dc,first_q_complete_fanout=cl)
 chains=[chain('return_req','return_req_meta','return_req_sync',source_clock,dest_clock),chain('return_ack','return_ack_meta','return_ack_sync',dest_clock,source_clock)]
 proofs=[];payload=[];fields=[]
 for source,capture,width,bits in (('return_data','unpack_data',256,range(256)),('return_generation','unpack_generation',32,range(32)),('return_word','unpack_word',11,range(3,11))):
  sr=[r(source,i) for i in bits];dr=[r(capture,i) for i in bits]
  for stem,rows in ((source,sr),(capture,dr)):
   matched={p for p in g.regs if re.fullmatch(re.escape(B+'/'+stem)+r'_\d+_s\d+',p)};require(matched==set(rows),'live field bitmap drift: '+stem)
  for a,b in zip(sr,dr):ff(a,source_clock);ff(b,dest_clock);require(n.pin(b,'D')==n.pin(a,'Q'),'payload bit mapping changed')
  payload+=list(zip(sr,dr));fields.append(dict(source=source,capture=capture,logical_width=width,live_bits=list(bits),source_registers=sr,capture_registers=dr))
 require(len(payload)==296,'return live width not296')
 source_ces={n.pin(a,'CE') for a,b in payload};capture_ces={n.pin(b,'CE') for a,b in payload}
 require(len(source_ces)==len(capture_ces)==1,'payload field enables differ')
 preload=next(iter(source_ces));capture=next(iter(capture_ces));pending=q('return_pending')
 proofs.append(g.equivalent('actual296 payload CE is exactly !pending',[preload,pending],lambda x:x[0]==(not x[1])))
 ff(r('return_pending'),source_clock);ff(r('return_req'),source_clock)
 pub=n.pin(r('return_req'),'CE')
 proofs.append(g.equivalent('actual request D inverts current token',[n.pin(r('return_req'),'D'),q('return_req')],lambda x:x[0]==(not x[1])))
 # The exact publication CE is a named arbitrary premise, NOT a proof of
 # native-response reachability. It is not cut in the payload-freeze proof.
 proofs.append(g.equivalent('pending holds until synchronized ACK, outside common reset',[n.pin(r('return_pending'),'D'),n.pin(r('return_pending'),'CE'),pending,q('return_req'),q('return_ack_sync'),pub],lambda x:(x[0] if x[1] else x[2])==((x[2] or x[5]) and (not x[2] or x[3]!=x[4])),cuts={pub}))
 front=g.carry_frontier(capture);require(len(front)==1,'capture generation comparator frontier changed');neq=next(iter(front))
 expected_pairs={frozenset((q('return_generation',i),q('generation',i))) for i in range(32)}
 require(g.inequality_chain(neq)==expected_pairs,'actual generation comparator missing/swapped bits')
 common=[q('return_req_sync'),q('return_ack'),q('unpack_active'),neq,q('fetch_active'),q('clear_pending'),n.canonical('','raw_channel_fault'),n.canonical('','raw_object_fault')]
 eligible=lambda x:not x[3] and x[4] and not x[5] and not x[6] and not x[7]
 cap=lambda x:x[0]!=x[1] and not x[2] and eligible(x)
 proofs.append(g.equivalent('actual296 capture CE exactly synchronized pending and full generation/fence eligibility',[capture,*common],lambda x:x[0]==cap(x[1:]),cuts={neq}))
 ack=r('return_ack');require(n.pin(ack,'D')==q('return_req_sync'),'ACK D not synchronized token')
 idx=[q('unpack_index',i) for i in range(3)];atlast=lambda x:all(x[8:11])
 proofs.append(g.equivalent('actual ACK only final unpack edge or explicit fenced discard',[n.pin(ack,'CE'),*common,*idx],lambda x:x[0]==((x[3] and atlast(x[1:])) or (x[1]!=x[2] and not x[3] and not eligible(x[1:]))),cuts={neq}))
 active=r('unpack_active');ff(active,dest_clock)
 proofs.append(g.equivalent('actual unpack active nextQ begins capture and retires index7',[n.pin(active,'D'),n.pin(active,'CE'),*common,*idx],lambda x:(x[0] if x[1] else x[4])==((x[4] and not atlast(x[2:])) or cap(x[2:])),cuts={neq}))
 for bit in range(3):
  p=r('unpack_index',bit);ff(p,dest_clock)
  def expected_index(x,bit=bit):
   c=x[2:];old=sum(int(c[8+i])<<i for i in range(3));new=(old+1)&7 if c[2] and old!=7 else 0 if cap(c) else old
   return (x[0] if x[1] else c[8+bit])==bool((new>>bit)&1)
  proofs.append(g.equivalent('actual unpack index bit'+str(bit)+' effective nextQ',[n.pin(p,'D'),n.pin(p,'CE'),*common,*idx],expected_index,cuts={neq}))
 # Full actual source-Q consumer closure, including generation qualifiers.
 closures={};pairs=set();sourcepins={a+'/Q' for a,b in payload};directpins={b+'/D' for a,b in payload}
 for a,b in payload:
  cl=complete_closure(n,g,[a]);require(not cl['primitive_endpoints'] and not cl['top_output_endpoints'],'payload reaches opaque/export consumer')
  require(all(n.canonical('',v)==dest_clock for v in cl['ff_endpoints'].values()),'payload reaches unexpected clock')
  closures[a+'/Q']=cl;pairs|={(a+'/Q',t) for t in cl['ff_endpoints']}
 gen_sources={r('return_generation',i)+'/Q' for i in range(32)}
 gen_closure=complete_closure(n,g,[r('return_generation',i) for i in range(32)])
 gen_direct={r('unpack_generation',i)+'/D' for i in range(32)};qual=set(gen_closure['ff_endpoints'])-gen_direct
 require(len(gen_closure['ff_endpoints'])==333 and len(qual)==301,'qualification closure changed; explicit review required')
 relevant_targets={t for s,t in pairs}|{c['first'] for c in chains}|{c['second'] for c in chains}
 pins=sorted(p+'/'+port for p,c in n.cells.items() for port in c['ports']);allpinset=set(pins);cache={}
 def resolve(body):
  if body not in cache:
   result=set()
   for pattern in body.split():
    prefix=pattern[:next((i for i,x in enumerate(pattern) if x in '*?['),len(pattern))];a=bisect.bisect_left(pins,prefix);b=bisect.bisect_right(pins,prefix+'\U0010ffff')
    result.update(p for p in pins[a:b] if fnmatch.fnmatchcase(p,pattern))
   cache[body]=result
  return cache[body]
 @lru_cache(maxsize=None)
 def query(body,kind,side):
  if kind=='get_pins':return resolve(body)
  if kind=='get_regs':return {p for p in allpinset if any(fnmatch.fnmatchcase(p.rsplit('/',1)[0],s) for s in body.split())}
  if kind=='get_clocks':
   aliases=({'memory_clk','ddr_ui100'} if side=='from' else {'clk_50m','clk_50m_d'})
   return (sourcepins if side=='from' else relevant_targets) if any(fnmatch.fnmatchcase(a,s) for a in aliases for s in body.split()) else set()
  require(kind=='get_ports','unknown SDC query kind');return set() # payload starts in FF Q, not top ports
 def coverage(value):
  finite=set();hold=set();setup_cuts=set();weak=set();multicycle=set();rows=[]
  for raw in value.splitlines():
   line=raw.strip()
   if not line.startswith(('set_max_delay ','set_false_path ','set_multicycle_path ')):continue
   matches=list(re.finditer(r'-(from|to)\s+\[(get_pins|get_regs|get_clocks|get_ports)\s+\{([^}]+)\}\]',line))
   require(len(matches)==len(re.findall(r'-(?:from|to)\b',line)), 'unparsed payload constraint query')
   src,tgt=set(sourcepins),set(relevant_targets)
   for m in matches:
    selected=query(m[3],m[2],m[1]);
    if m[1]=='from':src&=selected
    else:tgt&=selected
   hit={(a,b) for a,b in pairs if a in src and b in tgt}
   if not hit:continue
   require('-through' not in line,'unreviewed through selector on payload paths')
   if line.startswith('set_max_delay '):
    m=re.match(r'set_max_delay ([0-9.]+) ',line);require(m is not None,'unparsed max delay')
    if float(m[1])<=10:finite|=hit
    else:weak|=hit
   elif line.startswith('set_multicycle_path '):multicycle|=hit
   elif '-hold' in line:
    options=set(re.findall(r'(?<!\S)-[A-Za-z_]+\b',line))
    require(options <= {'-hold','-from','-to'},'payload false path must waive only hold')
    hold|=hit
   else:setup_cuts|=hit
   rows.append(dict(constraint=line,payload_pair_count=len(hit)))
  return dict(complete=not(pairs-finite or pairs-hold or setup_cuts or weak or multicycle),total_real_pairs=len(pairs),finite_10ns_covered_pairs=len(finite),hold_covered_pairs=len(hold),missing_finite_pairs=sorted(pairs-finite),missing_hold_pairs=sorted(pairs-hold),setup_falsepath_pairs=sorted(setup_cuts),weaker_override_pairs=sorted(weak),multicycle_pairs=sorted(multicycle),relevant_constraints=rows)

 def clock_groups(value):
  for raw in value.splitlines():
   line=raw.strip()
   if not line.startswith('set_clock_groups '):continue
   bodies=re.findall(r'\[get_clocks\s+\{([^}]+)\}\]',line)
   require(bodies,'unparsed clock grouping')
   require(not any(fnmatch.fnmatchcase(clock,pattern) for body in bodies for pattern in body.split()
       for clock in ('clk_50m','clk_50m_d','ddr_ui100','memory_clk')),'whole-clock grouping touches mailbox domains')
 clock_groups(sdc)
 lines=constraints().splitlines()
 require(all(sdc.splitlines().count(line)==1 for line in lines),'qualification bound missing or duplicated')
 fragment=constraints()
 candidate_queries=re.findall(r'\[get_pins \{([^}]+)\}\]',lines[0])
 require(len(candidate_queries)==2 and resolve(candidate_queries[0])==gen_sources and resolve(candidate_queries[1])==qual,'qualification selector misses or adds actual consumers')
 require(sum(len(resolve(x)) for x in candidate_queries[1].split())==301,'qualification selector overlap')
 original=coverage(sdc)
 require(original['complete'],'incomplete finite10ns/hold payload coverage or overriding exception')
 baseline_sdc=sdc
 for line in lines:baseline_sdc=baseline_sdc.replace(line+'\n','',1)
 # Separate synchronizer first/second finite-bound and no setup cut at second.
 def sync_constraints(value):
  rows=[]
  for c in chains:
   firstpat=c['first'].rsplit('_s',1)[0]+'_s*/D';secondpat=c['second'].rsplit('_s',1)[0]+'_s*/D';firstqpat=c['first_Q'].rsplit('_s',1)[0]+'_s*/Q'
   first='set_false_path -to [get_pins {'+firstpat+'}]';second='set_max_delay 2.000 -from [get_pins {'+firstqpat+'}] -to [get_pins {'+secondpat+'}]'
   require(value.splitlines().count(first)==1 and value.splitlines().count(second)==1,'req/ACK exact sync constraints missing')
   require(resolve(firstpat)=={c['first']} and resolve(secondpat)=={c['second']} and resolve(firstqpat)=={c['first_Q']},'req/ACK selector extra consumer')
   aliases={'memory_clk','ddr_ui100'} if c['destination_clock']==source_clock else {'clk_50m','clk_50m_d'}
   for raw in value.splitlines():
    line=raw.strip()
    if not line.startswith(('set_false_path ','set_multicycle_path ','set_max_delay ')):continue
    matched=dict(from_=True,to=True)
    queries=list(re.finditer(r'-(from|to)\s+\[(get_pins|get_regs|get_clocks|get_ports)\s+\{([^}]+)\}\]',line))
    require(len(queries)==len(re.findall(r'-(?:from|to)\b',line)), 'unparsed synchronizer constraint query')
    for m in queries:
     pin=c['first_Q'] if m[1]=='from' else c['second']
     if m[2]=='get_pins':hit=pin in resolve(m[3])
     elif m[2]=='get_regs':hit=any(fnmatch.fnmatchcase(pin.rsplit('/',1)[0],p) for p in m[3].split())
     elif m[2]=='get_clocks':hit=any(fnmatch.fnmatchcase(a,p) for a in aliases for p in m[3].split())
     else:hit=False
     matched['from_' if m[1]=='from' else 'to'] &= hit
    if matched['from_'] and matched['to']:
     require(line==second,'second sync D exception/bound overridden')
   rows.append(dict(first=first,second=second,second_setup_not_cut=True))
  return rows
 chain_constraints=sync_constraints(sdc)
 # Actual mapped primitive mutations and selector/coverage controls. Rebuild
 # local Graph after each mutation; restore original cell bytes immediately.
 negatives=[]
 intended_failure={
  'actual payload overwrite while pending':'Boolean contract changed: negative pending freeze',
  'actual premature pending release':'Boolean contract changed: negative pending releases before ACK',
  'actual conditional req receiver':'conditional sync receiving CE',
  'actual req first-stage bypass':'sync bypass/disconnect',
  'actual ACK first-stage bypass':'sync bypass/disconnect',
  'actual swapped payload bit':'actual payload mapping mismatch',
  'actual unconditional premature ACK':'Boolean contract changed: negative premature ACK'}
 def mutate_check(name,p,port,newvalue,check):
  old=n.cells[p]['ports'][port];require(old!=newvalue,'ineffective mutation');n.cells[p]['ports'][port]=newvalue
  try:
   try:check()
   except (ValueError,KeyError,AssertionError) as e:
    require(intended_failure[name] in str(e),'negative rejected for an unintended reason: '+name+': '+str(e))
    negatives.append(dict(name=name,rejected=True,reason=str(e)))
   else:raise ValueError('negative accepted: '+name)
  finally:n.cells[p]['ports'][port]=old
 def freeze_mutant():
  gg=Graph(n);gg.equivalent('negative pending freeze',[n.pin(payload[0][0],'CE'),pending],lambda x:not(x[0] and x[1]))
 mutate_check('actual payload overwrite while pending',payload[0][0],'CE',"1'b1",freeze_mutant)
 def pending_mutant():
  gg=Graph(n);gg.equivalent('negative pending releases before ACK',[n.pin(r('return_pending'),'D'),n.pin(r('return_pending'),'CE'),pending,q('return_req'),q('return_ack_sync'),pub],lambda x:(x[0] if x[1] else x[2])==((x[2] or x[5]) and (not x[2] or x[3]!=x[4])),cuts={pub})
 mutate_check('actual premature pending release',r('return_pending'),'D',"1'b0",pending_mutant)
 mutate_check('actual conditional req receiver',r('return_req_meta'),'CE',n.cells[r('return_pending')]['ports']['Q'],lambda:chain('return_req','return_req_meta','return_req_sync',source_clock,dest_clock))
 mutate_check('actual req first-stage bypass',r('return_req_sync'),'D',n.cells[r('return_req')]['ports']['Q'],lambda:chain('return_req','return_req_meta','return_req_sync',source_clock,dest_clock))
 mutate_check('actual ACK first-stage bypass',r('return_ack_sync'),'D',n.cells[r('return_ack')]['ports']['Q'],lambda:chain('return_ack','return_ack_meta','return_ack_sync',dest_clock,source_clock))
 mutate_check('actual swapped payload bit',payload[0][1],'D',n.cells[payload[1][1]]['ports']['D'],lambda:require(n.pin(payload[0][1],'D')==n.pin(payload[0][0],'Q'),'actual payload mapping mismatch'))
 def ack_mutant():
  gg=Graph(n);gg.equivalent('negative premature ACK',[n.pin(ack,'CE'),*common,*idx],lambda x:x[0]==((x[3] and atlast(x[1:])) or (x[1]!=x[2] and not x[3] and not eligible(x[1:]))),cuts={neq})
 mutate_check('actual unconditional premature ACK',ack,'CE',"1'b1",ack_mutant)
 for name,mutant in (
  ('drop qualifier finite bound',baseline_sdc+fragment.splitlines()[1]+'\n'),
  ('drop qualifier hold rule',baseline_sdc+fragment.splitlines()[0]+'\n'),
  ('weaken qualifier finite bound',baseline_sdc+fragment.replace('10.000','11.000')),
  ('replace qualifier hold with setup falsepath',baseline_sdc+fragment.replace('set_false_path -hold','set_false_path')),
  ('miss one qualifier endpoint',baseline_sdc+fragment.replace(B+'/unpack_index_1_s*/CE',''))):
  require(not coverage(mutant)['complete'],'coverage negative accepted: '+name);negatives.append(dict(name=name,rejected=True))
 broad=B+'/return_ack_s*/CE';require(resolve(broad)!={r('return_ack')+'/CE'},'ACK alias negative became ineffective');negatives.append(dict(name='broad ACK selector reaches extra sync CE',rejected=True,extra=sorted(resolve(broad)-{r('return_ack')+'/CE'})))

 require(len(negatives)==13 and all(row['rejected'] for row in negatives),'thirteen mapped/constraint negative controls required')
 # Regression cases from actual-VO review. Whitespace and clock queries
 # cannot bypass the first-stage-only exception boundary.
 for name,value,check in (
   ('indented second-stage setup cut',sdc+'  set_false_path -to [get_pins {'+chains[0]['second']+'}]\n',sync_constraints),
   ('indented clock grouping',sdc+'  set_clock_groups -asynchronous -group [get_clocks {ddr_ui100}] -group [get_clocks {clk_50m}]\n',clock_groups),
   ('mixed setup and hold cut',baseline_sdc+fragment.replace('set_false_path -hold','set_false_path -setup -hold'),coverage),
   ('clock-wide ACK second-stage cut',sdc+'set_false_path -to [get_clocks {ddr_ui100}]\n',sync_constraints),
   ('first-Q setup cut without target',sdc+'set_false_path -from [get_pins {'+chains[0]['first_Q']+'}]\n',sync_constraints),
   ('unparsed nonbraced payload query',sdc+'set_max_delay 10.000 -from [get_pins '+B+'/return_generation_*_s*/Q] -to [get_pins {'+B+'/unpack_data_*_s*/CE}]\n',coverage)):
  try:check(value)
  except ValueError as error:negatives.append(dict(name=name,rejected=True,reason=str(error)))
  else:raise ValueError('SDC negative accepted: '+name)
 require(len(negatives)==19,'thirteen primary and six SDC regression controls required')
 verify_selection(stage, selected)
 return dict(policy=POLICY, mapping=mapping, source_selection=selected,
     lexical_audit=lexical, clocks=dict(source=source_clock,destination=dest_clock),
     local_common_reset_pins=dict(source=source_clear,destination=dest_clear),
     common_root_reset_acceptance_delegated_to_existing_strict_gate=True,
     logical_payload_bits=299,mapped_live_payload_bits=296,absent_word_bits=[0,1,2],
     absent_word_bits_have_no_mapped_source_or_capture_FF=True,fields=fields,
     synchronizers=chains,synchronizer_constraints=chain_constraints,
     mapped_boolean_proofs=proofs,generation_comparator_exact32_pairs=True,
     source_pending_payload_freeze_verified=True,pending_release_only_returned_ACK_verified=True,
     capture_and_ACK_local_state_verified=True,
     native_response_reachability_invariant_formally_proven=False,
     narrow_publication_CE_named_as_arbitrary_premise_for_pending_nextQ=True,
     full_source_Q_closures=closures,actual_real_source_consumer_pairs=len(pairs),
     actual_generation_qualifier_endpoints=sorted(qual),
     installed_payload_constraint_coverage=original,negative_controls=negatives,
     primary_negative_control_count=13,additional_sdc_negative_control_count=6,
     complete_payload_10ns_coverage_verified=True,
     whole_source_CDC_accepted=False,physical_CDC_accepted=False,
     routed_timing_verified=False,hardware_tested=False)
