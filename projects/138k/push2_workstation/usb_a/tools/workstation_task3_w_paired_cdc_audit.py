"""Explicit W paired CDC proof for the real headless native composition.

The fault/FIFO proof retains the reviewed DEMO Boolean equations and complete
consumer inventories. The paired W queue has no M settled-status receiver.
Retired display scopes gain no invented stand-in mailbox. No legacy auditor,
clock, timing budget or hardware acceptance is changed here.
"""
from pathlib import Path
import bisect
import fnmatch
import hashlib
import json
import re
from tools.workstation_runtime_pcm_cdc import Graph, BooleanDiagram
from tools.workstation_recording_phase1_cdc import complete_closure
from tools.workstation_demo_boundary_cdc import (
    D, E, RF, U, F, R, A, FAULTS, closure_eq, verify_wptr_lsb_nextq,
    validate_sdc as validate_boundary_sdc)
from tools.workstation_native_protocol_audit import (
    audit_control_boundaries, audit_timing_boundaries, APB, DELAY, DMA)
from tools.workstation_runtime_profile import protocol_constraints
from tools.workstation_performance_reset import demo_held_handshake_constraints
from tools.workstation_task3_native_held import zero_ff, inverse, next_proof

POLICY = 'task3-w-paired-retained-native-cdc-v1'
TOOL = 'tools/workstation_task3_w_paired_cdc_audit.py'
AUDIT_SOURCES = (TOOL, 'tools/workstation_demo_boundary_cdc.py',
    'tools/workstation_native_protocol_audit.py', 'tools/workstation_runtime_pcm_cdc.py',
    'tools/workstation_recording_phase1_cdc.py', 'tools/workstation_task3_w_paired_profile.py',
    'tools/workstation_performance_reset.py', 'tools/workstation_runtime_profile.py',
    'tools/workstation_task3_native_held.py', 'tools/workstation_task3_root_reset_audit.py')


def require(condition, message):
    if not condition:
        raise ValueError('paired W CDC audit: ' + message)


# Static paired W specialization of the reviewed DEMO fault/FIFO proof.
# Only the absent M settled-status branch is replaced by an explicit absence
# assertion and the exact paired W 139-endpoint queue inventory.
def _audit_boundary(n, *, mapping="synthesis", expected_role="W", usb_retired=False):
 require(mapping == "synthesis", "paired W routed mapping has not been reviewed")
 require(expected_role == "W", "explicit paired W role required")
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
 # Either reviewed DMA FSM mapping can occur in either DEMO role. Select
 # its complete first-source closure, then require every source to match.
 # Business role is independently bound to the complete USB queue closure.
 # No clock, prefix or new-consumer filter accommodates a changed mapping.
 source_closures={stem:complete_closure(n,g,[p]) for stem,p in zip(FAULTS,fault_regs)}
 m_fault_ends=dict(fault_ends)
 m_fault_ends[reg(D,'wptr',0)+'/D']='memory_clk'
 exp_add(m_fault_ends,D,'state',(1,2),'D','memory_clk')
 mixed_fault_ends=dict(m_fault_ends)
 del mixed_fault_ends[reg(D,'wptr',0)+'/D']
 mixed_fault_ends[reg(D,'wptr',0)+'/CE']='memory_clk'
 if source_closures[FAULTS[0]]['ff_endpoints']==dict(sorted(m_fault_ends.items())):
  fault_inventory=663;fault_ends=m_fault_ends
 elif source_closures[FAULTS[0]]['ff_endpoints']==dict(sorted(mixed_fault_ends.items())):
  fault_inventory=663;fault_ends=mixed_fault_ends
 else:
  fault_inventory=664
  fault_ends[reg(D,'wptr',0)+'/CE']='memory_clk'
  exp_add(fault_ends,D,'state',(1,2,3),'CE','memory_clk')
 require(len(fault_ends)==fault_inventory,'reviewed source fault inventory count')
 fault_prims={}
 for prefix in (('',) if mapping=='synthesis' else ('','gowin_add_SDPX9B_')):
  for parity in ('even','odd'):
   for bit in range(2):
    p=RF+'/'+prefix+f'g_large_head.{parity}_memory_g_large_head.{parity}_memory_0_{bit}_s'
    require(n.cells[p]['kind']=='SDPX9B' and n.pin(p,'CLKA')=='memory_clk' and n.pin(p,'CLKB')=='audio_clk','source fault RAM identity/clocks '+p)
    fault_prims[p+'/CEA']={'kind':'SDPX9B','clock_pins':{'CLKA':'memory_clk','CLKB':'audio_clk'}}
 for stem,c in source_closures.items():
  closure_eq(c,fault_ends,fault_prims,'fault '+stem)
 wptr_lsb_nextq=verify_wptr_lsb_nextq(n,g)
 first=complete_closure(n,g,[meta]);closure_eq(first,{sync+'/D':'audio_clk'}, {},'fault first receiver')
 require(first['combinational_cells']==0,'fault first receiver combinational consumer')
 if usb_retired:
  from tools.workstation_task3_w_usb_retirement import audit_absence
  return dict(policy=POLICY,mapping=mapping,inventory_role='W',
   USB_retirement=audit_absence(n),fault_inventory_endpoints=fault_inventory,
   source_fault_registers=fault_regs,fault_source_closures=source_closures,
   fault_first_stage_closure=first,fault_wptr_lsb_nextq=wptr_lsb_nextq,
   source_sticky_D_constant_1=True,source_faults_memory_domain=True,source_OR_exact_all_three=True,
   fault_receiver_reset_source=compute_release+'/Q',fault_source_reset_source=mem_release+'/Q',
   functional_pointer_recovery_removal_waived=False,
   acceptance=dict(structural_only=True,metastability_MTBF_verified=False,
    routed_timing_passed=False,reset_pulsewidth_verified=False,hardware_tested=False))
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
 queue_ends={reg('u_managed/control_cdc','acknowledge_toggle')+'/CE':'audio_clk',reg(U+'/events/fifo','r_rdy')+'/CE':'audio_clk',reg(U,'queue_write_release',0)+'/D':'usb_clk'}
 exp_add(queue_ends,'u_managed/control_cdc','response_held',range(33),'CE','audio_clk');exp_add(queue_ends,'u_managed/events/queue','count',range(2),'D','audio_clk')
 for stem,bits in [('data[0]',range(18)),('data[1]',range(18)),('first',range(2))]:
  for pin in ('D','CE'):exp_add(queue_ends,'u_managed/events/queue',stem,bits,pin,'audio_clk')
 exp_add(queue_ends,F,'consume_r_bin',range(7),'D','audio_clk');exp_add(queue_ends,F,'consume_r_gry',range(7),'CE','audio_clk')
 for stem in ('stage0','stage1'):queue_ends[reg(F+'/rst_cdc',stem)+'/PRESET']='audio_clk'
 exp_add(queue_ends,R,'release_q',range(2),'CLEAR','usb_clk');exp_add(queue_ends,U,'stopped_clock_queue_fence.drain_release',range(6),'CLEAR','audio_clk')
 queue_closure=complete_closure(n,g,[chain[5]])
 require(not any(p.startswith(U+'/settled_sync_') for p in n.cells),
         'paired W retained retired M settled-status synchronizer')
 queue_ends[reg('u_managed/events/queue','tail')+'/CE']='audio_clk'
 inventory_role='W';tail_mapping='CE'
 require(len(queue_ends)==139,'paired W exact queue source inventory count')
 packet=F+'/storage_storage_0_0_s';require(n.cells[packet]['kind']=='SDPX9B' and n.pin(packet,'CLKA')=='usb_clk' and n.pin(packet,'CLKB')=='audio_clk','packet RAM clock/identity')
 queue_prims={packet+'/'+pin:{'kind':'SDPX9B','clock_pins':{'CLKA':'usb_clk','CLKB':'audio_clk'}} for pin in ('ADB','OCE')}
 closure_eq(queue_closure,queue_ends,queue_prims,'queue sixth Q')
 require(expected_role is None or inventory_role==expected_role,'complete queue inventory does not match selected DEMO role')
 pointers=g.group(F,'produce_w_bin',7)+g.group(F,'produce_w_gry',6)
 local=n.pin(pointers[0],'CLEAR');last=n.pin(release[1],'Q')
 for p in pointers:ff(p,'usb_clk',clear=local)
 bd=BooleanDiagram([last]);require(g.support(local)=={last} and bd.net(g,local)==bd.invert(bd.inputs[last]),'only final USB release may reset real write pointers')
 require(sorted(g.fan[local])==sorted((p,'CLEAR','ff') for p in pointers),'functional write reset owns exactly 13 pointer CLEARs')
 return dict(policy=POLICY, mapping=mapping, inventory_role=inventory_role, fault_inventory_endpoints=fault_inventory, source_fault_registers=fault_regs,fault_source_closures=source_closures,fault_first_stage_closure=first,fault_wptr_lsb_nextq=wptr_lsb_nextq,
  source_sticky_D_constant_1=True,source_faults_memory_domain=True,source_OR_exact_all_three=True,
  fault_receiver_reset_source=compute_release+'/Q',fault_source_reset_source=mem_release+'/Q',
  queue_tail_mapping=tail_mapping,
  queue_source_chain=chain,queue_source_closure=queue_closure,queue_reset_support=[p+'/Q' for p in producer]+[chain[5]+'/Q'],
  fifo_release_chain=release,fifo_first_release_closure=first_release,fifo_write_pointers=pointers,
  functional_pointer_recovery_removal_waived=False,
  acceptance=dict(structural_only=True,metastability_MTBF_verified=False,routed_timing_passed=False,reset_pulsewidth_verified=False,hardware_tested=False))


def audit_boundary(n, sdc, *, mapping='synthesis',usb_retired=False):
    """Prove the actual paired W fault/FIFO boundary and its installed SDC."""
    result = _audit_boundary(n, mapping=mapping, expected_role='W',usb_retired=usb_retired)
    result['installed_sdc'] = validate_boundary_sdc(sdc, n, result,usb_retired=usb_retired)
    return result


def _closure(n, g, sources, expected, label):
    value = complete_closure(n, g, sources)
    require(value['ff_endpoints'] == dict(sorted(expected.items())) and
            not value['primitive_endpoints'] and not value['top_output_endpoints'],
            label + ' complete consumer closure changed')
    return value


def _mailboxes(n, g):
    """Exact retained PC/health mailboxes, with no stand-in for display."""
    retired = ('u_managed/display/', 'u_managed/display_observation_health/',
               'u_video/', 'u_tf_audio/')
    require(not any(p.startswith(retired) for p in n.cells),
            'paired W headless/TF-disabled composition retained retired owner')
    rows = []

    def regs(scope, stem, bits):
        actual = {}
        for p in g.regs:
            match = re.fullmatch(re.escape(scope + '/' + stem) + r'_(\d+)_s\d+', p)
            if match:
                require(int(match[1]) not in actual, 'duplicate payload bit: ' + p)
                actual[int(match[1])] = p
        require(set(actual) == set(bits), 'payload bit inventory changed: ' + scope + '/' + stem)
        return actual

    def unconditional(p, domain):
        zero_ff(n, g, p, domain)
        require(n.pin(p, 'CE') in g.high, 'synchronizer CE changed: ' + p)

    def chain(scope, source, first, second, source_domain, dest_domain):
        source, first, second = [g.register(scope, s) for s in (source, first, second)]
        zero_ff(n, g, source, source_domain)
        for p in (first, second):
            unconditional(p, dest_domain)
        require(n.pin(first, 'CLEAR') == n.pin(second, 'CLEAR') and
                n.pin(first, 'D') == n.pin(source, 'Q') and
                n.pin(second, 'D') == n.pin(first, 'Q'), 'synchronizer reset/bypass changed: ' + first)
        closure = _closure(n, g, [first], {second + '/D': dest_domain}, 'first stage ' + first)
        require(closure['combinational_cells'] == 0, 'first stage gained combinational consumer: ' + first)
        return dict(source=source + '/Q', first=first + '/D', second=second + '/D',
                    first_stage_complete_closure=closure, second_stage_normally_timed=True)

    for scope, bits, source_domain in (
            ('u_managed/pc_bytes', tuple(range(8)), 'clk_50m'),
            ('u_managed/health_snapshot', tuple(range(32, 64)), 'dac_mclk_d')):
        dest_domain = 'audio_clk'
        request = chain(scope, 'request_toggle', 'req_meta', 'req_sync', source_domain, dest_domain)
        acknowledge = chain(scope, 'acknowledge_toggle', 'ack_meta', 'ack_sync', dest_domain, source_domain)
        settled, sync = [g.register(scope, stem) for stem in ('req_settled', 'req_sync')]
        unconditional(settled, dest_domain)
        require(n.pin(settled, 'D') == n.pin(sync, 'Q') and
                n.pin(settled, 'CLEAR') == n.pin(sync, 'CLEAR'), 'third request stage bypass/reset: ' + scope)
        _closure(n, g, [sync], {settled + '/D': dest_domain}, 'second request stage ' + scope)
        held, captured = regs(scope, 'held_data', bits), regs(scope, 'destination_data', bits)
        for collection, domain in ((held, source_domain), (captured, dest_domain)):
            for p in collection.values():
                zero_ff(n, g, p, domain)
        source_enables = {n.pin(p, 'CE') for p in held.values()}
        capture_enables = {n.pin(p, 'CE') for p in captured.values()}
        require(len(source_enables) == len(capture_enables) == 1, 'payload common CE changed: ' + scope)
        source_ce, capture_ce = next(iter(source_enables)), next(iter(capture_enables))
        request_reg = g.register(scope, 'request_toggle')
        ack_reg = g.register(scope, 'acknowledge_toggle')
        require(n.pin(ack_reg, 'D') == n.pin(settled, 'Q') and n.pin(ack_reg, 'CE') == capture_ce,
                'ACK must capture settled request with payload: ' + scope)
        drivers = g.drivers[source_ce]
        require(len(drivers) == 1, 'acceptance gate driver ambiguous: ' + scope)
        gate, output = drivers[0]
        kind = n.cells[gate]['kind']
        require(kind in ('LUT3', 'LUT4') and output == 'F', 'acceptance gate shape changed: ' + scope)
        leaves = [n.pin(gate, 'I' + str(i)) for i in range(int(kind[3:]))]
        req = n.pin(request_reg, 'Q')
        ack_sync = n.pin(g.register(scope, 'ack_sync'), 'Q')
        require(req in leaves and ack_sync in leaves and len(set(leaves)) == len(leaves),
                'acceptance lost request/returned ACK dependence: ' + scope)
        bd = BooleanDiagram(leaves)
        accepted = bd.net(g, source_ce)
        equal = bd.invert(bd.different(bd.inputs[req], bd.inputs[ack_sync]))
        require(bd.both(accepted, bd.invert(equal)) == 0,
                'payload overwrite while awaiting ACK: ' + scope)
        require(bd.net(g, n.pin(request_reg, 'D')) == bd.different(bd.inputs[req], accepted) and
                n.pin(request_reg, 'CE') in g.high, 'request does not toggle exactly on capture: ' + scope)
        settled_q, ack_q = n.pin(settled, 'Q'), n.pin(ack_reg, 'Q')
        bd = BooleanDiagram([settled_q, ack_q])
        require(bd.net(g, capture_ce) == bd.different(bd.inputs[settled_q], bd.inputs[ack_q]),
                'capture must use settled request XOR ACK: ' + scope)
        for bit in bits:
            require(n.pin(captured[bit], 'D') == n.pin(held[bit], 'Q') and
                    g.drivers[n.pin(held[bit], 'Q')] == [(held[bit], 'Q')],
                    'held/capture bit mapping or competing driver: ' + scope + '/' + str(bit))
        closure = _closure(n, g, list(held.values()),
            {p + '/D': dest_domain for p in captured.values()}, 'held payload ' + scope)
        rows.append(dict(scope=scope, request=request, acknowledge=acknowledge,
            third_request_stage=settled + '/D', source_clock=source_domain,
            destination_clock=dest_domain, source_enable=source_ce, capture_enable=capture_ce,
            held_ff_bits=len(bits), registered_ram_bits=0, payload_bits=len(bits),
            payload_sources={str(bit): held[bit] + '/Q' for bit in bits}, ram=[],
            exact_held_payload_closure=closure, source_busy_prevents_overwrite=True,
            request_toggles_on_capture=True, minimum_request_pipeline_stages=3,
            destination_ack_and_payload_capture_share_enable=True))
    return rows


# The source clock release is also the retained PLL/global startup release.
# Its second-Q complete inventory is deliberately exact, rather than accepting
# arbitrary additional consumers by name/domain. This is a synthesis-only
# mapping and certifies the retained mailbox releases, not the other clients.
SHARED_CONTROL_RELEASE_CLOSURE_SHA256 = '477bbd629328a4c398d69f6e7d3951094683948bf87f480190314504e35e35d2'


def _root_release(n, g, clear, root_q, domain, *, local_scope=None, local_side=None):
    support = g.support(clear)
    require(len(support) == 1, 'mailbox CLEAR is not one registered local release')
    last_q = next(iter(support))
    inverse(g, clear, last_q, 'W functional CLEAR inverse final local release')
    reverse, q = [], last_q
    for index in range(3):
        drivers = g.drivers[q]
        require(len(drivers) == 1 and drivers[0][0] in g.regs and drivers[0][1] == 'Q',
                'W local release producer missing/ambiguous')
        p = drivers[0][0]
        zero_ff(n, g, p, domain)
        require(n.pin(p, 'CE') in g.high, 'W local release CE changed')
        reverse.append(p)
        if index < 2:
            q = n.pin(p, 'D')
        else:
            require(n.pin(p, 'D') in g.high, 'W local release first D is not fill-one')
    stages = list(reversed(reverse))
    expected = {
        'clk_50m': ['u_usb_pll/u_pll_init/enable_r_0_s0',
                    'u_usb_pll/u_pll_init/enable_r_1_s0',
                    'u_managed/midi_bytes/source_release_2_s0'],
        'audio_clk': [f'u_managed/midi_bytes/destination_release_{i}_s0' for i in range(3)],
        'dac_mclk_d': [f'u_managed/observation/drops/source_release_{i}_s0' for i in range(3)]}
    if local_scope is not None:
        require(local_scope in ('u_managed/pc_bytes', 'u_managed/health_snapshot') and
                local_side in ('source', 'destination'), 'unreviewed preserved release owner')
        expected[domain] = [g.register(local_scope, 'g_preserved_release.' + local_side + '_pipe', i) for i in range(3)]
    require(stages == expected[domain], 'W reviewed local release mapping changed: ' + domain)
    require(len({n.pin(p, 'CLEAR') for p in stages}) == 1,
            'W release common assertion differs between stages')
    assertion = inverse(g, n.pin(stages[0], 'CLEAR'), root_q, 'W local release exact common root assertion')
    closures = []
    for index in (0, 1):
        if local_scope is None and domain == 'clk_50m' and index == 1:
            closure = complete_closure(n, g, [stages[index]])
            digest = hashlib.sha256(json.dumps(closure, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            require(digest == SHARED_CONTROL_RELEASE_CLOSURE_SHA256 and
                    len(closure['ff_endpoints']) == 14361 and len(closure['primitive_endpoints']) == 245 and
                    len(closure['top_output_endpoints']) == 3,
                    'W shared PLL/control release complete inventory changed')
            mailbox_prefixes = ('u_managed/pc_bytes/', 'u_managed/health_snapshot/')
            require(not any(pin.startswith(mailbox_prefixes) for pin in closure['ff_endpoints']),
                    'W shared early release bypasses mailbox third stage')
            closures.append(dict(source=stages[index] + '/Q', complete_inventory_sha256=digest,
                ff_endpoints=14361, primitive_endpoints=245, top_output_endpoints=3,
                mailbox_functional_consumers_absent=True, other_clients_reset_semantics_not_certified=True))
        else:
            closures.append(_closure(n, g, [stages[index]],
                {stages[index + 1] + '/D': domain}, 'W local release early stage'))
    return dict(stages=stages, final_q=last_q, domain=domain, release_edges=3,
                common_assertion=assertion, exact_early_consumer_closures=closures)


def _held_resets(n, g, result, root):
    from tools.workstation_task3_root_reset_audit import validate_root_publisher
    root_q = validate_root_publisher(n, g, root)
    mailbox_resets = {}
    for mailbox in result['mailboxes']:
        scope = mailbox['scope']
        bits = tuple(int(bit) for bit in mailbox['payload_sources'])
        held = [g.register(scope, 'held_data', bit) for bit in bits]
        captured = [g.register(scope, 'destination_data', bit) for bit in bits]
        source = [g.register(scope, s) for s in ('ack_meta', 'ack_sync', 'request_toggle')] + held
        destination = [g.register(scope, s) for s in ('req_meta', 'req_sync', 'req_settled', 'acknowledge_toggle')]
        destination += captured
        if scope == 'u_managed/pc_bytes':
            source += g.group(scope, 'drop_count', 32)
            destination.append(g.register(scope, 'destination_valid'))
        local_release = result.get('local_stream_release') is not None
        release_regs = [g.register(scope, 'g_preserved_release.' + side + '_pipe', i)
                        for side in ('source', 'destination') for i in range(3)] if local_release else []
        require(set(source + destination + release_regs) == {p for p in g.regs if p.startswith(scope + '/')},
                'paired W mailbox exact functional register inventory changed: ' + scope)
        releases = {}
        for side, owners, domain in (('source', source, mailbox['source_clock']),
                                      ('destination', destination, mailbox['destination_clock'])):
            for p in owners:
                zero_ff(n, g, p, domain)
            clears = {n.pin(p, 'CLEAR') for p in owners}
            require(len(clears) == 1, 'mailbox shared local reset changed: ' + scope)
            releases[side] = dict(_root_release(n, g, next(iter(clears)), root_q, domain,
                local_scope=scope if local_release else None,
                local_side=side if local_release else None),
                                  owners=owners, reset_asserted_value=0)
        source_q, dest_q = releases['source']['final_q'], releases['destination']['final_q']
        cq = lambda stem: n.pin(g.register(scope, stem), 'Q')
        proofs = []
        for stem, prior, release_q in (
                ('ack_meta', 'acknowledge_toggle', source_q), ('ack_sync', 'ack_meta', source_q),
                ('req_meta', 'request_toggle', dest_q), ('req_sync', 'req_meta', dest_q),
                ('req_settled', 'req_sync', dest_q)):
            proofs.append(next_proof(n, g, g.register(scope, stem), [release_q, cq(prior)],
                lambda b, r=release_q, v=cq(prior): b.both(b.inputs[r], b.inputs[v]), scope + '/' + stem))
        for p, h in zip(captured, held):
            def payload_next(b):
                capture = b.different(b.inputs[cq('req_settled')], b.inputs[cq('acknowledge_toggle')])
                value = b.choose(capture, b.inputs[n.pin(h, 'Q')], b.inputs[n.pin(p, 'Q')])
                return b.both(b.inputs[dest_q], value)
            proofs.append(next_proof(n, g, p,
                [dest_q, cq('req_settled'), cq('acknowledge_toggle'), n.pin(h, 'Q')],
                payload_next, scope + '/payload'))
        mailbox_resets[scope] = dict(mode='real_root_three_receiving_edge_release',
            root_power_up_assertion_supported=True, external_button_reset_available=False,
            releases=releases, reset_inclusive_next_q=proofs)
    apb_resets = {}
    for side, stem, domain, names, groups in (
            ('source', 'p_release', 'ram_clk',
             ('request_toggle', 'state_0', 'state_1', 'ack_meta', 'ack_sync', 'ack_settled'),
             (('request_held', 49), ('response_local', 33))),
            ('destination', 'a_release', 'audio_clk',
             ('acknowledge_toggle', 'req_meta', 'req_sync', 'req_settled', 'request_decoded'),
             (('request_local', 49), ('response_held', 33)))):
        release_scope = 'u_task3_pair_link/config_cdc' if side == 'source' else APB
        release = g.group(release_scope, stem, 3)
        owners = [g.register(APB, name) for name in names]
        owners += [p for name, width in groups for p in g.group(APB, name, width)]
        for p in release + owners:
            zero_ff(n, g, p, domain)
        require(all(n.pin(p, 'CE') in g.high for p in release) and n.pin(release[0], 'D') in g.high and
                all(n.pin(release[i], 'D') == n.pin(release[i - 1], 'Q') for i in (1, 2)) and
                len({n.pin(p, 'CLEAR') for p in release}) == len({n.pin(p, 'CLEAR') for p in owners}) == 1,
                'W APB shared payload/control/release assertion changed')
        proof = inverse(g, n.pin(owners[0], 'CLEAR'), n.pin(release[2], 'Q'),
                        'W APB functional reset inverse third local release')
        early = [_closure(n, g, [release[i]], {release[i + 1] + '/D': domain},
                          'W APB early local release') for i in (0, 1)]
        apb_resets[side] = dict(release=release, shared_assertion=n.pin(release[0], 'CLEAR'),
                                affected_registers=len(owners), proof=proof,
                                exact_early_consumer_closures=early)
    require(apb_resets['source']['shared_assertion'] == apb_resets['destination']['shared_assertion'],
            'W APB common assertion differs across domains')
    preset = n.canonical('', 'preset_n')
    apb_resets['common_assertion_proof'] = g.equivalent('W APB exact root AND CPU assertion',
        [apb_resets['source']['shared_assertion'], root_q, preset],
        lambda x: x[0] == 1 - (x[1] & x[2]), cuts=(root_q, preset))
    pc = result['mailboxes'][0]
    return dict(mailbox_resets=mailbox_resets, apb_resets=apb_resets,
        pc_source_pins=list(pc['payload_sources'].values()),
        pc_capture_pins=[g.register('u_managed/pc_bytes', 'destination_data', i) + '/D' for i in range(8)],
        apb_request_source_pins=[p + '/Q' for p in g.group(APB, 'request_held', 49)],
        apb_request_capture_pins=[p + '/D' for p in g.group(APB, 'request_local', 49)],
        new_chains=[pc['request'], *result['timing_boundaries']['apb_response']['chains']],
        max_delay_ns=13.020, pc_minimum_receiving_capture_edge=4,
        apb_request_minimum_receiving_capture_edge=3, physical_timing_verified=False, hardware_tested=False)


def validate_held_sdc(sdc, n, result):
    """Resolve each retained bound and reject new cuts on every later D."""
    mandatory = [line for line in protocol_constraints().splitlines()
        if any(scope in line for scope in ('u_managed/health_snapshot/',
            'u_managed/pc_health_meta_', APB + '/response_held_', DELAY + '/', DMA + '/peer_',
            'u_managed/pc_bytes/ack_meta_'))]
    extra = demo_held_handshake_constraints().splitlines()
    require(len(mandatory) == 18 and len(extra) == 10 and
            all(sdc.splitlines().count(line) == 1 for line in mandatory + extra),
            'paired W retained protocol/held constraints missing, duplicated or changed')
    pins = sorted(p + '/' + port for p, c in n.cells.items() for port in c['ports'])

    def resolved(body):
        actual = set()
        for pattern in body.split():
            prefix = pattern[:next((i for i, char in enumerate(pattern) if char in '*?['), len(pattern))]
            first, last = bisect.bisect_left(pins, prefix), bisect.bisect_right(pins, prefix + '\U0010ffff')
            actual.update(pin for pin in pins[first:last] if fnmatch.fnmatchcase(pin, pattern))
        return actual

    def exact(line, expected):
        bodies = re.findall(r'\[get_pins \{([^}]+)\}\]', line)
        require(len(bodies) == len(expected) and 'get_clocks' not in line,
                'paired W local SDC query shape changed')
        for body, wanted in zip(bodies, expected):
            require(resolved(body) == set(wanted), 'paired W exact SDC query inventory changed: ' + line)

    protected, bounded, hold = set(), set(), set()
    finite_lines = set(mandatory + extra)
    for row in result['mailboxes']:
        source = list(row['payload_sources'].values())
        capture = [pin.rsplit('/', 1)[0].replace('/held_data_', '/destination_data_') + '/D' for pin in source]
        protected.update(capture)
        bounded.update(capture)
        protected.add(row['third_request_stage'])
        if row['scope'] == 'u_managed/health_snapshot':
            rows = [line for line in mandatory if row['scope'] + '/' in line]
            require(len(rows) == 6 and rows[0].startswith('set_max_delay 13.020 ') and
                    rows[1].startswith('set_false_path -hold '), 'health held setup/hold policy changed')
            for line in rows[:2]:
                exact(line, (source, capture))
            hold.add(rows[1])
        for name in ('request', 'acknowledge'):
            chain = row[name]
            protected.add(chain['second'])
            bounded.add(chain['second'])
            first_pattern = chain['first'].rsplit('_s', 1)[0] + '_s*/D'
            second_pattern = chain['second'].rsplit('_s', 1)[0] + '_s*/D'
            first = [line for line in mandatory + extra if first_pattern in line]
            second = [line for line in mandatory + extra if second_pattern in line]
            require(len(first) == len(second) == 1 and first[0].startswith('set_false_path ') and
                    '-hold' not in first[0] and second[0].startswith('set_max_delay 2.000 '),
                    'retained mailbox chain first/second timing policy changed')
            exact(first[0], ([chain['source']], [chain['first']]) if '-from ' in first[0] else ([chain['first']],))
            exact(second[0], ([chain['first'].rsplit('/', 1)[0] + '/Q'], [chain['second']]))
    controls = result['control_boundaries']
    require(controls['tf_control'] is None, 'W retained TF control crossing')
    for row in controls['pc_health_levels']:
        protected.add(row['second'])
        bounded.add(row['second'])
    timing = result['timing_boundaries']
    require(timing['tf_quiesce'] is None, 'W retained TF quiesce crossing')
    for row in timing['delay_heartbeats']:
        protected.add(row['second'])
        bounded.add(row['second'])
        first_pattern = row['first'].rsplit('_s', 1)[0] + '_s*/D'
        second_pattern = row['second'].rsplit('_s', 1)[0] + '_s*/D'
        first = [line for line in mandatory if first_pattern in line]
        second = [line for line in mandatory if second_pattern in line]
        require(len(first) == len(second) == 1 and first[0].startswith('set_false_path -from ') and
                second[0].startswith('set_max_delay 2.000 '), 'heartbeat crossing timing policy changed')
        exact(first[0], ([row['source']], [row['first']]))
        exact(second[0], ([row['first'].rsplit('/', 1)[0] + '/Q'], [row['second']]))
    apb = timing['apb_response']
    apb_lines = [line for line in mandatory if APB + '/response_held_' in line]
    require(len(apb_lines) == 2 and apb_lines[0].startswith('set_max_delay 20.000 ') and
            apb_lines[1].startswith('set_false_path -hold '), 'APB response finite setup/hold policy changed')
    for line in apb_lines:
        exact(line, (apb['source_pins'], apb['capture_pins']))
    protected.update(apb['capture_pins'])
    bounded.update(apb['capture_pins'])
    hold.add(apb_lines[1])
    for row in apb['chains']:
        protected.update((row['second'], row['third']))
    held = result['retained_held_handshakes']
    expected = []
    for source, capture in ((held['pc_source_pins'], held['pc_capture_pins']),
                            (held['apb_request_source_pins'], held['apb_request_capture_pins'])):
        expected.extend((('set_max_delay 13.020 ', source, capture),
                         ('set_false_path -hold ', source, capture)))
        protected.update(capture)
        bounded.update(capture)
    for row in held['new_chains']:
        expected.extend((('set_false_path ', [row['source']], [row['first']]),
                         ('set_max_delay 2.000 ', [row['first'].rsplit('/', 1)[0] + '/Q'], [row['second']])))
        bounded.add(row['second'])
    require(len(expected) == len(extra), 'retained held constraint inventory drift')
    for line, (prefix, source, capture) in zip(extra, expected):
        require(line.startswith(prefix) and (prefix != 'set_false_path ' or '-hold' not in line),
                'retained held payload setup must remain finite')
        exact(line, (source, capture))
        if prefix == 'set_false_path -hold ':
            hold.add(line)
    from tools.workstation_runtime_cdc import MODE_EXCLUSIONS
    for raw in sdc.splitlines():
        line = raw.strip()
        if line.startswith('set_max_delay'):
            for kind, body in re.findall(r'-to\s+\[(get_pins|get_regs)\s+\{([^}]+)\}\]', line):
                require(not any(fnmatch.fnmatchcase(pin if kind == 'get_pins' else pin.rsplit('/', 1)[0], pattern)
                    for pattern in body.split() for pin in bounded) or line in finite_lines,
                    'retained held finite setup bound overridden')
        if not line.startswith('set_false_path'):
            continue
        if 'get_clocks' in line:
            require(line in MODE_EXCLUSIONS, 'paired W retained held whole-clock setup cut forbidden')
        if line in hold:
            continue
        for kind, body in re.findall(r'-to\s+\[(get_pins|get_regs)\s+\{([^}]+)\}\]', line):
            require(not any(fnmatch.fnmatchcase(pin if kind == 'get_pins' else pin.rsplit('/', 1)[0], pattern)
                for pattern in body.split() for pin in protected),
                'timing exception reaches retained later synchronizer/settled/payload D: ' + line)
    return dict(required_local_lines_installed_once=True, exact_required_lines=28,
        mailbox_payload_bits=40, apb_request_bits=49, apb_response_bits=33,
        protected_later_stage_and_payload_pins=sorted(protected),
        later_stage_setup_hold_exceptions_absent=True, finite_setup_bounds_not_overridden=True,
        retired_display_constraints_not_required=True, global_clock_exception_audit_complete=False)


def audit_retirements(n):
    """Explain paired-only dead SDC members and exact synthesized aliases."""
    from tools.workstation_task3_w_paired_profile import RETIRED_SELECTORS
    g = Graph(n)
    require(not any(p.startswith(RETIRED_SELECTORS) for p in n.cells),
            'paired W retired constrained register/owner reappeared')
    media = 'u_managed/media_stop'
    constant_receivers = []
    for stem, kind, reset_pin in (('request_compute', 'DFFCE', 'CLEAR'),
                                   ('hold_compute', 'DFFPE', 'PRESET')):
        first, second = [g.register(media, stem, bit) for bit in (0, 1)]
        for p in (first, second):
            require(n.cells[p]['kind'] == kind and n.pin(p, 'CLK') == 'audio_clk' and
                    n.pin(p, 'CE') in g.high, 'paired W retired source receiver shape changed')
        require(n.pin(first, 'D') in g.low and n.pin(second, 'D') == n.pin(first, 'Q') and
                n.pin(first, reset_pin) == n.pin(second, reset_pin),
                'paired W removed media source is not a constant-zero receiving chain')
        closure = _closure(n, g, [first], {second + '/D': 'audio_clk'}, 'retired media source receiver')
        constant_receivers.append(dict(first=first + '/D', source_constant=0,
            second=second + '/D', receiving_domain='audio_clk', first_stage_closure=closure,
            reset_pin=reset_pin, receiver_retained=True))
    root_q = n.pin(g.register('u_reset', 'started'), 'Q')
    startup = []
    for scope, stem, domain in (
            ('u_managed', 'startup_compute', 'audio_clk'),
            ('u_managed/runtime', 'startup_compute', 'audio_clk'),
            ('u_managed/runtime', 'startup_memory', 'memory_clk'),
            ('u_managed/runtime', 'startup_serial', 'dac_mclk_d')):
        first, second = [g.register(scope, stem, bit) for bit in (0, 1)]
        for p in (first, second):
            zero_ff(n, g, p, domain)
            require(n.pin(p, 'CE') in g.high, 'startup rebind CE changed')
        require(n.pin(first, 'D') == n.canonical('', 'runtime_reset_n') and
                n.pin(second, 'D') == n.pin(first, 'Q') and
                n.pin(first, 'CLEAR') == n.pin(second, 'CLEAR'), 'startup rebind data/reset changed')
        proof = inverse(g, n.pin(first, 'CLEAR'), root_q, 'W startup CLEAR inverse true root')
        closure = _closure(n, g, [first], {second + '/D': domain}, 'W startup first stage')
        startup.append(dict(first=first, second=second, primitive='DFFCE', actual_async_pin='CLEAR',
                            former_pin='RESET', assertion_proof=proof, first_stage_closure=closure))
    scope = 'u_task3_media/cnn_stream/task_service'
    first = g.register(scope, 'backend_meta')
    aliases = [(scope + '/cnn', 'model_memory_ready'), (scope, 'backend_sync')]
    present = [(owner, stem) for owner, stem in aliases
               if any(p.startswith(owner + '/' + stem + '_s') for p in g.regs)]
    require(len(present) == 1, 'CNN second-stage alias absent/ambiguous')
    second = g.register(*present[0])
    require(not any(p.startswith(scope + '/cnn/model_memory_meta_s') for p in n.cells),
            'CNN merged first-stage duplicate reappeared')
    for p in (first, second):
        zero_ff(n, g, p, 'clk_50m')
        require(n.pin(p, 'CE') in g.high, 'CNN backend-ready chain CE changed')
    producer = 'u_task3_media/memory/ddr_client_ready_s'
    backend_binding = None
    if present == [(scope, 'backend_sync')]:
        native = g.register(scope, 'g_domain_reset.native_release', 2)
        control = g.register(scope, 'g_domain_reset.control_release', 2)
        zero_ff(n, g, native, 'memory_clk');zero_ff(n, g, control, 'clk_50m')
        require(n.cells[producer]['kind']=='LUT4' and
            n.cells[producer]['parameters']=={'INIT': "16'h1000"} and
            [n.pin(producer,'I'+str(i))for i in range(4)]==[
                n.canonical('u_task3_media/memory','bist_failed'),
                n.canonical('u_task3_media','task3_memory_transport_fault'),
                n.canonical('','ddr_client_reset_n'),
                n.canonical('u_task3_media/memory','bist_done')],
            'CNN ready BIST/fault/client gate changed')
        backend_binding = g.equivalent('CNN backend first D exact ready AND native final release',
            [n.pin(first,'D'),n.pin(producer,'F'),n.pin(native,'Q')],
            lambda v:v[0]==int(v[1] and v[2]),cuts={n.pin(producer,'F'),n.pin(native,'Q')})
        inverse(g,n.pin(first,'CLEAR'),n.pin(control,'Q'),'CNN backend control-domain release')
        require(n.pin(second,'D')==n.pin(first,'Q') and
            n.pin(first,'CLEAR')==n.pin(second,'CLEAR'),'CNN actual ready second link/reset changed')
    else:
        require(n.cells[producer]['kind'] == 'LUT4' and
                n.cells[producer]['parameters'] == {'INIT': "16'h4000"} and
                n.pin(first, 'D') == n.pin(producer, 'F') and
                n.pin(second, 'D') == n.pin(first, 'Q') and
                n.pin(first, 'CLEAR') == n.pin(second, 'CLEAR'),
                'CNN merged ready first D/reset/second link changed')
        require(n.pin(producer, 'I0') == n.canonical('u_task3_media/memory', 'bist_failed') and
                n.pin(producer, 'I1') == n.canonical('u_task3_media/memory', 'bist_done') and
                n.pin(producer, 'I2') == n.canonical('', 'ddr_client_reset_n') and
                n.pin(producer, 'I3') == n.canonical('', 'n32_4'),
                'CNN merged ready source no longer real memory BIST/client gate')
    first_closure = _closure(n, g, [first], {second + '/D': 'clk_50m'}, 'CNN merged backend first stage')
    return dict(policy=POLICY, retired_selectors=list(RETIRED_SELECTORS),
        retired_registers_and_owners_absent=True, constant_media_receivers=constant_receivers,
        startup_async_pin_rebindings=startup, cnn_backend_ready_merge=dict(
            original_first=scope + '/cnn/model_memory_meta', selected_first=first,
            original_second=scope + '/backend_sync', selected_second=second,
            source_pin=producer + '/F', source_gate=('(!bist_failed && !native_transport_fault && client_reset && bist_done) AND native_release2'
                         if backend_binding is not None else '!bist_failed && bist_done && client_reset && peer_gate'),
            first_stage_complete_closure=first_closure, exact_two_stage_link=True,
            native_release_ready_binding=backend_binding),
        fixed_runtime_retirement_is_W_only=True, routed_mapping_reviewed=False, hardware_tested=False)


def audit_held(stage, sdc, metadata, n, *, mapping='synthesis'):
    """Only the explicitly selected W paired real-root/headless composition."""
    from tools.workstation_task3_w_paired_profile import POLICY as W_POLICY
    from tools.workstation_task3_root_reset_audit import audit_root_startup
    require(mapping == 'synthesis', 'paired W routed mapping has not been reviewed')
    require(metadata.get('worker_media', {}).get('policy') == W_POLICY,
            'explicit paired W sealed role metadata required')
    require(n.frames.get('', {}).get('kind') == 'workstation_custom_138k_top', 'wrong actual W top')
    root = audit_root_startup(n, stage=stage)
    g = Graph(n)
    result = dict(schema=1, policy=POLICY, profile='w-task3-paired', mapping=mapping,
        mailboxes=_mailboxes(n, g),
        control_boundaries=audit_control_boundaries(n, g, profile='w-demo-d'),
        timing_boundaries=audit_timing_boundaries(n, g, profile='w-demo-d'),
        retired_display_and_TF_owners_absent=True, constraints_complete=False,
        routed_timing_verified=False, physical_cdc_accepted=False, hardware_tested=False)
    from tools.workstation_local_stream_release import verify as verify_local_stream
    result['local_stream_release'] = verify_local_stream(stage,
        json.loads((Path(stage).parent.parent/'workstation_profile.json').read_text())['configuration'], metadata.get('local_stream_release'),
        metadata['enabled_inputs'])
    result['retained_held_handshakes'] = _held_resets(n, g, result, root)
    result['paired_constraint_retirement_and_rebinding'] = audit_retirements(n)
    result['installed_local_sdc'] = validate_held_sdc(sdc, n, result)
    result['constraints_complete'] = True
    return dict(gate_applied=True, actual_native_protocol=result, actual_root_startup=root,
        actual_pc_reset_scope='real_root_three_receiving_edge_release',
        physical_timing_verified=False, hardware_tested=False)
