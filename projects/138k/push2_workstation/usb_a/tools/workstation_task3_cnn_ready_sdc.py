"""Explicit W CNN readiness selector rebind; budgets and exceptions are fixed."""
import fnmatch
import hashlib

POLICY='task3_w_CNN_ready_backend_sync_rebind_v1'
SCOPE='u_task3_media/cnn_stream/task_service'
FIRST=SCOPE+'/backend_meta*'
STALE=SCOPE+'/cnn/model_memory_ready*'
FINAL=SCOPE+'/backend_sync*'
BEFORE='set_max_delay 2.000 -from [get_regs {'+FIRST+'}] -to [get_regs {'+STALE+'}]'
AFTER=BEFORE.replace(STALE,FINAL)


def require(ok,message):
    if not ok:raise ValueError('W CNN ready SDC: '+message)


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def project(sdc):
    require(sdc.splitlines().count(BEFORE)==1 and sdc.count(STALE)==1,
            'exact original second-stage selector absent/duplicated')
    require(FINAL not in sdc,'corrected selector already present')
    selected=sdc.replace(BEFORE,AFTER,1)
    return selected,dict(policy=POLICY,parent_sha256=digest(sdc),
        selected_sha256=digest(selected),before=BEFORE,after=AFTER,
        added_exceptions=0,timing_budgets_changed=False,
        mapped_binding_required=True,physical_CDC_accepted=False)


def restore(sdc,evidence):
    require(sdc.splitlines().count(AFTER)==1 and sdc.count(FINAL)==1 and STALE not in sdc,
            'exact selected second-stage selector absent/duplicated')
    parent=sdc.replace(AFTER,BEFORE,1)
    selected,expected=project(parent)
    require(selected==sdc and evidence==expected,'inverse evidence drift')
    return parent


def audit(n,sdc,*,stage):
    from tools.workstation_task3_cnn_reset import source_evidence
    from tools.workstation_runtime_pcm_cdc import Graph
    from tools.workstation_recording_phase1_cdc import complete_closure
    source=source_evidence(stage)
    require(sdc.splitlines().count(AFTER)==1 and STALE not in sdc,
            'installed SDC uses stale or changed readiness selector')
    g=Graph(n)
    first,last=(g.register(SCOPE,stem) for stem in ('backend_meta','backend_sync'))
    for pattern,p in ((FIRST,first),(FINAL,last)):
        require([x for x in g.regs if fnmatch.fnmatchcase(x,pattern)]==[p],
                'selector resolves missing/extra registers: '+pattern)
    for p in (first,last):
        c=n.cells[p]
        require(c['kind']=='DFFCE' and set(c['ports'])=={'D','Q','CLK','CE','CLEAR'} and
                c['parameters'].get('INIT',"1'b0")=="1'b0" and
                n.pin(p,'CLK')=='clk_50m' and n.pin(p,'CE') in g.high,
                'readiness primitive/INIT/clock/enable changed: '+p)
    require(n.pin(last,'D')==n.pin(first,'Q') and
            n.pin(last,'CLEAR')==n.pin(first,'CLEAR'),'second stage link/reset changed')
    native=n.pin(g.register(SCOPE,'g_domain_reset.native_release',2),'Q')
    control=n.pin(g.register(SCOPE,'g_domain_reset.control_release',2),'Q')
    ready=n.canonical(SCOPE,'ddr_client_ready')
    data=g.equivalent('ready first D is native release and actual DDR client readiness',
        [n.pin(first,'D'),native,ready],lambda v:v[0]==(v[1] and v[2]),cuts=(ready,))
    clear=g.equivalent('readiness CLEAR uses final control reset',
        [n.pin(first,'CLEAR'),control],lambda v:v[0]==(not v[1]))
    require(n.canonical(SCOPE+'/cnn','backend_sync')==n.pin(last,'Q') and
            n.canonical(SCOPE+'/cnn/u_basic_pitch','backend_sync')==n.pin(last,'Q'),
            'CNN ready input disconnected from final stage')
    require(not any(p.startswith(SCOPE+'/cnn/model_memory_ready_s') for p in n.cells),
            'historical second-stage register reappeared')
    closure=complete_closure(n,g,[first])
    require(closure['ff_endpoints']=={last+'/D':'clk_50m'} and
            not closure['primitive_endpoints'] and not closure['top_output_endpoints'],
            'first readiness stage has another consumer')
    return dict(policy=POLICY,source=source,first=first,last=last,first_D=data,
        assertion=clear,first_complete_closure=closure,
        final_complete_closure=complete_closure(n,g,[last]),
        max_delay_ns=2.000,selectors_resolve_exactly=True,
        complete_CDC_accepted=False,routed_timing_verified=False,hardware_tested=False)
