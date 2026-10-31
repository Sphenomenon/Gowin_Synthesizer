"""Exact DEMO DMA-fault and USB FIFO async-receiver boundary audit.

Only the two reviewed receiving boundaries gain exceptions. Source sticky
faults, local functional resets and all source-domain consumers remain timed.
This emits no RTL and does not select any accepted or historical profile.
"""
from pathlib import Path
import fnmatch
import hashlib
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.workstation_runtime_pcm_cdc import PcmNetlist, Graph, BooleanDiagram, TOP
from tools.workstation_synthesis_netlist import SynthesisNetlist, IDENTIFIER
from tools.workstation_recording_phase1_cdc import complete_closure

POLICY = "independent-demo-boundary-cdc-v1"
TOOL = "tools/workstation_demo_boundary_cdc.py"
AUDIT_SOURCES = (TOOL, "tools/workstation_runtime_pcm_cdc.py",
    "tools/workstation_synthesis_netlist.py", "tools/workstation_recording_phase1_cdc.py")
D='u_managed/runtime/delay_dma';E='u_managed/runtime/service/workstation/runtime_effects.effects';RF=E+'/delay_stage/u_read_fifo'
U='u_native_usb/input_owner';F=U+'/events/fifo/unbuffered';R=F+'/write_domain_reset';A='u_managed/runtime'
FAULTS=('watchdog_fault','protocol_fault','peer_fault')
PROPOSAL=(f'set_false_path -from [get_pins {{{" ".join(D+"/"+x+"_s*/Q" for x in FAULTS)}}}] -to [get_pins {{{E}/dma_fault_meta_s*/D}}]\n'
 f'set_max_delay 2.000 -from [get_pins {{{E}/dma_fault_meta_s*/Q}}] -to [get_pins {{{E}/dma_fault_sync_s*/D}}]\n'
 f'set_false_path -from [get_pins {{{U}/queue_release_5_s*/Q}}] -to [get_pins {{{R}/release_q_0_s*/CLEAR {R}/release_q_1_s*/CLEAR}}]\n'
 f'set_max_delay 2.000 -from [get_pins {{{R}/release_q_0_s*/Q}}] -to [get_pins {{{R}/release_q_1_s*/D}}]\n')

def require(condition, message):
    if not condition:
        raise ValueError("DEMO boundary CDC audit: " + message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def proposed_constraints():
    return PROPOSAL


def select_demo_boundary(stage, sdc, role):
    require(role in ("M", "W"), "unknown DEMO role")
    lines = proposed_constraints().splitlines()
    require(all(line not in sdc.splitlines() for line in lines), "DEMO boundary lines already installed")
    source = Path(stage) / TOOL
    result = sdc + ("" if not sdc or sdc.endswith("\n") else "\n") + proposed_constraints()
    return result, dict(policy=POLICY, role=role, source=TOOL,
        source_sha256=digest(source), added_lines=lines)


def verify_demo_boundary(stage, sdc, role, evidence):
    require(role in ("M", "W"), "unknown DEMO role")
    lines = proposed_constraints().splitlines()
    if evidence is None:
        require(all(line not in sdc.splitlines() for line in lines),
                "DEMO boundary lines lack explicit selection evidence")
        return dict(mode="sealed_legacy_without_demo_boundary_additions")
    require(isinstance(evidence, dict) and evidence.get("source") == TOOL,
            "DEMO boundary selected source changed")
    require(evidence.get("source_sha256") == digest(Path(stage) / TOOL),
            "DEMO boundary sealed source identity changed")
    expected = dict(policy=POLICY, role=role, source=TOOL,
        source_sha256=evidence["source_sha256"], added_lines=lines)
    require(evidence == expected, "DEMO boundary selection metadata changed")
    require(all(sdc.splitlines().count(line) == 1 for line in lines),
            "DEMO boundary selected line absent or duplicated")
    return dict(evidence, installed_lines_verified=True)


def closure_eq(actual, endpoints, primitives, label):
    require(actual["ff_endpoints"] == dict(sorted(endpoints.items())), label + " all FF consumers drift")
    require(actual["primitive_endpoints"] == dict(sorted(primitives.items())), label + " opaque consumers drift")
    require(not actual["top_output_endpoints"], label + " top output consumer")


def netlist(text, *, mapping="synthesis"):
    require(mapping in ("synthesis", "routed"), "unknown explicit mapping")
    if mapping == "synthesis":
        return PcmNetlist(text, TOP)
    n = SynthesisNetlist(text, TOP)
    require(set(n.frames) == {""}, "routed netlist must be flat")
    modules = list(re.finditer(r"^module\s+(" + IDENTIFIER + r")\s*\((.*?)^endmodule\b", text, re.M | re.S))
    require(len(modules) == 1, "routed module inventory")
    instances = re.compile(r"^[ \t]*(" + IDENTIFIER + r")[ \t]+(" + IDENTIFIER + r")[ \t]*\((.*?)\);", re.M | re.S)
    ports = re.compile(r"\.(?:(\\[^\s]+)[ \t]+|([A-Za-z_$][A-Za-z0-9_$]*))\s*\(\s*([^()]*?)\s*\)")
    seen, count = set(), 0
    for match in instances.finditer(modules[0][2]):
        p = match[2].removeprefix("\\")
        require(p in n.cells and p not in seen, "duplicate/unknown routed instance " + p)
        seen.add(p)
        bindings = {}
        for port in ports.finditer(match[3]):
            key = (port[1] or port[2]).removeprefix("\\")
            require(key not in bindings, "duplicate routed named port " + p + "/" + key)
            bindings[key] = port[3].strip()
            count += 1
        require(not ports.sub("", match[3]).strip(" \t\r\n,"), "unparsed routed named port " + p)
        require(bindings == n.cells[p]["ports"], "routed named-port parser disagreement " + p)
    require(seen == set(n.cells), "incomplete whole routed primitive inventory")
    n.demo_boundary_lexical_audit = dict(whole_flat_vo_strict=True, primitive_count=len(seen),
        named_port_count=count, original_bytes_rewritten=False, shared_parser_modified=False)
    return n

def audit(n, *, mapping="synthesis"):
 require(mapping in ("synthesis", "routed"), "unknown explicit mapping")
 if mapping == "routed":
  require(getattr(n, "demo_boundary_lexical_audit", {}).get("whole_flat_vo_strict") is True, "routed strict named-port inventory missing")
 g=Graph(n);reg=lambda scope,stem,bit=None:g.register(scope,stem,bit);q=lambda scope,stem,bit=None:n.pin(reg(scope,stem,bit),'Q')
 def ff(p,domain,unconditional=False,clear=None):
  c=n.cells[p];require(c['kind']=='DFFCE' and set(c['ports'])=={'D','Q','CLK','CE','CLEAR'},'FF shape '+p)
  require(n.pin(p,'CLK')==domain,'FF clock '+p)
  require(c['parameters'].get('INIT',"1'b0")=="1'b0",'FF INIT '+p)
  if unconditional:require(n.pin(p,'CE') in g.high,'FF CE '+p)
  if clear is not None:require(n.pin(p,'CLEAR')==clear,'FF CLEAR '+p)
 def exp_add(out,scope,stem,bits,pin,domain):
  for bit in bits:out[reg(scope,stem,bit)+'/'+pin]=domain
 fault_regs=[reg(D,s) for s in FAULTS];meta=reg(E,'dma_fault_meta');sync=reg(E,'dma_fault_sync')
 mem_release=reg(A,'memory_release',2);compute_release=reg(A,'compute_release',2)
 require(n.pin(mem_release,'CLK')=='memory_clk' and n.pin(compute_release,'CLK')=='audio_clk','actual source release domains')
 mem_clear=n.pin(fault_regs[0],'CLEAR');audio_clear=n.pin(meta,'CLEAR')
 for p in fault_regs:
  ff(p,'memory_clk',clear=mem_clear);require(n.pin(p,'D') in g.high,'fault must be sticky D=1 '+p)
  bd=BooleanDiagram([n.pin(mem_release,'Q')]);require(bd.net(g,mem_clear)==bd.invert(bd.inputs[n.pin(mem_release,'Q')]),'source fault CLEAR exact memory release')
 for p in (meta,sync):ff(p,'audio_clk',True,audio_clear)
 bd=BooleanDiagram([n.pin(compute_release,'Q')]);require(bd.net(g,audio_clear)==bd.invert(bd.inputs[n.pin(compute_release,'Q')]),'fault receiver CLEAR exact compute release')
 require(n.pin(sync,'D')==n.pin(meta,'Q'),'fault second-stage direct link')
 source_nets=[n.pin(p,'Q') for p in fault_regs]
 require(g.support(n.pin(meta,'D'))==set(source_nets),'fault first D must have exactly all three registered sources')
 bd=BooleanDiagram(source_nets);require(bd.net(g,n.pin(meta,'D'))==bd.either(bd.either(bd.inputs[source_nets[0]],bd.inputs[source_nets[1]]),bd.inputs[source_nets[2]]),'fault first D must be exact three-source OR')
 fault_ends={reg(D,'applied_rate_44100_o')+'/CE':'memory_clk',reg(D,'state',0)+'/CE':'memory_clk',reg(RF,'g_large_head.full_q')+'/D':'memory_clk',meta+'/D':'audio_clk'}
 for stem,width,start in [('chunk_buf',256,0),('popped_sample',64,0),('rptr',32,2),('rsp_hold',256,0),('wptr',32,1)]:exp_add(fault_ends,D,stem,range(start,width),'CE','memory_clk')
 exp_add(fault_ends,RF,'write_binary',range(10),'CE','memory_clk');exp_add(fault_ends,RF,'write_gray',range(9),'CE','memory_clk')
 # The two real DEMO builds have distinct mapped DMA FSMs. Select only by
 # the complete first source closure, then require every source and the
 # queue closure to match that exact same role inventory. No clock, prefix
 # or new-consumer filter is used to accommodate a changed mapping.
 source_closures={stem:complete_closure(n,g,[p]) for stem,p in zip(FAULTS,fault_regs)}
 m_fault_ends=dict(fault_ends)
 m_fault_ends[reg(D,'wptr',0)+'/D']='memory_clk'
 exp_add(m_fault_ends,D,'state',(1,2),'D','memory_clk')
 if source_closures[FAULTS[0]]['ff_endpoints']==dict(sorted(m_fault_ends.items())):
  inventory_role='M';fault_ends=m_fault_ends
 else:
  inventory_role='W'
  fault_ends[reg(D,'wptr',0)+'/CE']='memory_clk'
  exp_add(fault_ends,D,'state',(1,2,3),'CE','memory_clk')
 require(len(fault_ends)==(663 if inventory_role=='M' else 664),'reviewed source fault inventory count')
 fault_prims={}
 for prefix in (('',) if mapping=='synthesis' else ('','gowin_add_SDPX9B_')):
  for parity in ('even','odd'):
   for bit in range(2):
    p=RF+'/'+prefix+f'g_large_head.{parity}_memory_g_large_head.{parity}_memory_0_{bit}_s'
    require(n.cells[p]['kind']=='SDPX9B' and n.pin(p,'CLKA')=='memory_clk' and n.pin(p,'CLKB')=='audio_clk','source fault RAM identity/clocks '+p)
    fault_prims[p+'/CEA']={'kind':'SDPX9B','clock_pins':{'CLKA':'memory_clk','CLKB':'audio_clk'}}
 for stem,c in source_closures.items():
  closure_eq(c,fault_ends,fault_prims,'fault '+stem)
 first=complete_closure(n,g,[meta]);closure_eq(first,{sync+'/D':'audio_clk'}, {},'fault first receiver')
 require(first['combinational_cells']==0,'fault first receiver combinational consumer')
 # Exact source six-edge chain and all four reset-condition producers.
 chain=g.group(U,'queue_release',6);input_reset=n.pin(chain[0],'CLEAR')
 for i,p in enumerate(chain):
  ff(p,'audio_clk',True,input_reset)
  require(n.pin(p,'D') in g.high if i==0 else n.pin(p,'D')==n.pin(chain[i-1],'Q'),'queue six-edge chain '+str(i))
  if i<5:closure_eq(complete_closure(n,g,[p]),{chain[i+1]+'/D':'audio_clk'}, {},'queue intermediate '+str(i))
 producer=[reg(U,'event_release',2),reg(U,'connected'),reg(U,'panic_flush')]
 require(all(n.pin(p,'CLK')=='usb_clk' for p in producer),'input reset source domains')
 ev,conn,panic=[n.pin(p,'Q') for p in producer];queueq=n.pin(chain[5],'Q')
 bd=BooleanDiagram([ev,conn,panic]);expect=bd.either(bd.either(bd.invert(bd.inputs[ev]),bd.invert(bd.inputs[conn])),bd.inputs[panic])
 require(g.support(input_reset)=={ev,conn,panic} and bd.net(g,input_reset)==expect,'input reset exact event/connected/panic equation')
 release=g.group(R,'release_q',2);assertion=n.pin(release[0],'CLEAR')
 for p in release:ff(p,'usb_clk',True,assertion)
 require(n.pin(release[0],'D') in g.high and n.pin(release[1],'D')==n.pin(release[0],'Q'),'FIFO two real USB edge chain')
 first_release=complete_closure(n,g,[release[0]]);closure_eq(first_release,{release[1]+'/D':'usb_clk'}, {},'FIFO first release')
 require(first_release['combinational_cells']==0,'FIFO first release combinational consumer')
 bd=BooleanDiagram([ev,conn,panic,queueq]);expected=bd.either(bd.either(bd.either(bd.invert(bd.inputs[ev]),bd.invert(bd.inputs[conn])),bd.inputs[panic]),bd.invert(bd.inputs[queueq]))
 require(g.support(assertion)=={ev,conn,panic,queueq} and bd.net(g,assertion)==expected,'FIFO reset must be input_reset OR !sixth queue release')
 # Reviewed complete queue-Q closure: include same-domain logic and opaque
 # packet-memory endpoints; no domain/prefix filter hides a new consumer.
 queue_ends={reg('u_managed/control_cdc','acknowledge_toggle')+'/CE':'audio_clk',reg('u_managed/events/queue','tail')+('/CE' if inventory_role=='M' else '/D'):'audio_clk',reg(U+'/events/fifo','r_rdy')+'/CE':'audio_clk',reg(U,'queue_write_release',0)+'/D':'usb_clk'}
 if inventory_role=='M':queue_ends[reg(U,'settled_sync',0)+'/D']='usb_clk'
 exp_add(queue_ends,'u_managed/control_cdc','response_held',range(33),'CE','audio_clk');exp_add(queue_ends,'u_managed/events/queue','count',range(2),'D','audio_clk')
 for stem,bits in [('data[0]',range(18)),('data[1]',range(18)),('first',range(2))]:
  for pin in ('D','CE'):exp_add(queue_ends,'u_managed/events/queue',stem,bits,pin,'audio_clk')
 exp_add(queue_ends,F,'consume_r_bin',range(7),'D','audio_clk');exp_add(queue_ends,F,'consume_r_gry',range(7),'CE','audio_clk')
 for stem in ('stage0','stage1'):queue_ends[reg(F+'/rst_cdc',stem)+'/PRESET']='audio_clk'
 exp_add(queue_ends,R,'release_q',range(2),'CLEAR','usb_clk');exp_add(queue_ends,U,'stopped_clock_queue_fence.drain_release',range(6),'CLEAR','audio_clk')
 require(len(queue_ends)==(140 if inventory_role=='M' else 139),'reviewed queue source inventory count')
 packet=F+'/storage_storage_0_0_s';require(n.cells[packet]['kind']=='SDPX9B' and n.pin(packet,'CLKA')=='usb_clk' and n.pin(packet,'CLKB')=='audio_clk','packet RAM clock/identity')
 queue_prims={packet+'/'+pin:{'kind':'SDPX9B','clock_pins':{'CLKA':'usb_clk','CLKB':'audio_clk'}} for pin in ('ADB','OCE')}
 queue_closure=complete_closure(n,g,[chain[5]]);closure_eq(queue_closure,queue_ends,queue_prims,'queue sixth Q')
 pointers=g.group(F,'produce_w_bin',7)+g.group(F,'produce_w_gry',6)
 local=n.pin(pointers[0],'CLEAR');last=n.pin(release[1],'Q')
 for p in pointers:ff(p,'usb_clk',clear=local)
 bd=BooleanDiagram([last]);require(g.support(local)=={last} and bd.net(g,local)==bd.invert(bd.inputs[last]),'only final USB release may reset real write pointers')
 require(sorted(g.fan[local])==sorted((p,'CLEAR','ff') for p in pointers),'functional write reset owns exactly 13 pointer CLEARs')
 return dict(policy=POLICY, mapping=mapping, inventory_role=inventory_role, source_fault_registers=fault_regs,fault_source_closures=source_closures,fault_first_stage_closure=first,
  source_sticky_D_constant_1=True,source_faults_memory_domain=True,source_OR_exact_all_three=True,
  fault_receiver_reset_source=compute_release+'/Q',fault_source_reset_source=mem_release+'/Q',
  queue_source_chain=chain,queue_source_closure=queue_closure,queue_reset_support=[p+'/Q' for p in producer]+[chain[5]+'/Q'],
  fifo_release_chain=release,fifo_first_release_closure=first_release,fifo_write_pointers=pointers,
  functional_pointer_recovery_removal_waived=False,
  acceptance=dict(structural_only=True,metastability_MTBF_verified=False,routed_timing_passed=False,reset_pulsewidth_verified=False,hardware_tested=False))


def validate_sdc(sdc, n, result):
    """Accept only four exact additions; retain all later/functional checks."""
    expected = proposed_constraints().splitlines()
    require(all(sdc.splitlines().count(line) == 1 for line in expected),
            "exact four boundary constraints absent or duplicated")
    all_pins = {p + "/" + pin for p, c in n.cells.items() for pin in c["ports"]}
    resolved = {}
    for body in re.findall(r"\[get_pins \{([^{}]+)\}\]", proposed_constraints()):
        for selector in body.split():
            matches = {p for p in all_pins if fnmatch.fnmatchcase(p, selector)}
            require(len(matches) == 1, "boundary selector must resolve to one exact pin: " + selector)
            resolved[selector] = sorted(matches)
    require(len(resolved) == 11, "reviewed boundary selector inventory")
    g = Graph(n)
    faults = result["source_fault_registers"]
    meta, sync = (g.register(E, stem) for stem in ("dma_fault_meta", "dma_fault_sync"))
    r0, r1 = result["fifo_release_chain"]
    queue_source = result["queue_source_chain"][-1]
    first_data, first_clear = {meta + "/D"}, {r0 + "/CLEAR", r1 + "/CLEAR"}
    false_pairs = ((set(p + "/Q" for p in faults), first_data),
                   ({queue_source + "/Q"}, first_clear))
    for line, (sources, targets) in zip((expected[0], expected[2]), false_pairs):
        bodies = re.findall(r"\[get_pins \{([^{}]+)\}\]", line)
        for body, pins in zip(bodies, (sources, targets)):
            actual = {p for sel in body.split() for p in all_pins if fnmatch.fnmatchcase(p, sel)}
            require(actual == pins, "boundary exception source/receiver inventory")
    for line, pair in zip((expected[1], expected[3]), ((meta, sync), (r0, r1))):
        for body, pin in zip(re.findall(r"\[get_pins \{([^{}]+)\}\]", line),
                             (pair[0] + "/Q", pair[1] + "/D")):
            actual = {p for sel in body.split() for p in all_pins if fnmatch.fnmatchcase(p, sel)}
            require(actual == {pin}, "later 2ns data bound inventory")
    # Source-domain DMA consumers and functional FIFO pointer resets remain
    # timed. Existing, separately owned queue-fence CDC endpoints stay outside
    # this new exception policy; their prior constraints are not regenerated.
    protected = set(result["fault_source_closures"]["watchdog_fault"]["ff_endpoints"])
    protected.update(result["fault_source_closures"]["watchdog_fault"]["primitive_endpoints"])
    protected.update((meta + "/CLEAR", sync + "/D", sync + "/CLEAR", r0 + "/D", r1 + "/D"))
    protected.update(first_clear)
    protected.update(p + "/CLEAR" for p in result["fifo_write_pointers"])
    clocks = {"audio_76m8": "audio_clk", "usb_48m": "usb_clk", "ddr_ui100": "memory_clk"}
    unrelated = []
    for raw in sdc.splitlines():
        line = raw.strip()
        if re.match(r"set_clock_groups\b", line):
            groups = re.findall(r"\[get_clocks\s+\{([^{}]+)\}\]", line)
            require(groups, "unreviewed clock-group syntax")
            require(not any(fnmatch.fnmatchcase(name, selector)
                            for body in groups for selector in body.split() for name in clocks),
                    "whole boundary clock-group exception")
        if not re.match(r"set_false_path\b", line) or line in (expected[0], expected[2]):
            continue
        query = re.findall(r"-to\s+\[(get_pins|get_regs|get_clocks|get_ports)\s+\{([^{}]+)\}\]", line)
        require(len(query) == 1, "unreviewed false-path destination syntax")
        kind, body = query[0]
        matched = set()
        for selector in body.split():
            if kind in ("get_pins", "get_regs"):
                matched.update(p for p in protected if fnmatch.fnmatchcase(
                    p if kind == "get_pins" else p.rsplit("/", 1)[0], selector))
            elif kind == "get_clocks":
                domains = {v for k, v in clocks.items() if fnmatch.fnmatchcase(k, selector)}
                matched.update(p for p in protected if p.rsplit("/", 1)[0] in g.regs and
                               n.pin(p.rsplit("/", 1)[0], "CLK") in domains)
                require(not matched, "whole boundary clock-domain exception")
        if not matched:
            continue
        origins = re.findall(r"-from\s+\[(get_pins|get_regs)\s+\{([^{}]+)\}\]", line)
        require(len(origins) == 1, "exception reaches protected later/functional endpoint")
        source_kind, source_body = origins[0]
        candidates = set(g.regs) if source_kind == "get_regs" else {p + "/Q" for p in g.regs}
        selected = {p for sel in source_body.split() for p in candidates if fnmatch.fnmatchcase(p, sel)}
        if source_kind == "get_pins":
            actual = {p for sel in source_body.split() for p in all_pins if fnmatch.fnmatchcase(p, sel)}
            require(actual == selected, "protected exception source includes a non-FF-Q pin")
        sources = selected if source_kind == "get_regs" else {p.rsplit("/", 1)[0] for p in selected}
        require(sources, "protected exception lacks reviewed FF-Q sources")
        closure = complete_closure(n, g, sources)
        require(not matched.intersection(set(closure["ff_endpoints"]) | set(closure["primitive_endpoints"])),
                "exception reaches protected later/functional endpoint")
        unrelated.append(line)
    # Other timing overrides must not supersede the required 2ns data bound
    # or waive recovery/removal through a min-delay or multicycle command.
    later_targets = {sync + "/D", r1 + "/D"}
    for raw in sdc.splitlines():
        line = raw.strip()
        command = re.match(r"set_(max_delay|min_delay|multicycle_path)\b", line)
        if command is None or line in (expected[1], expected[3]):
            continue
        query = re.findall(r"-to\s+\[(get_pins|get_regs|get_clocks|get_ports)\s+\{([^{}]+)\}\]", line)
        require(len(query) == 1, "unreviewed timing-override destination syntax")
        kind, body = query[0]
        targets = later_targets if command[1] == "max_delay" else protected
        if kind == "get_clocks":
            domains = {v for name, v in clocks.items() for selector in body.split()
                       if fnmatch.fnmatchcase(name, selector)}
            matched = any(p.rsplit("/", 1)[0] in g.regs and
                          n.pin(p.rsplit("/", 1)[0], "CLK") in domains for p in targets)
        else:
            matched = kind != "get_ports" and any(fnmatch.fnmatchcase(
                p if kind == "get_pins" else p.rsplit("/", 1)[0], selector)
                for p in targets for selector in body.split())
        require(not matched, "duplicate or weaker protected timing bound")
    return dict(exact_four_commands=True, query_resolution=resolved,
        fault_first_data_source_count=3, fault_first_data_target_count=1,
        queue_async_clear_source_count=1, queue_async_clear_target_count=2,
        later_data_max_delay_ns=2.0, protected_later_and_functional_pins=len(protected),
        functional_recovery_removal_exceptions_absent=True,
        unrelated_explicit_source_closure_excludes_protected_pins=unrelated,
        whole_boundary_clock_exceptions_absent=True, physical_cdc_accepted=False)
