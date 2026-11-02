"""Actual DIRECT physical-tail mailboxes; no source, SDC or board mutations.

This local gate proves reset-inclusive request stability, serial capture and
reply retirement against the retained VG.  Compute business consumers, Gray
arithmetic, physical recovery/removal and routed timing remain separate gates.
"""
import bisect
import fnmatch
import hashlib
from pathlib import Path
import re

from tools.workstation_recording_phase1_cdc import complete_closure
from tools.workstation_runtime_pcm_cdc import BooleanDiagram, Graph
from tools.workstation_task3_root_reset_audit import POLICY as ROOT_POLICY, validate_root_publisher

POLICY = 'task3-direct-tf-tail-local-cdc-v1'
SCOPE = 'u_managed/runtime/g_direct_tf.tail'
SOURCE = 'rtl/tf_audio/workstation_tf_physical_tail_v1.sv'
SOURCE_SHA256 = '6411af9cc250391eae6303c952c828376c34f63c5e4bef04a50ec6ca059d3eed'


def require(ok, message):
    if not ok:
        raise ValueError('task3 TF tail CDC audit: ' + message)


def audit_tf_tail_cdc(n, *, root, stage):
    g, s = Graph(n), SCOPE
    require(root.get('policy') == ROOT_POLICY and root.get('all_state_assignments_proven') is True,
            'actual root startup proof required')
    rq = root['root_q']
    validate_root_publisher(n, g, root)
    require(n.frames.get(s, {}).get('kind') == 'workstation_tf_physical_tail_v1',
            'actual physical tail hierarchy missing')
    source_hash=hashlib.sha256((Path(stage)/SOURCE).read_bytes()).hexdigest()
    require(source_hash==SOURCE_SHA256,'reviewed staged tail source identity changed')
    q = lambda p: n.pin(p, 'Q')
    groups = {name: g.group(s, name, width) for name, width in (
        ('held_request', 162), ('serial_token', 162), ('held_reply', 229),
        ('fence_gray', 32), ('fence_meta', 32), ('fence_sync', 32),
        ('request_sync', 2), ('reply_sync', 2), ('serial_state', 2))}
    scalar = {name: g.register(s, name) for name in (
        'request_toggle', 'reply_toggle', 'reply_consumed', 'serial_request_seen',
        'serial_context_valid', 'serial_rate', 'serial_frame_error')}
    scalar.update({name: g.register(s, name) for name in (
        'arm_pending', 'armed_o', 'failed_o', 'tail_receipted')})
    baseline = g.group(s, 'baseline_drops_o', 32)
    common = n.pin(scalar['request_toggle'], 'CLEAR')
    bd = BooleanDiagram([rq])
    require(g.support(common) == {rq} and bd.net(g, common) == bd.invert(bd.inputs[rq]),
            'common CLEAR is not exact inverse real root')
    rows = []

    def ff(path, clock):
        c = n.cells[path]
        require(c['kind'] == 'DFFCE' and set(c['ports']) == {'Q','D','CLK','CE','CLEAR'}
                and c['parameters'].get('INIT', "1'b0") == "1'b0"
                and n.pin(path,'CLK') == clock and n.pin(path,'CLEAR') == common,
                'FF primitive/INIT/clock/common CLEAR changed: ' + path)
        rows.append(dict(register=path, clock=clock, primitive=c['kind'],
                         effective_init=0, common_clear=common))

    for name, regs in groups.items():
        clock = 'audio_clk' if name in ('held_request','reply_sync','fence_gray') else 'dac_mclk_d'
        for p in regs:
            ff(p, clock)
    for name,p in scalar.items():
        ff(p, 'audio_clk' if name in ('request_toggle','reply_consumed','arm_pending',
                                    'armed_o','failed_o','tail_receipted') else 'dac_mclk_d')
    for p in baseline:
        ff(p,'audio_clk')

    # Reviewed optimizer boundary inputs are explicit symbolic cuts. Their
    # upstream policy is not inferred or silently accepted by this local gate.
    kind = n.frames[s]['kind']
    external = set()
    for port in n.frames[s]['ports']:
        if n.directions[kind].get(port) != 'input':
            continue
        bounds = n.ranges[kind].get(port)
        bits = [port] if bounds is None else [port+'['+str(i)+']' for i in range(min(bounds),max(bounds)+1)]
        external.update(n.canonical(s, bit) for bit in bits)
    proofs = []

    def proof(path, inputs, expected, contract, *, actual_cuts=()):
        leaves = sorted((set(inputs) | {rq,q(path)}) - g.high - g.low)
        b = BooleanDiagram(leaves)
        actual = b.choose(b.net(g,n.pin(path,'CLEAR')),0,
                    b.choose(b.net(g,n.pin(path,'CE')),b.net(g,n.pin(path,'D')),b.inputs[q(path)]))
        require(actual == expected(b), 'reset-inclusive next-Q changed: '+path)
        row = dict(register=path, contract=contract, named_inputs=leaves,
                   exhaustive_assignments=1 << len(leaves), bdd_nodes=len(b.nodes),
                   reset_inclusive_next_q_exact=True, input_cuts=list(actual_cuts))
        proofs.append(row)
        return row

    closures = {}
    request, token, reply = (groups[k] for k in ('held_request','serial_token','held_reply'))
    for name, regs in (('held_request',request),('held_reply',reply),('fence_gray',groups['fence_gray'])):
        closure = complete_closure(n,g,regs)
        require(not closure['primitive_endpoints'] and not closure['top_output_endpoints'],
                'held/Gray bus has opaque or top-output consumer: '+name)
        closures[name] = closure
    require(closures['held_request']['ff_endpoints'] == {
        **{p+'/D':'audio_clk' for p in request}, **{p+'/D':'dac_mclk_d' for p in token}},
        'held request complete source/self/capture closure changed')
    reply_remote = {**{p+'/D':'audio_clk' for p in baseline},
                    **{p+'/CE':'audio_clk' for p in baseline},
                    **{scalar[k]+'/CE':'audio_clk' for k in ('arm_pending','armed_o','failed_o','tail_receipted')}}
    require(closures['held_reply']['ff_endpoints'] == {
        **{p+'/D':'dac_mclk_d' for p in reply}, **reply_remote},
        'held reply complete source/self/compute D+CE closure changed')
    remote_gray = {pin:clock for pin,clock in closures['fence_gray']['ff_endpoints'].items()
                   if clock != 'audio_clk'}
    require(remote_gray == {p+'/D':'dac_mclk_d' for p in groups['fence_meta']},
            'cancellation Gray has extra/missing remote consumer')

    chains = []
    for name, producer, sync, clock in (
        ('request',scalar['request_toggle'],groups['request_sync'],'dac_mclk_d'),
        ('reply',scalar['reply_toggle'],groups['reply_sync'],'audio_clk')):
        first, second = sync
        require(all(n.pin(p,'CE') in g.high for p in sync)
                and n.pin(first,'D') == q(producer) and n.pin(second,'D') == q(first),
                'synchronizer exact direct D/CE mapping changed: '+name)
        closure = complete_closure(n,g,[first])
        require(closure['ff_endpoints'] == {second+'/D':clock}
                and not closure['primitive_endpoints'] and not closure['top_output_endpoints'],
                'first synchronizer has extra consumer: '+name)
        pc = complete_closure(n,g,[producer])
        origin = 'audio_clk' if name == 'request' else 'dac_mclk_d'
        require({p:c for p,c in pc['ff_endpoints'].items() if c != origin} == {first+'/D':clock}
                and not pc['primitive_endpoints'] and not pc['top_output_endpoints'],
                'toggle has extra remote/opaque/top consumer: '+name)
        for path,upstream in ((first,producer),(second,first)):
            proof(path,[q(upstream)],lambda b,u=upstream:b.both(b.inputs[rq],b.inputs[q(u)]),
                  'root & exact preceding/source Q')
        chains.append(dict(id=name,source=producer+'/Q',first=first+'/D',second=second+'/D',
                           first_consumer_closure=closure,producer_complete_closure=pc))
    for bit,(first,second,producer) in enumerate(zip(groups['fence_meta'],groups['fence_sync'],groups['fence_gray'])):
        require(n.pin(first,'D') == q(producer) and n.pin(second,'D') == q(first)
                and n.pin(first,'CE') in g.high and n.pin(second,'CE') in g.high,
                'fence Gray exact direct bit/CE mapping changed')
        closure=complete_closure(n,g,[first])
        require(closure['ff_endpoints']=={second+'/D':'dac_mclk_d'}
                and not closure['primitive_endpoints'] and not closure['top_output_endpoints'],
                'fence meta has extra consumer')
        for path,upstream in ((first,producer),(second,first)):
            proof(path,[q(upstream)],lambda b,u=upstream:b.both(b.inputs[rq],b.inputs[q(u)]),
                  'root & exact preceding Gray bit Q')

    # Actual source CE can include upstream combinational arithmetic; stop only
    # at declared module inputs. No data cut is used to assume mailbox hold.
    toggle=scalar['request_toggle']; ce=n.pin(toggle,'CE')
    support=g.support(ce,cuts=external)
    request_q=q(toggle); reply_sync1=q(groups['reply_sync'][1])
    require(request_q in support and reply_sync1 in support,
            'request source acceptance no longer checks both busy operands')
    b=BooleanDiagram(sorted(support | {request_q,reply_sync1}))
    commit=b.net(g,ce)
    require(b.both(commit,b.different(b.inputs[request_q],b.inputs[reply_sync1]))==0,
            'request source can commit while mailbox busy')
    proof(toggle,support,
          lambda b:b.both(b.inputs[rq],b.different(b.inputs[request_q],b.net(g,ce))),
          'root & (request XOR actual accepted commit); commit implies !busy',actual_cuts=external & support)
    for p in request:
        leaves=g.support(n.pin(p,'D'),cuts=external) | g.support(n.pin(p,'CE'),cuts=external) | support
        b=BooleanDiagram(sorted((leaves | {rq,q(p),request_q,reply_sync1}) - g.high - g.low))
        nextq=b.choose(b.net(g,n.pin(p,'CE')),b.net(g,n.pin(p,'D')),b.inputs[q(p)])
        require(b.both(b.invert(b.net(g,ce)),b.different(nextq,b.inputs[q(p)]))==0,
                'held request changes outside exact request-toggle commit: '+p)
        require(b.both(b.different(b.inputs[request_q],b.inputs[reply_sync1]),
                       b.different(nextq,b.inputs[q(p)]))==0,
                'held request changes while mailbox busy: '+p)
        proofs.append(dict(register=p,contract='root clear; actual next-Q holds unless exact request-toggle commit',
                           named_inputs=sorted(b.inputs),exhaustive_assignments=1<<len(b.inputs),
                           bdd_nodes=len(b.nodes),reset_checked_by_exact_common_CLEAR=True,
                           no_overwrite_without_toggle_proven=True,busy_no_overwrite_proven=True,
                           source_data_value_semantics_proven=False))

    # Receiver consumes the payload only at IDLE and a synchronized new request.
    st=[q(p) for p in groups['serial_state']]
    request_sync1=q(groups['request_sync'][1]); reply_q=q(scalar['reply_toggle'])
    control=[*st,request_sync1,reply_q]
    def capture(b):
        return b.all([b.invert(b.inputs[st[0]]),b.invert(b.inputs[st[1]]),
                      b.different(b.inputs[request_sync1],b.inputs[reply_q])])
    for bit,p in enumerate(token):
        require(n.pin(p,'D')==q(request[bit]), 'serial token bit mapping changed')
        b=BooleanDiagram(control)
        require(b.net(g,n.pin(p,'CE'))==capture(b),'serial token capture CE changed')
        proof(p,[*control,q(request[bit])],
              lambda b,p=p,bit=bit:b.both(b.inputs[rq],b.choose(capture(b),b.inputs[q(request[bit])],b.inputs[q(p)])),
              'root & choose(IDLE && reqsync1!=reply, matching held request bit, token Q)')
    seen=scalar['serial_request_seen']
    proof(seen,control,
          lambda b:b.both(b.inputs[rq],b.choose(capture(b),b.inputs[request_sync1],b.inputs[q(seen)])),
          'root & choose(exact token capture event, reqsync1, seen)')
    consumed=scalar['reply_consumed']; sync1=q(groups['reply_sync'][1])
    proof(consumed,[sync1],lambda b:b.both(b.inputs[rq],b.inputs[sync1]),
          'root & replysync1 (CE inequality form is next-Q equivalent)')

    return dict(policy=POLICY,scope=s,root_register=root['root_register'],root_q=rq,
                source_sha256={SOURCE:source_hash},
                common_clear=common,registers=rows,register_count=len(rows),
                exact_source_self_remote_closure=closures,
                held_request_source_pins=[p+'/Q' for p in request],
                held_request_capture_pins=[p+'/D' for p in token],
                held_reply_source_pins=[p+'/Q' for p in reply],
                held_reply_compute_capture_pins=sorted(reply_remote),
                cancellation_gray_source_pins=[p+'/Q' for p in groups['fence_gray']],
                cancellation_gray_capture_pins=[p+'/D' for p in groups['fence_meta']],
                cancellation_gray_second_pins=[p+'/D' for p in groups['fence_sync']],
                chains=chains,next_q=proofs,request_commit_ce=ce,
                request_no_overwrite_without_toggle_proven=True,request_busy_no_overwrite_proven=True,
                serial_capture_no_earlier_than_receiving_edge=3,
                external_interface_inputs_explicit_cuts=True,source_request_data_semantics_proven=False,
                reply_retirement_next_q_proven=False,compute_reply_business_next_q_proven=False,
                cancellation_gray_arithmetic_proven=False,sequence_physical_semantics_proven=False,
                full_tf_cdc_proven=False,routed_timing_verified=False,
                physical_recovery_removal_verified=False,hardware_tested=False,
                release_ready=False,deployment_allowed=False)


def validate_tf_tail_sdc(sdc,n,*,tail):
    """Reject exact missing CE pins, phantom targets and extra setup waivers."""
    require(tail.get('policy')==POLICY and tail.get('request_busy_no_overwrite_proven') is True,
            'actual local tail proof required')
    pins=sorted(p+'/'+port for p,c in n.cells.items() for port in c['ports'])
    def resolve(body,strict=True):
        result=set()
        for glob in body.split():
            prefix=glob[:next((i for i,c in enumerate(glob) if c in '*?['),len(glob))]
            a,b=bisect.bisect_left(pins,prefix),bisect.bisect_right(pins,prefix+'\U0010ffff')
            hits={p for p in pins[a:b] if fnmatch.fnmatchcase(p,glob)}
            require(hits or not strict,'SDC query has no actual pins: '+glob)
            result.update(hits)
        return result
    def pair(line):
        queries=re.findall(r'\[get_pins \{([^}]+)\}\]',line)
        require(len(queries)==2 and 'get_clocks' not in line and 'get_regs' not in line,
                'exact pin-to-pin SDC shape required')
        return [resolve(q) for q in queries]
    records=[]; allowed=set(); finite=set(); protected=set(); firsts=set()
    def exact(marker,source,target,budget,hold=False):
        selected=[l for l in sdc.splitlines() if marker in l.split(' -to ',1)[0] and
                  l.startswith(('set_max_delay ','set_false_path ')) and '-from ' in l]
        prefixes=[f'set_max_delay {budget:.3f} ']+(['set_false_path -hold '] if hold else [])
        require(len(selected)==len(prefixes),'missing/duplicate finite SDC row: '+marker)
        for prefix in prefixes:
            matches=[l for l in selected if l.startswith(prefix)]
            require(len(matches)==1,'finite/hold command changed: '+marker)
            line=matches[0];actual=pair(line)
            require(actual==[set(source),set(target)],'complete SDC source/target inventory changed: '+marker)
            (allowed if prefix.startswith('set_false_path') else finite).add(line)
            records.append(dict(constraint=line,source_pins=sorted(source),capture_pins=sorted(target)))
        protected.update(target)
    for name,budget in (('held_request',20.000),('held_reply',13.020),('cancellation_gray',13.020)):
        source=tail[name+'_source_pins']
        target=tail[name+('_compute_capture_pins' if name=='held_reply' else '_capture_pins')]
        exact(source[0].rsplit('_',2)[0] if name!='cancellation_gray' else SCOPE+'/fence_gray_',source,target,budget,hold=True)
    for row in tail['chains']:
        source,first,second=row['source'],row['first'],row['second']
        marker=first.rsplit('_s',1)[0]+'_s*/D'
        selected=[l for l in sdc.splitlines() if marker in l and l.startswith('set_false_path ')]
        require(len(selected)==1 and selected[0].startswith('set_false_path -from ')
                and pair(selected[0])==[{source},{first}], 'exact producer-to-first synchronizer cut changed')
        allowed.add(selected[0]);firsts.add(first)
        exact(first.rsplit('/',1)[0].rsplit('_s',1)[0]+'_s*/Q',[first.rsplit('/',1)[0]+'/Q'],[second],2.000)
    meta=[p.rsplit('/',1)[0]+'/Q' for p in tail['cancellation_gray_capture_pins']]
    exact(SCOPE+'/fence_meta_',meta,tail['cancellation_gray_second_pins'],2.000)
    for line in sdc.splitlines():
        require(not line.startswith('set_clock_groups '),'unreviewed whole-clock group exception')
        if not line.startswith(('set_false_path ','set_max_delay ')):
            continue
        require('-through ' not in line,'unreviewed through exception')
        if line.startswith('set_false_path') and 'get_clocks' in line:
            from tools.workstation_runtime_cdc import MODE_EXCLUSIONS
            require(line in MODE_EXCLUSIONS,'unreviewed whole-clock false path')
        if line.startswith('set_false_path') and '-to ' not in line:
            protected_sources=set(tail['held_request_source_pins']+tail['held_reply_source_pins']+
                                  tail['cancellation_gray_source_pins'])
            for kind,body in re.findall(r'-from\s+\[(get_pins|get_regs)\s+\{([^}]+)\}\]',line):
                sources=resolve(body,strict=False) if kind=='get_pins' else {
                    p for p in pins if any(fnmatch.fnmatchcase(p.rsplit('/',1)[0],a) for a in body.split())}
                require(not (sources&protected_sources),
                        'source-only setup cut reaches a held/Gray producer')
        for kind,body in re.findall(r'-to\s+\[(get_pins|get_regs)\s+\{([^}]+)\}\]',line):
            targets=resolve(body,strict=False) if kind=='get_pins' else {p for p in pins if any(fnmatch.fnmatchcase(p.rsplit('/',1)[0],a) for a in body.split())}
            if targets & protected:
                require(line in allowed|finite,'later tail endpoint has unreviewed extra setup cut/bound')
    return dict(policy=POLICY+'-exact-sdc',installed_constraints=records,
                exact_held_reply_D_and_CE_pin_count=68,exact_source_target_queries=True,
                full_tf_cdc_proven=False,routed_timing_verified=False,hardware_tested=False)
