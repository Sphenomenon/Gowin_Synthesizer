"""M-only same-edge cancellation FF replication; no new pipeline stage.

Retire this exact staging annotation when the native composition selects an
audited synthesis fanout policy directly. Historical RTL and profiles stay intact.
"""
from pathlib import Path
import hashlib

KEY = 'cancel_fanout_policy'
POLICY = 'task3_M_same_edge_cancel_fanout128_v1'
SOURCE = 'rtl/audio/gw138k_event_workstation.sv'
DESTINATION = 'src/ae350/gw138k_event_workstation.sv'
TOOL = 'tools/workstation_cancel_fanout.py'
PARENT_SHA256 = 'e17ebe35c8a697453a90260d0139d9525015349a5f5359d02762f915012530e6'
SELECTED_SHA256 = 'd30e05a2f8ff83d144b1e73722ca89635ee60f5657074200d48d033adfe6e447'
BEFORE = '    logic pending_clear;'
AFTER = '    (* syn_maxfan=128 *) logic pending_clear;'


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError('M cancel fanout: ' + message)


def configured(configuration):
    value = configuration.get(KEY)
    require(value in (None, POLICY), 'unknown policy')
    if value:
        require(configuration.get('demo_role') == 'M' and
                configuration.get('event_admission_policy') ==
                'task3_M_combined_sample_event_admission_v1',
                'requires complete M combined admission')
    return bool(value)


def restore(text):
    if AFTER not in text:
        return text
    require(digest(text) == SELECTED_SHA256 and text.count(AFTER) == 1,
            'selected source or annotation drift')
    text = text.replace(AFTER, BEFORE, 1)
    require(digest(text) == PARENT_SHA256, 'inverse parent drift')
    return text


def select(stage, configuration):
    if not configured(configuration):
        return None
    path = Path(stage) / DESTINATION
    text = path.read_text()
    require(digest(text) == PARENT_SHA256 and text.count(BEFORE) == 1,
            'composed parent drift')
    selected = text.replace(BEFORE, AFTER, 1)
    require(digest(selected) == SELECTED_SHA256 and restore(selected) == text,
            'annotation inverse drift')
    path.write_text(selected)
    return evidence(stage, configuration)


def evidence(stage, configuration):
    if not configured(configuration):
        return None
    text = (Path(stage) / DESTINATION).read_text()
    require(digest(text) == SELECTED_SHA256, 'selected annotation absent')
    restore(text)
    return dict(policy=POLICY, parent_sha256=PARENT_SHA256,
                selected_sha256=SELECTED_SHA256, fanout_limit=128,
                executable_RTL_unchanged=True, added_cycles=0,
                sample_and_parameter_edges_unchanged=True,
                physical_timing_verified=False, hardware_tested=False)


def audit(n, configuration=None):
    """Prove the actual, finite replica inventory and every state input pin.

    This proves replica equality by induction from equal INIT/reset and equal
    D/CE/CLEAR/CLK. It does not claim whole-netlist equivalence.
    """
    from tools.workstation_runtime_pcm_cdc import Graph
    from tools.workstation_reader_validated_metadata import configured as compact_selected
    from tools.workstation_reciprocal_div147 import configured as reciprocal_selected
    compact = compact_selected({} if configuration is None else configuration)
    reciprocal = reciprocal_selected({} if configuration is None else configuration)
    g = Graph(n)
    reader = 'u_video/u_runtime_display/reader/'
    validations = {p for p in g.regs if p.startswith(reader) and
                   p.rsplit('/', 1)[-1].startswith(('meta_low_ok_q_', 'meta_high_ok_q_'))}
    prevalidated = bool(validations)
    if prevalidated:
        require(compact and len(validations) == 2 and
                all(any(p.startswith(reader + stem + '_s') for p in validations)
                    for stem in ('meta_low_ok_q', 'meta_high_ok_q')),
                'metadata validation mapping changed')
    # The two reviewed storage mappings pack cancellation consumers differently.
    # Both retain the exact same-edge tuple and the per-replica fanout bound.
    # v116 retires the restoring divider's private valid/flush consumers.
    # The exact11 remaining replicas retain the same tuple and <=128 fanout.
    count = 11 if reciprocal or (compact and not prevalidated) else 12
    scope = 'u_managed/runtime/service/workstation'
    stem = scope + '/native_cancel_delivery.pending_clear'
    expected = {stem + '_s' + str(i) for i in range(1, count + 1)}
    actual = {p for p in g.regs if p.startswith(stem + '_s')}
    require(actual == expected, 'exact selected replica inventory changed: expected ' + str(count))
    pins = dict(D='u_managed/runtime/service/panic_accept_Z',
                CE=scope + '/VCC',
                CLEAR='u_managed/runtime/\\attack_step_q24[0]_ER_init',
                CLK='audio_clk')
    replicas = []
    for p in sorted(actual):
        cell = n.cells[p]
        require(cell['kind'] == 'DFFCE' and
                set(cell['ports']) == {'Q', 'D', 'CE', 'CLEAR', 'CLK'} and
                cell['parameters'].get('INIT', "1'b0") == "1'b0" and
                set(cell['parameters']) <= {'INIT'}, 'FF primitive/INIT changed: ' + p)
        require({pin: n.pin(p, pin) for pin in pins} == pins,
                'D/CE/CLEAR/CLK tuple changed: ' + p)
        q = n.pin(p, 'Q')
        require(g.drivers[q] == [(p, 'Q')], 'replica Q driver changed: ' + p)
        fanout = len(g.fan[q])
        require(0 < fanout <= 128, 'replica fanout outside reviewed bound: ' + p)
        replicas.append(dict(register=p, fanout=fanout))
    return dict(policy=POLICY, replicas=replicas, identical_input_tuple=pins,
                init=0, equality_induction=True, added_registers=count - 1,
                compact_metadata_mapping=compact,
                prevalidated_metadata_mapping=prevalidated,
                reciprocal_divider_mapping=reciprocal,
                added_cycles=0, max_fanout=max(r['fanout'] for r in replicas),
                whole_netlist_equivalence_proven=False,
                physical_timing_verified=False, hardware_tested=False)
