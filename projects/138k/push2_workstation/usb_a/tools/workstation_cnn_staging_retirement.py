"""Opt-in native CNN staging retirement for the task3 W preboard profile.

The owner implementation is versioned RTL. This temporary adapter only wires
that boundary into the unchanged task service; exact input identity, anchors
and inverse are checked. Retire the adapter by passing an explicit native
option after the complete paired regression and physical checks pass.
"""
from pathlib import Path
import hashlib

KEY = 'cnn_staging_retirement_policy'
POLICY = 'task3_W_registered_native_staging_retirement_v1'
SOURCE = 'rtl/music/workstation_cnn_task_service.sv'
HELPER = 'rtl/music/workstation_cnn_staging_retirement.sv'
TOOL = 'tools/workstation_cnn_staging_retirement.py'
PARENT_SHA256 = 'dedb3c023610af36100804fc4ea864c9d08ed4b2dfdfa156bffd3b53e16d2cde'
EDITS = (
    ('    reg completion_overflow;',
     '    wire retired_completion_valid,staging_retire_busy,staging_retire_fault;\n'
     '    wire [256:0] retired_completion_data;\n'
     '    reg completion_overflow;'),
    ('else if((completion_write || staging_response) && !completion_source_ready)completion_overflow<=1;',
     'else if(staging_retire_fault || ((completion_write || staging_response) && !completion_source_ready))completion_overflow<=1;'),
    ('.write_valid_i(completion_write || staging_response)',
     '.write_valid_i(retired_completion_valid)'),
    ('.write_data_i({completion_write,memory_read_data_i})',
     '.write_data_i(retired_completion_data)'),
    ('    assign request_ready=staging_native_ready;',
     '    workstation_cnn_staging_retirement staging_retirement(\n'
     '        .clk_i(memory_clk_i),.reset_ni(native_reset_n),\n'
     '        .commit_i(staging_native_ready),.write_i(request_data[317]),\n'
     '        .response_i(staging_response),.response_data_i(memory_read_data_i),\n'
     '        .completion_ready_i(completion_source_ready),.request_retire_o(request_ready),\n'
     '        .completion_valid_o(retired_completion_valid),.completion_data_o(retired_completion_data),\n'
     '        .busy_o(staging_retire_busy),.fault_o(staging_retire_fault));'),
    ('.stage_valid_i(request_valid && completion_source_ready)',
     '.stage_valid_i(request_valid && completion_source_ready && !staging_retire_busy)'),
)


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError('CNN staging retirement: ' + message)


def configured(configuration):
    value = configuration.get(KEY)
    require(value in (None, POLICY), 'unknown policy')
    if value:
        require(configuration.get('demo_role') == 'W' and
                configuration.get('cnn_reset_policy') ==
                'task3_w_CNN_control_native_reset_release3_v1',
                'requires locally released W CNN domains')
    return bool(value)


def adapt(text):
    require(digest(text) == PARENT_SHA256, 'parent source drift')
    for before, after in EDITS:
        require(text.count(before) == 1, 'forward anchor drift')
        text = text.replace(before, after, 1)
    return text


def restore(text):
    if 'workstation_cnn_staging_retirement staging_retirement(' not in text:
        return text
    for before, after in reversed(EDITS):
        require(text.count(after) == 1, 'inverse anchor drift')
        text = text.replace(after, before, 1)
    require(digest(text) == PARENT_SHA256, 'inverse parent drift')
    return text


def select(stage, configuration):
    if not configured(configuration):
        return None
    path = Path(stage) / SOURCE
    path.write_text(adapt(path.read_text()))
    return evidence(stage, configuration)


def evidence(stage, configuration):
    if not configured(configuration):
        return None
    text = (Path(stage) / SOURCE).read_text()
    parent = restore(text)
    require(text == adapt(parent), 'selection absent or changed')
    helper = Path(stage) / HELPER
    native = Path(__file__).resolve().parents[1] / HELPER
    require(helper.read_bytes() == native.read_bytes(), 'native boundary drift')
    return dict(policy=POLICY, parent_sha256=PARENT_SHA256,
                selected_sha256=digest(text), helper_sha256=digest(helper.read_text()),
                native_commit_edge_unchanged=True, fifo_retirement_delay_cycles=1,
                completion_delay_min_cycles=1, audio_sample_schedule_unchanged=True,
                mapped_verification_required=True, routed_timing_verified=False,
                hardware_tested=False)


def audit(n, scope='u_task3_media/cnn_stream/task_service/staging_retirement'):
    """Exact mapped next-Q over arbitrary inputs at the native boundary.

    Only the module's incoming event/data/reset ports are cuts. No internal
    decision or state is assumed. The complete async-FIFO/broker scoreboard
    and real CNN regression separately validate integration and event order.
    """
    from tools.workstation_task3_w_consumer_nextq import Circuit, Expressions, sat_compare
    from tools.workstation_runtime_pcm_cdc import Graph
    e=Expressions()
    c=Circuit(n,e)
    g=Graph(n)
    reg=lambda stem:c.state[(scope+'/' if scope else '')+stem]
    q=lambda path:c.net(n.pin(path,'Q'))
    controls={}
    mapped=bool(scope and 'commit_i' not in n.frames[scope]['ports'])
    def cut(stem):
        net=n.canonical(scope,stem)
        value=e.node('state','port/'+stem)
        c.memo[net]=value
        return value
    both=lambda x,y:e.choose(x,y,0)
    either=lambda x,y:e.choose(x,1,y)
    if mapped:
        # Gowin moves the broker response qualification and FIFO full
        # comparison into this module. Its real incoming ports are the cuts;
        # the moved logic is expanded on both sides of every state equation.
        require(set(n.frames[scope]['ports'])=={
            'completion_write','memory_clk','n1191_6','staging_native_ready',
            'write_fire','stage_owner','n949_4','n1195_6','client_rdata',
            'write_gray','read_gray_sync','staging_retire_fault',
            'request_ready','retired_completion_valid','retired_completion_data'},
            'expanded boundary port inventory changed')
        controls['commit_i']=cut('staging_native_ready')
        write=cut('completion_write')
        controls['response_i']=both(cut('stage_owner'),cut('n949_4'))
        w,r,upper=map(cut,('write_gray[0]','read_gray_sync[0]','n1195_6'))
        controls['completion_ready_i']=e.invert(both(upper,e.invert(e.xor(w,r))))
    else:
        for stem in ('commit_i','write_i','response_i','completion_ready_i'):
            controls[stem]=cut(stem)
        write=both(controls['commit_i'],controls['write_i'])
    data=[]
    for bit in range(256):
        net=n.canonical(scope,('client_rdata' if mapped else 'response_data_i')+'['+str(bit)+']')
        value=e.node('state','port/response_data_i/'+str(bit))
        c.memo[net]=value
        data.append(value)
    req=reg('request_retire_o')
    valid=reg('completion_valid_o')
    fault=reg('fault_o')
    payload=[reg('completion_data_o_'+str(bit)) for bit in range(257)]
    clear=n.pin(req,'CLEAR')
    c.memo[clear]=e.node('state','port/reset_asserted')
    reset=c.memo[clear]
    require(all(n.cells[p]['kind']=='DFFCE' and n.pin(p,'CLEAR')==clear and
                n.pin(p,'CLK')==n.pin(req,'CLK') for p in [req,valid,fault,*payload]),
            'local reset/clock or FF kind changed')
    a=controls
    event=either(write,a['response_i'])
    collision=either(both(write,a['response_i']),
                     both(q(valid),e.invert(a['completion_ready_i'])))
    capture=both(event,e.invert(collision))
    expected_valid=e.choose(capture,1,
        e.choose(both(q(valid),a['completion_ready_i']),0,q(valid)))
    expected_fault=either(q(fault),both(event,collision))
    expected=[('request_retire',req,a['commit_i']),
              ('completion_valid',valid,expected_valid),('fault',fault,expected_fault)]
    expected += [('payload_'+str(bit),p,e.choose(capture,v,q(p)))
                 for bit,(p,v) in enumerate(zip(payload,[*data,write]))]
    proofs=[]
    for label,p,value in expected:
        actual,_,_=c.next_q(p)
        proof=sat_compare(e,actual,e.choose(reset,0,value))
        proofs.append(dict(register=p,meaning=label,**proof))
    return dict(policy=POLICY,scope=scope,exact_next_Q_equations=len(proofs),
                incoming_event_and_data_bits=263 if mapped else 260,
                expanded_broker_response_and_FIFO_full=mapped,
                arbitrary_inputs_and_old_state=True,
                no_internal_combinational_cuts=True,proofs=proofs,
                hardware_tested=False,routed_timing_verified=False)
