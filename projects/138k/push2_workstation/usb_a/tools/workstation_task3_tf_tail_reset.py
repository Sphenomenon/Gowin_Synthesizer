"""Select the native TF reset option; retain exact historical source inverses.

Only the parameter default is selected in staging. The runtime implementation
is maintained RTL. Retire this parameter adapter when a versioned provider can
select it without changing historical provider identities.
"""
from pathlib import Path
import hashlib
import json

POLICY = 'task3_m_TF_tail_existing_local_release_v1'
KEY = 'tf_tail_reset_policy'
PROFILE = 'custom138k-workstation-task3-m-paired-checkpoint-v19'
PROFILES = (PROFILE, 'custom138k-workstation-task3-m-paired-checkpoint-v20',
            'custom138k-workstation-task3-m-paired-checkpoint-v21', 'custom138k-workstation-task3-m-preboard-v1')
RUNTIME = 'rtl/workstation/workstation_runtime_audio.sv'
TAIL = 'rtl/tf_audio/workstation_tf_physical_tail_v1.sv'
TOOL = 'tools/workstation_task3_tf_tail_reset.py'
MANIFEST = 'rtl/tf_audio/workstation_tf_tail_local_reset_v1.adaptation.json'
MANIFEST_SHA256 = '78fc375b386e0023b768fa58fdc6e2f3a57f89e747417b96715a727053b90b42'
DEFAULT = 'parameter bit TF_TAIL_LOCAL_RESET_ENABLE=0'
SELECTED = 'parameter bit TF_TAIL_LOCAL_RESET_ENABLE=1'


def digest(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError('TF tail local reset: ' + message)


def records():
    path = Path(__file__).resolve().parents[1] / MANIFEST
    require(digest(path.read_bytes()) == MANIFEST_SHA256, 'adaptation bytes changed')
    data = json.loads(path.read_text())
    require(data.get('schema') == 1 and data.get('policy') == POLICY,
            'adaptation identity changed')
    return data['inputs']


def inverse(relative, text):
    row = records()[relative]
    if relative == RUNTIME and SELECTED in text:
        require(text.count(SELECTED) == 1 and DEFAULT not in text,
                'parameter selection changed')
        text = text.replace(SELECTED, DEFAULT, 1)
    require(digest(text) == row['native_sha256'], 'native source changed: ' + relative)
    for edit in reversed(row['edits']):
        require(text.count(edit['after']) == 1, 'inverse anchor changed: ' + relative)
        text = text.replace(edit['after'], edit['before'], 1)
    require(digest(text) == row['parent_sha256'], 'historical inverse changed: ' + relative)
    return text


def native(relative, text):
    inverse(relative, text)
    return text.replace(SELECTED, DEFAULT, 1) if relative == RUNTIME else text


def configured(configuration):
    value = configuration.get(KEY)
    require(value in (None, POLICY), 'unknown reset policy')
    if value is not None:
        require(configuration.get('demo_role') == 'M' and
                configuration.get('tf_policy') == 'task3_m_native_direct_tf_v1' and
                configuration.get('phone_batch_policy') == 'full_key_atomic_owner_snapshot_command_v1',
                'requires the explicit paired M direct-TF owner')
    return value is not None


def select(stage, configuration):
    selected = configured(configuration)
    if selected:
        path = Path(stage) / RUNTIME
        text = path.read_text()
        inverse(RUNTIME, text)
        require(text.count(DEFAULT) == 1 and SELECTED not in text, 'default selection drift')
        path.write_text(text.replace(DEFAULT, SELECTED, 1))
    return evidence(stage, configuration)


def evidence(stage, configuration):
    selected = configured(configuration)
    stage = Path(stage)
    if not selected:
        if (stage / RUNTIME).is_file():
            require(SELECTED not in (stage / RUNTIME).read_text(), 'unselected local reset')
        return None
    hashes = {}
    for relative in (RUNTIME, TAIL):
        path = stage / relative
        require(path.is_file(), 'source missing: ' + relative)
        text = path.read_text()
        inverse(relative, text)
        if relative == RUNTIME:
            require(text.count(SELECTED) == 1 and DEFAULT not in text, 'local option not selected')
        hashes[relative] = digest(text)
    return dict(policy=POLICY, source_sha256=hashes,
        asynchronous_assertion='existing coherent common runtime lifetime',
        compute_release='u_managed/runtime/compute_release[2]',
        serial_release='u_managed/runtime/serial_common_release[2]',
        new_reset_registers=0, sample_schedule_changed=False,
        session_fence_resets_mailbox=False, legacy_source_inverse_verified=True,
        mapped_reset_verified=False, routed_timing_verified=False, hardware_tested=False)


def audit_mapped(n, *, stage, root=None):
    """Prove the two actual release chains and every selected tail reset pin.

    This gate does not replace mailbox payload, Gray, complete CPU/TF CDC or
    physical recovery/removal proofs.
    """
    from tools.workstation_runtime_pcm_cdc import BooleanDiagram, Graph
    from tools.workstation_recording_phase1_cdc import complete_closure
    from tools.workstation_task3_root_reset_audit import audit_root_startup
    stage=Path(stage)
    profile=json.loads((stage.parents[1]/'workstation_profile.json').read_text())
    require(profile.get('profile') in PROFILES, 'mapped reset requires explicit reviewed M')
    source=evidence(stage,profile['configuration'])
    root=root or audit_root_startup(n,stage=stage)
    require(root.get('all_state_assignments_proven') is True, 'complete actual root proof required')
    g=Graph(n);rq=root['root_q'];runtime='u_managed/runtime'
    guard=g.register('u_runtime_memory_guard','started_o');guard_q=n.pin(guard,'Q')
    grant=n.canonical('','runtime_reset_n')
    chains={}
    for role,clock,stem in [('compute','audio_clk','compute_release'),
                            ('serial','dac_mclk_d','serial_common_release')]:
        start=g.group(runtime,'startup_'+role,2);release=g.group(runtime,stem,3)
        regs=start+release;leaves=[rq,guard_q,*[n.pin(p,'Q') for p in regs]]
        require(len(leaves)==len(set(leaves))==7,'reset chain sources alias')
        b=BooleanDiagram(leaves)
        require(g.support(grant)=={rq,guard_q} and b.net(g,grant)==b.both(b.inputs[rq],b.inputs[guard_q]),
                'runtime startup grant is not exact root and memory grant')
        rows=[]
        for index,p in enumerate(regs):
            c=n.cells[p]
            require(c['kind']=='DFFCE' and set(c['ports'])=={'Q','D','CLK','CE','CLEAR'} and
                    c['parameters'].get('INIT',"1'b0")=="1'b0" and
                    n.pin(p,'CLK')==clock and n.pin(p,'CE') in g.high,
                    'release primitive/INIT/clock/CE changed: '+p)
            clear=n.pin(p,'CLEAR')
            require(g.support(clear)=={rq} and b.net(g,clear)==b.invert(b.inputs[rq]),
                    'release assertion not exact actual root: '+p)
            if index==0:expected=b.both(b.inputs[rq],b.net(g,grant))
            elif index==1:expected=b.both(b.inputs[rq],b.inputs[n.pin(start[0],'Q')])
            else:
                previous=1 if index==2 else b.inputs[n.pin(regs[index-1],'Q')]
                expected=b.all([b.inputs[rq],b.inputs[n.pin(start[1],'Q')],previous])
            actual=b.choose(b.net(g,clear),0,b.net(g,n.pin(p,'D')))
            require(actual==expected,'reset-inclusive local next-Q changed: '+p)
            rows.append(dict(register=p,clock=clock,reset_inclusive_next_q_exact=True))
        chains[role]=dict(registers=rows,final_q=n.pin(release[2],'Q'),
            all_state_assignments_proven=True,first_release_edge=5,
            new_registers=0)
    checked=[];tail=runtime+'/g_direct_tf.tail'
    for p,c in g.regs.items():
        scope=n.scopes[p]
        if scope==tail:pass
        elif scope==runtime and p.startswith(runtime+'/g_direct_tf.'):
            pass
        else:continue
        clock=n.pin(p,'CLK')
        role='compute' if clock=='audio_clk' else 'serial' if clock=='dac_mclk_d' else None
        require(role is not None,'tail register has unexpected clock: '+p)
        local=chains[role]['final_q'];b=BooleanDiagram([local])
        clear=n.pin(p,'CLEAR')
        require(c['kind']=='DFFCE' and c['parameters'].get('INIT',"1'b0")=="1'b0" and
                g.support(clear)=={local} and b.net(g,clear)==b.invert(b.inputs[local]),
                'tail state bypasses its exact local release: '+p)
        checked.append(dict(register=p,clock=clock,domain=role,clear=clear))
    require(len(checked)>900 and {r['domain'] for r in checked}=={'compute','serial'},
            'complete TF tail/owner state inventory missing')
    # Forward traversal covers arithmetic carry/mux primitives as well as
    # LUTs. The Boolean-chain proof above intentionally admits only LUT/INV.
    closure=complete_closure(n,g,[root['root_register']])
    selected={row['register'] for row in checked}
    hits=[pin for pin in closure['ff_endpoints']
          if pin.rsplit('/',1)[0] in selected and pin.rsplit('/',1)[1] in ('D','CE')]
    require(not hits,'raw root reaches selected tail data/enable: '+str(hits))
    require(not any(pin.startswith(tail+'/') for pin in closure['primitive_endpoints']),
            'opaque raw-root consumer in physical tail')
    return dict(policy=POLICY,source=source,root=root,chains=chains,registers=checked,
        register_count=len(checked),all_selected_tail_reset_pins_proven=True,
        actual_root_consumer_closure=closure,
        raw_root_absent_from_tail_data_and_enable=True,full_tf_cdc_proven=False,
        routed_timing_verified=False,hardware_tested=False,deployment_allowed=False)
