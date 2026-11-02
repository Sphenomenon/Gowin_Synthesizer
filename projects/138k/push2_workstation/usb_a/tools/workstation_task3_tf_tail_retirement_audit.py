"""Actual serial tail retirement/sequence comparison and reply next-Q proof.

Seven exact 32-bit NE carry chains are classified by their real operand pairs
before being used as Boolean summaries. Raw physical completion/drop values
are explicit declared module inputs, not invented original formal names or
arbitrary data-expression cuts. This is a local serial proof, not full TF CDC.
"""
from pathlib import Path
import hashlib
import xml.etree.ElementTree as ET

from tools.workstation_runtime_pcm_cdc import BooleanDiagram, Graph
from tools.workstation_task3_root_reset_audit import POLICY as ROOT_POLICY, validate_root_publisher

POLICY='task3-direct-tf-tail-serial-retirement-v1'
SCOPE='u_managed/runtime/g_direct_tf.tail'
SOURCE='rtl/tf_audio/workstation_tf_physical_tail_v1.sv'
SOURCE_SHA256='6411af9cc250391eae6303c952c828376c34f63c5e4bef04a50ec6ca059d3eed'


def require(condition,message):
    if not condition:
        raise ValueError('task3 TF tail retirement audit: '+message)


def audit_tf_tail_retirement(n, *, root, stage):
    s=SCOPE
    require(root.get('policy')==ROOT_POLICY and root.get('all_state_assignments_proven') is True,
            'verified actual root startup proof required')
    require(n.frames.get(s,{}).get('kind')=='workstation_tf_physical_tail_v1',
            'actual serial tail hierarchy missing')
    g=Graph(n)
    root_register=g.register('u_reset','started')
    rq=n.pin(root_register,'Q')
    validate_root_publisher(n, g, root)
    selected=[row.get('path') for row in ET.parse(Path(stage)/'Prj1.gprj').find('FileList')
              if row.get('enable')=='1']
    require(selected.count(SOURCE)==1,'reviewed serial-retirement source is not uniquely selected')
    source_hash=hashlib.sha256((Path(stage)/SOURCE).read_bytes()).hexdigest()
    require(source_hash==SOURCE_SHA256,'reviewed staged serial-retirement source changed')
    kind=n.frames[s]['kind']
    declared={}
    for port in n.frames[s]['ports']:
        if n.directions[kind].get(port)!='input':continue
        bounds=n.ranges[kind].get(port)
        bits=[port] if bounds is None else [port+'['+str(bit)+']'
                for bit in range(min(bounds),max(bounds)+1)]
        declared[port]=[n.canonical(s,bit) for bit in bits]

    def boundary(name,width=1):
        require(name in declared and len(declared[name])==width and
                len(set(declared[name]))==width,'actual declared input boundary changed: '+name)
        return declared[name]

    physical_epoch=boundary('physical_frame_epoch',32)
    physical_sequence=boundary('physical_frame_sequence',32)
    drops=boundary('observation_source_drop',32)
    physical_valid=boundary('physical_frame_valid')[0]
    physical_rate=boundary('physical_frame44')[0]
    physical_error=boundary('physical_frame_error')[0]
    groups={stem:g.group(s,stem,width) for stem,width in (
        ('serial_token',162),('held_reply',229),('serial_state',2),
        ('serial_generation',32),('serial_session',32),('serial_epoch',32),
        ('serial_fence',32),('serial_baseline',32),('fence_sync',32),('request_sync',2))}
    scalar={stem:g.register(s,stem) for stem in ('reply_toggle','serial_request_seen',
        'serial_context_valid','serial_rate','serial_frame_error')}
    q=lambda path:n.pin(path,'Q')
    token=[q(p) for p in groups['serial_token']]
    state=[q(p) for p in groups['serial_state']]
    common=n.pin(scalar['reply_toggle'],'CLEAR')
    bd=BooleanDiagram([rq])
    require(g.support(common)=={rq} and bd.net(g,common)==bd.invert(bd.inputs[rq]),
            'serial common CLEAR is not exact inverse actual root')
    checked=[]
    for path in [p for regs in groups.values() for p in regs]+list(scalar.values()):
        cell=n.cells[path]
        require(cell['kind']=='DFFCE' and set(cell['ports'])=={'Q','D','CLK','CE','CLEAR'}
                and cell['parameters'].get('INIT',"1'b0")=="1'b0"
                and n.pin(path,'CLK')=='dac_mclk_d' and n.pin(path,'CLEAR')==common,
                'serial FF primitive/INIT/clock/root CLEAR changed: '+path)
        checked.append(dict(register=path,primitive='DFFCE',effective_init=0,
            **{pin.lower():n.pin(path,pin) for pin in ('Q','D','CLK','CE','CLEAR')}))
    specs={
        'context-generation':(token[128:160],[q(p) for p in groups['serial_generation']]),
        'context-session':(token[96:128],[q(p) for p in groups['serial_session']]),
        'context-epoch':(token[64:96],[q(p) for p in groups['serial_epoch']]),
        'context-fence':(token[:32],[q(p) for p in groups['serial_fence']]),
        'cancel-fence':(token[:32],[q(p) for p in groups['fence_sync']]),
        'physical-epoch':(token[64:96],physical_epoch),
        'physical-sequence':(token[32:64],physical_sequence),
    }
    expected={name:{frozenset(pair) for pair in zip(*operands)} for name,operands in specs.items()}
    require(all(len(pairs)==32 and all(len(pair)==2 for pair in pairs) for pairs in expected.values()),
            'comparison operand inventory aliases or loses a bit')
    frontier=set().union(*(g.carry_frontier(n.pin(path,pin)) for path,pin in (
        (scalar['reply_toggle'],'CE'),(groups['serial_state'][0],'D'),(groups['serial_state'][1],'D'))))
    require(len(frontier)==7,'serial state/retire comparator frontier is not exact seven comparisons')
    comparisons,compare_nets={},{}
    for net in sorted(frontier):
        pairs=g.inequality_chain(net)
        names=[name for name,required in expected.items() if pairs==required]
        require(len(names)==1 and names[0] not in compare_nets,
                'unknown/duplicate/missing 32-bit serial comparison: '+net)
        name=names[0];compare_nets[name]=net
        comparisons[name]=dict(output=net,width=32,exact_NE_chain_verified=True,
            operand_pairs=sorted(sorted(pair) for pair in pairs),
            primitive_model='GW5A ALU_MODE=3 COUT=(I0!=I1)||CIN; zero/XOR seed')
    require(set(compare_nets)==set(specs),'serial comparison classification incomplete')
    context_valid=q(scalar['serial_context_valid']);serial_rate=q(scalar['serial_rate'])
    frame_error=q(scalar['serial_frame_error']);seen=q(scalar['serial_request_seen'])
    reply_q=q(scalar['reply_toggle']);request_sync1=q(groups['request_sync'][1])
    controls=[rq,*state,token[160],token[161],context_valid,serial_rate,frame_error,
        seen,reply_q,request_sync1,physical_valid,physical_rate,physical_error,*compare_nets.values()]
    require(len(controls)==len(set(controls)),'serial state/comparison/declared input sources alias')

    def ne(b,name):return b.inputs[compare_nets[name]]
    def terms(b):
        low,high=(b.inputs[bit] for bit in state)
        idle=b.all([b.invert(low),b.invert(high)])
        validate=b.both(low,b.invert(high));wait=b.both(b.invert(low),high);water=b.both(low,high)
        fence_bad=ne(b,'cancel-fence')
        good=b.all([b.inputs[context_valid],b.invert(b.different(b.inputs[token[160]],b.inputs[serial_rate])),
                    *(b.invert(ne(b,name)) for name in ('context-generation','context-session','context-epoch','context-fence'))])
        arm=b.all([validate,b.invert(fence_bad),b.invert(b.inputs[token[161]])])
        retire=b.either(water,b.either(b.both(wait,fence_bad),
            b.both(validate,b.either(fence_bad,b.either(b.invert(b.inputs[token[161]]),b.invert(good))))))
        match=b.all([b.inputs[physical_valid],b.invert(b.different(b.inputs[physical_rate],b.inputs[token[160]])),
                     b.invert(ne(b,'physical-epoch')),b.invert(ne(b,'physical-sequence'))])
        return dict(idle=idle,validate=validate,wait=wait,water=water,fence_bad=fence_bad,
                    context_good=good,arm=arm,retire=retire,physical_match=match)

    bd=BooleanDiagram(controls);retire_ce=n.pin(scalar['reply_toggle'],'CE')
    require(bd.net(g,retire_ce)==terms(bd)['retire'],
            'reply toggle CE is not exact source-reviewed retirement condition')
    require(n.pin(scalar['reply_toggle'],'D')==seen,'reply retirement D is not serial_request_seen Q')
    proofs=[]
    def prove(path,extra,predicate,contract,*,reply_hold=False):
        leaves=list(dict.fromkeys([*controls,*extra,q(path)]))
        b=BooleanDiagram(leaves)
        actual=b.choose(b.net(g,n.pin(path,'CLEAR')),0,
            b.choose(b.net(g,n.pin(path,'CE')),b.net(g,n.pin(path,'D')),b.inputs[q(path)]))
        require(actual==predicate(b),'reset-inclusive serial next-Q changed: '+path)
        row=dict(register=path,contract=contract,named_inputs=leaves,
            exhaustive_symbolic_assignments=1<<len(leaves),bdd_nodes=len(b.nodes),
            reset_before_enable=True,reset_inclusive_next_q_exact=True)
        if reply_hold:
            require(b.both(b.all([b.inputs[rq],b.invert(terms(b)['retire'])]),
                           b.different(actual,b.inputs[q(path)]))==0,
                    'held reply changes without retirement: '+path)
            row['no_overwrite_outside_retirement_or_root_clear_proven']=True
        proofs.append(row)

    prove(scalar['reply_toggle'],[],lambda b:b.both(b.inputs[rq],
        b.choose(terms(b)['retire'],b.inputs[seen],b.inputs[reply_q])),
        'root & choose(retire, captured request seen, reply toggle Q)')
    prove(groups['serial_state'][0],[],lambda b:b.both(b.inputs[rq],b.either(
        b.both(terms(b)['idle'],b.different(b.inputs[request_sync1],b.inputs[reply_q])),
        b.all([terms(b)['wait'],b.invert(terms(b)['fence_bad']),terms(b)['physical_match']]))),
        'IDLE->VALIDATE on new request; WAIT_FRAME->WATERMARK only on exact physical identity; retire->IDLE bit0')
    prove(groups['serial_state'][1],[],lambda b:b.both(b.inputs[rq],b.either(
        b.all([terms(b)['validate'],b.invert(terms(b)['fence_bad']),b.inputs[token[161]],terms(b)['context_good']]),
        b.both(terms(b)['wait'],b.invert(terms(b)['fence_bad'])))),
        'VALIDATE->WAIT_FRAME only for valid tail context; WAIT_FRAME holds unless cancelled; WATERMARK->IDLE bit1')
    prove(scalar['serial_frame_error'],[],lambda b:b.both(b.inputs[rq],b.choose(
        b.all([terms(b)['wait'],b.invert(terms(b)['fence_bad']),terms(b)['physical_match']]),
        b.inputs[physical_error],b.inputs[frame_error])),
        'root & choose(exact matched WAIT_FRAME completion, physical error input, latched frame error)')
    for bit,path in enumerate(groups['held_reply']):
        require(n.pin(path,'CE') in g.high,'actual held_reply CE is not VCC: '+path)
        extra=[]
        if bit>=67:
            value_net=token[bit-67];extra=[value_net]
            def value(b,net=value_net):return b.inputs[net]
            label='exact serial token bit %d'%(bit-67)
        elif bit==66:
            def value(b):
                t=terms(b);return b.all([t['validate'],b.invert(t['fence_bad']),b.inputs[token[161]],b.invert(t['context_good'])])
            label='BAD_CONTEXT status high bit'
        elif bit==65:
            def value(b):return terms(b)['fence_bad']
            label='CANCELLED status low bit'
        elif bit>=33:
            baseline=q(groups['serial_baseline'][bit-33]);drop=drops[bit-33];extra=[baseline,drop]
            def value(b,baseline=baseline,drop=drop):
                t=terms(b);return b.choose(t['validate'],b.both(t['arm'],b.inputs[drop]),b.inputs[baseline])
            label='arm baseline from real source counter; tail baseline from retained serial baseline'
        elif bit>=1:
            drop=drops[bit-1];extra=[drop]
            def value(b,drop=drop):
                t=terms(b);return b.choose(t['validate'],b.both(t['arm'],b.inputs[drop]),b.inputs[drop])
            label='arm/tail prefix from real source counter; failed validation zero'
        else:
            def value(b):
                t=terms(b);return b.choose(t['validate'],b.invert(t['arm']),
                    b.choose(t['wait'],1,b.either(t['fence_bad'],b.inputs[frame_error])))
            label='cancel/bad-context error or matched-frame latched physical error'
        prove(path,extra,lambda b,path=path,value=value:b.both(b.inputs[rq],
            b.choose(terms(b)['retire'],value(b),b.inputs[q(path)])),
            'root & choose(retire, '+label+', held reply Q)',reply_hold=True)
    require(len(proofs)==233,'reply/state/error next-Q proof inventory incomplete')
    return dict(policy=POLICY,scope=s,root_register=root_register,root_q=rq,
        source_sha256={SOURCE:source_hash},common_clear=common,
        actual_declared_input_cuts=declared,
        used_physical_input_cuts=dict(epoch=physical_epoch,sequence=physical_sequence,
            valid=physical_valid,rate=physical_rate,error=physical_error,source_drops=drops),
        comparisons=comparisons,comparison_count=7,comparison_operand_pairs=224,
        comparison_summaries_only_after_exact_operand_and_mode_proof=True,
        registers=checked,reply_retire_ce=retire_ce,next_q=proofs,
        proof_register_count=233,held_reply_next_q_bits=229,
        reply_retirement_next_q_proven=True,serial_state_two_bit_next_q_proven=True,
        physical_epoch_and_sequence_compare_proven=True,matched_frame_error_latch_next_q_proven=True,
        held_reply_no_overwrite_outside_retirement_or_root_clear=True,
        source_data_expression_cuts_used=False,
        serial_context_register_transition_logic_proven=False,
        token_capture_and_request_sync_owned_by_parent_gate=True,
        compute_reply_business_next_q_proven=False,cancellation_gray_arithmetic_proven=False,
        upstream_physical_and_observation_counter_authenticity_proven=False,
        full_tf_cdc_proven=False,physical_tail_hardware_semantics_accepted=False,
        routed_timing_verified=False,physical_recovery_removal_verified=False,
        hardware_tested=False,release_ready=False,deployment_allowed=False)
