"""Strict AE350 F806/HCI/audio boundary gate, separate from physical acceptance.

Prepare pins the reviewed implementation. Actual VG gates use the maintained
strict parser, complete fanout walks and Boolean equations; no prefix clock
filter hides extra consumers. Missing or unsupported topology fails closed.
"""
from pathlib import Path
import argparse
import fnmatch
import hashlib
import json
import re
from tools.workstation_runtime_pcm_cdc import PcmNetlist, Graph, BooleanDiagram, COMB
from tools.workstation_runtime_clock_audit import verify_synthesis_identity, VG_RELATIVE, MODE_EXCLUSIONS
from tools.workstation_classic_runtime import cdc_bundle, verify_selection

POLICY='ae350-pcm-cdc-boundaries-v1'
POLICY_SOURCE='tools/workstation_ae350_pcm_cdc_policy.json'
POLICY_SHA256='46a8e7f3eca611833ebd8f19efd03cb2455bc3ad6b1ba66499bed6bae3a21e34'
TOP='workstation_custom_138k_top'
A='u_managed/pcm_apb/commands'
R='u_managed/runtime'
S=R+'/cpu_pcm/session'
O=R+'/cpu_pcm/owner'
H='u_bluetooth/u_core/owner'
Z=R+'/serializer'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(v,message):
    if not v:raise ValueError('AE350 PCM CDC: '+message)

def source_contract(root):
    root=Path(root).resolve();p=root/POLICY_SOURCE
    require(sha(p)==POLICY_SHA256,'reviewed policy bytes changed')
    d=json.loads(p.read_text())
    require(d['policy']==POLICY and d['payload_max_delay_ns']==10 and
            d['synchronizer_max_delay_ns']==2 and not d['physical_acceptance'],'policy or budget changed')
    for name,h in d['source_sha256'].items():
        target=root/name
        require(target.resolve().is_relative_to(root)and sha(target)==h,'reviewed source changed: '+name)
    return dict(policy=POLICY,policy_sha256=sha(p),source_sha256=d['source_sha256'],
        prepared_APB_source=d['prepared_APB_source'],prepared_APB_sha256=d['prepared_APB_sha256'],
        reviewed_source_contracts=True,physical_CDC_accepted=False,release_ready=False)

def prepared(root,stage):
    root,stage=Path(root).resolve(),Path(stage).resolve();result=source_contract(root)
    for name,h in result['source_sha256'].items():
        # Some first-party build helpers are not HDL compilation inputs. The
        # explicit full prepare closure still binds them outside this scope.
        p=stage/name
        if name.startswith('rtl/'):
            require(p.is_file()and sha(p)==h,'prepared source changed: '+name)
    require(sha(stage/result['prepared_APB_source'])==result['prepared_APB_sha256'],
            'actual prepared APB CDC changed')
    profile_path=stage.parents[1]/'workstation_profile.json'
    profile=json.loads(profile_path.read_text())
    require(profile.get('profile')=='custom138k-workstation-classic-runtime-v1',
            'explicit reviewed joint profile required')
    record=profile['classic_runtime']
    verify_selection(root,stage,stage.parents[1],record)
    result.update(candidate_identity=profile['candidate_identity'],prepared_profile_sha256=sha(profile_path),
        staged_source_identity_verified=True,macro_and_port_closure_verified=True,
        constraints=validate_candidate_sdc((stage/'constraints/custom_138k.sdc').read_text()))
    return result

def protected_source_pins():
    """Conservative scalar-name witnesses for source-stage wildcard screening.

    This catches broad overrides before synthesis. It deliberately does not
    claim that these illustrative names are actual tool objects.
    """
    widths=dict(request_held=49,request_local=49,response_held=33,response_local=33,
        p_release=3,a_release=3,state=2,request_toggle=1,acknowledge_toggle=1,
        req_meta=1,req_sync=1,req_settled=1,request_decoded=1,
        ack_meta=1,ack_sync=1,ack_settled=1)
    stems=[(A,name,width)for name,width in widths.items()]
    stems += [(S,'release_pipe',3),(S,'live_o',1),(S,'epoch_o',32),
        (S,'generation_o',32),(R,'pcm_hold_serial',2),
        (R+'/cpu_pcm','switch_inhibit_compute',2),
        ('u_bluetooth/u_core/initializer','boot_id',64),
        (H+'/flow','generations',64),(H+'/flow','active',2),
        (H+'/flow','is_le',2),(H,'classic_ready_o',1),(O,'probe',1)]
    regs=set()
    for scope,name,width in stems:
        regs.update([scope+'/'+name,scope+'/'+name+'_s0'])
        for bit in range(width):
            regs.update(scope+'/'+name+suffix for suffix in
                ('_'+str(bit)+'_s0','['+str(bit)+']','['+str(bit)+']_s0'))
    return {p+'/'+pin for p in regs for pin in ('D','CE','Q','CLEAR','PRESET','CLK')}

def validate_candidate_sdc(text,actual_protected_pins=None):
    expected=cdc_bundle()['sdc'].splitlines();active=[]
    protected=set(actual_protected_pins or ())|protected_source_pins()
    regex=re.compile(r'\[(get_pins|get_regs|get_ports|get_clocks)\s+\{([^{}]+)\}\]')
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.startswith('#'):continue
        active.append(line)
        require(not any(x in line for x in [';', '$', '\\']), 'Tcl evaluation/continuation unsupported')
        shape=regex.sub('QUERY',line)
        require('['not in shape and ']'not in shape,'unsupported query syntax: '+line)
        command=line.split()[0]
        require(command in ('create_clock','create_generated_clock','set_false_path',
            'set_max_delay','set_min_delay','set_input_delay','report_timing'),
            'unreviewed timing command: '+line)
        if command.startswith('create_')or command in ('set_input_delay','report_timing'):continue
        queries=regex.findall(line)
        require(queries,'exception without explicit object query: '+line)
        if any(kind=='get_clocks'for kind,body in queries):
            require(line in MODE_EXCLUSIONS,'whole-clock exception forbidden: '+line)
            continue
        touches=any(fnmatch.fnmatchcase(p if kind=='get_pins'else p.rsplit('/',1)[0],pattern)
            for kind,body in queries if kind in ('get_pins','get_regs')
            for pattern in body.split()for p in protected)
        named=any(prefix in line for prefix in
            [A,S,O,R+'/pcm_hold_serial',R+'/cpu_pcm/switch_inhibit_compute'])
        if touches or named:
            require(line in expected,'unreviewed new-boundary timing override: '+line)
    require(all(active.count(line)==1 for line in expected),'candidate lines missing or duplicate')
    return dict(reviewed_line_count=len(expected),candidate_lines_exact=True,
        wildcard_exception_scan_verified=True,source_name_witnesses_are_actual_objects=False,
        payload_max_delay_ns=10,synchronizer_max_delay_ns=2,
        actual_endpoint_resolution_verified=False,actual_CLEAR_PRESET_resolution_verified=False,
        recovery_removal_verified=False,routed_propagation_verified=False,physical_CDC_accepted=False)

def exact_closure(g,sources,expected,*,label):
    """Walk all fanout, reject aliases with extra drivers and unknown primitives."""
    todo=[g.n.pin(p,'Q')for p in sources];seen=set();ends=set()
    while todo:
        net=todo.pop()
        if net in seen:continue
        seen.add(net)
        require(len(g.drivers[net])==1,'multiple/missing payload driver: '+label+' '+net)
        for p,pin,role in g.fan[net]:
            require(role!='unsupported','unsupported primitive consumer: '+label+' '+p+'/'+pin)
            if role=='ff':ends.add(p+'/'+pin)
            else:todo.extend(g.n.pin(p,out)for out in COMB[g.n.cells[p]['kind']])
    require(ends==set(expected),'missing/extra consumer: '+label+' '+str(sorted(ends^set(expected))))
    return dict(source_registers=list(sources),endpoints=sorted(ends),complete_fanout=True)

def prove(g,label,nets,predicate):
    return g.equivalent(label,nets,predicate)

def audit_apb(n,g,domains):
    """Actual scalar FF inventory, held bit mapping, gates, resets and fanout."""
    widths=dict(request_held=49,request_local=49,response_held=33,response_local=33,
        p_release=3,a_release=3,state=2,request_toggle=None,acknowledge_toggle=None,
        req_meta=None,req_sync=None,req_settled=None,request_decoded=None,
        ack_meta=None,ack_sync=None,ack_settled=None)
    groups={name:g.group(A,name,width)for name,width in widths.items()}
    actual={p for p in g.regs if p.startswith(A+'/')}
    require(actual=={p for group in groups.values()for p in group},'APB FF inventory missing/extra')
    reg=lambda name:groups[name][0]
    q=lambda name:n.pin(reg(name),'Q')
    proofs=[];closures=[];reset_pins=[]
    compute={'request_local','response_held','a_release','acknowledge_toggle','req_meta','req_sync','req_settled','request_decoded'}
    raw=set()
    for name,group in groups.items():
        clock=domains['compute'if name in compute else 'apb']
        for p in group:
            require(n.cells[p]['kind']=='DFFCE'and n.pin(p,'CLK')==clock,'APB FF kind/clock changed: '+p)
            require('PRESET'not in n.cells[p]['ports'],'APB unexpected preset: '+p)
            clear=n.pin(p,'CLEAR');reset_pins.append(p+'/CLEAR')
            if name in ('p_release','a_release'):raw.add(clear)
            else:
                release=groups['a_release'if name in compute else 'p_release'][2]
                proofs.append(prove(g,'APB local reset '+p,[clear,n.pin(release,'Q')],lambda v:v[0]==1-v[1]))
    require(len(raw)==1 and not(raw& (g.high|g.low)),'APB common reset missing/bypassed')
    for name in ['p_release','a_release']:
        group=groups[name]
        require(n.pin(group[0],'D')in g.high,'APB release seed changed')
        for i,p in enumerate(group):
            require(n.pin(p,'CE')in g.high,'APB release gated')
            if i:require(n.pin(p,'D')==n.pin(group[i-1],'Q'),'APB release bypass/reorder')
    for first,second,third,source in [('req_meta','req_sync','req_settled','request_toggle'),
                                     ('ack_meta','ack_sync','ack_settled','acknowledge_toggle')]:
        require(n.pin(reg(first),'D')==q(source)and n.pin(reg(second),'D')==q(first)and
                n.pin(reg(third),'D')==q(second),'APB synchronizer bypass/reorder')
        require(all(n.pin(reg(x),'CE')in g.high for x in [first,second,third]),'APB synchronizer gated')
        closures.append(exact_closure(g,[reg(first)],[reg(second)+'/D'],label=first))
    payloads=[]
    for label,source,capture,width in [('request','request_held','request_local',49),('response','response_held','response_local',33)]:
        src,dst=groups[source],groups[capture]
        require(len({n.pin(p,'CE')for p in dst})==1,'APB capture enable differs per bit: '+label)
        for p,z in zip(src,dst):require(n.pin(z,'D')==n.pin(p,'Q'),'APB held bit mapping changed: '+label)
        closure=exact_closure(g,src,[p+'/D'for p in dst],label=label)
        payloads.append(dict(id=label,width=width,source_registers=src,capture_registers=dst,
            capture_pins=[p+'/D'for p in dst],minimum_destination_edges=3 if label=='request'else 4,
            max_delay_ns=10,complete_closure=closure))
    request_ce=n.pin(groups['request_local'][0],'CE');response_ce=n.pin(groups['response_local'][0],'CE')
    proofs.append(prove(g,'request capture third settling edge',[request_ce,q('req_sync'),q('req_settled')],lambda v:v[0]==(v[1]^v[2])))
    state=[n.pin(p,'Q')for p in groups['state']]
    proofs.append(prove(g,'response capture WAIT after settled ACK',[response_ce,*state,q('ack_settled'),q('request_toggle')],
        lambda v:(v[1]and v[2])or v[0]==(v[1]and not v[2]and v[3]==v[4])))
    for held,toggle in [('request_held','request_toggle'),('response_held','acknowledge_toggle')]:
        require({n.pin(p,'CE')for p in groups[held]}=={n.pin(reg(toggle),'CE')},'APB held/toggle launch differs')
    proofs.append(prove(g,'request token toggles with payload',[n.pin(reg('request_toggle'),'D'),q('request_toggle')],lambda v:v[0]==1-v[1]))
    require(n.pin(reg('acknowledge_toggle'),'D')==q('req_settled'),'APB ACK identity source changed')
    proofs.append(prove(g,'command waits for decoded settled request',
        [n.canonical(A,'command_valid'),n.pin(groups['a_release'][2],'Q'),q('request_decoded'),q('req_settled'),q('acknowledge_toggle')],
        lambda v:v[0]==(v[1]and v[2]and v[3]!=v[4])))
    return dict(payload_groups=payloads,synchronizer_closures=closures,Boolean_contracts=proofs,
        register_count=len(actual),reset_pins=reset_pins,local_reset_bypass_rejected=True,
        physical_recovery_removal_verified=False,physical_payload_flight_verified=False)

def audit_synthesis(root,stage,evidence):
    stage=Path(stage);before=verify_synthesis_identity(stage,evidence)
    prep=prepared(root,stage);text=(stage/VG_RELATIVE).read_text();n=PcmNetlist(text,TOP);g=Graph(n)
    # These are actual composition boundaries; do not infer an endpoint clock
    # from the endpoint being checked. Missing child instances fail naturally.
    domains=dict(apb=n.canonical(A,'pclk'),compute=n.canonical(A,'audio_clk'),
        selected=n.pin('u_managed/runtime/clocks/selector','CLKOUT'))
    require(len(set(domains.values()))==3,'reviewed independent clock domains collapsed')
    result=dict(schema=1,policy=POLICY,source_and_prepare=prep,synthesis=before,
        actual_VG_APB=audit_apb(n,g,domains),domains=domains,
        HCI_actual_endpoints_verified=False,serializer_hold_actual_endpoints_verified=False,
        synchronous_RAM_inventory_verified=False,physical_CDC_accepted=False,
        routed_propagation_verified=False,release_ready=False)
    require(before==verify_synthesis_identity(stage,evidence),'synthesis identity changed during audit')
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--stage',type=Path,required=True);p.add_argument('--synthesis-evidence',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=audit_synthesis(a.root,a.stage,a.synthesis_evidence)if a.synthesis_evidence else prepared(a.root,a.stage)
    require(not a.output.exists(),'output evidence must be new');a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n');print('PASS '+POLICY+' '+('actual VG partial scope'if a.synthesis_evidence else'source/prepare only')+'; physical acceptance false')
if __name__=='__main__':main()
