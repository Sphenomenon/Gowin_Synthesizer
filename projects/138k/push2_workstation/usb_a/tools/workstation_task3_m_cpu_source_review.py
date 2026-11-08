"""Supplemental, read-only M v16 CPU-source consumer review.

This is not selected by the sealed v16 synthesis auditor. It proves the named
source reset inventory and external APB response equations on that candidate;
it does not replace historical inventory hashes or accept the CPU black box,
destination, full handshake, physical CDC, timing, or hardware.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_recording_phase1_cdc import complete_closure
from tools.workstation_runtime_pcm_cdc import BooleanDiagram, Graph
from tools.workstation_task3_peripheral_releases_audit import (
    CPU_BLACKBOX, closure_identity, zero_async_ff)
from tools.workstation_task3_root_reset_audit import (
    PHONE_GROUPED_ROOT_VARIANT, source_binding)

POLICY = 'task3-m-v16-supplemental-cpu-source-review-v1'
PROFILE = 'custom138k-workstation-task3-m-paired-checkpoint-v16'
CONFIG = 'u_task3_pair_link/config_cdc'
MANAGED = 'u_managed/control_cdc'
STREAM = 'u_runtime/u_cpu_cdc'
APB_SOURCE = 'src/migration/gw138k_apb_cdc.sv'
STREAM_SOURCE = 'src/migration/gw138k_stream_cdc.sv'
SOURCES = {
    APB_SOURCE: '99eddbe61b57756f50e97cf108099cdfaf7324b55178808ab4d403bebf9818b7',
    STREAM_SOURCE: '90cb55acd6f83965d74b843993bed625d121ae2eefafbd928eb6fececb6e5376',
}
# These opaque inputs have reviewed external APB equations. They are not
# established reset pins; CPU interpretation of the inputs remains unproved.
OPAQUE_INPUTS = {'ready': 'n9888_3', 'error': 'n9896_3'}
PREBOARD_PROFILE = 'custom138k-workstation-task3-m-preboard-v1'
from tools.workstation_task3_m_phone_lease_source import ROOT_VARIANT as PREBOARD_ROOT_VARIANT
SELECTIONS = {PROFILE: (PHONE_GROUPED_ROOT_VARIANT, OPAQUE_INPUTS),
              PREBOARD_PROFILE: (PREBOARD_ROOT_VARIANT, {'ready':'n9892_3','error':'n9900_3'})}


def require(condition, message):
    if not condition:
        raise ValueError('M CPU source review: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sources(stage):
    stage = Path(stage)
    artifact = json.loads((stage.parent.parent / 'workstation_profile.json').read_text())
    binding = source_binding(stage)
    selected = SELECTIONS.get(artifact['profile'])
    require(selected is not None and binding.get('root_mapping_variant') == selected[0],
            'explicit reviewed CPU source profile/root variant required')
    for relative, expected in SOURCES.items():
        require(sha(stage / relative) == expected, 'sealed source drift: ' + relative)
    return dict(profile=artifact['profile'], candidate_identity=artifact['candidate_identity'],
                reviewed_source_sha256=SOURCES, root_binding=binding)


def review(n, *, source):
    selected = SELECTIONS.get(source.get('profile'))
    require(selected is not None and source.get('reviewed_source_sha256') == SOURCES and
            source.get('root_binding', {}).get('root_mapping_variant') == selected[0],
            'reviewed source binding required')
    opaque_inputs = selected[1]
    g = Graph(n)
    release = g.register(CONFIG, 'p_release', 2)
    release_q = n.pin(release, 'Q')
    clear = n.pin(g.register(STREAM, 'held_data', 0), 'CLEAR')
    require(g.support(clear) == {release_q}, 'final source CLEAR has extra input')
    bd = BooleanDiagram([release_q])
    require(bd.net(g, clear) == bd.invert(bd.inputs[release_q]),
            'final source CLEAR polarity changed')
    groups = {}
    for scope in (CONFIG, MANAGED):
        for stem, width in (('request_held', 49), ('response_local', 33), ('state', 2),
                            ('ack_meta', None), ('ack_sync', None),
                            ('ack_settled', None), ('request_toggle', None)):
            groups[scope + '/' + stem] = g.group(scope, stem, width)
    for stem, width in (('held_data', 224), ('ack_meta', None),
                        ('ack_sync', None), ('request_toggle', None)):
        groups[STREAM + '/' + stem] = g.group(STREAM, stem, width)
    registers = [p for rows in groups.values() for p in rows]
    require(len(registers) == len(set(registers)) == 403, 'named source states alias')
    for p in registers:
        zero_async_ff(n, p, clock='ram_clk', clear=clear)
    closure = complete_closure(n, g, [release])
    require(closure['ff_endpoints'] == {p + '/CLEAR': 'ram_clk' for p in registers},
            'complete source FF inventory differs from named state groups')
    require(not closure['top_output_endpoints'], 'source release reaches a top output')
    preboard=source['profile']==PREBOARD_PROFILE
    if preboard:
        # Synthesis numeric pin names can change with unrelated mapped logic.
        # Admit exactly two actual CPU input endpoints, then identify each by
        # its complete external APB Boolean equation below. No CPU pin is
        # assumed to be a reset or accepted by name/count alone.
        require(len(closure['primitive_endpoints'])==2 and
                all(pin.startswith(CPU_BLACKBOX+'/') and
                    row['kind']=='RiscV_AE350_SOC' and not row['clock_pins']
                    for pin,row in closure['primitive_endpoints'].items()),
                'unreviewed opaque source consumer')
    else:
        require(set(closure['primitive_endpoints']) ==
                {CPU_BLACKBOX + '/' + pin for pin in opaque_inputs.values()} and
                all(row['kind'] == 'RiscV_AE350_SOC' and not row['clock_pins']
                    for row in closure['primitive_endpoints'].values()),
                'unreviewed opaque source consumer')

    # Independently named CPU outputs are legitimate external Boolean inputs.
    # Never cut a net merely because recursive traversal could not resolve it.
    bus = [f'paddr[{i}]' for i in (*range(2), *range(12, 32))]
    bus += [f'pstrb[{i}]' for i in range(4)] + ['psel']
    wrapper = n.frames['u_cpu']['kind']
    for port in ('paddr', 'pstrb', 'psel'):
        require(n.directions[wrapper].get(port) == 'output',
                'declared external CPU output changed: ' + port)
    for net in bus:
        require(not g.drivers[net] and
                net in g.binding_bits('', n.cells['u_cpu']['ports'][net.split('[')[0]]),
                'external CPU bus output binding changed: ' + net)
    q = lambda scope, stem, bit: n.pin(g.register(scope, stem, bit), 'Q')
    # Pair-config and managed-control share the actual source release; UI and
    # clock-control have their own retained release FFs. All states are free
    # independent inputs, including illegal states, rather than assumed valid.
    pages = ((0xf8080, CONFIG, CONFIG), (0xf8030, 'u_clock_control', 'u_clock_control'),
             (0xf8010, MANAGED, CONFIG), (0xf8020, 'u_ui_control', 'u_ui_control'))
    named = {release_q}
    for _, scope, owner in pages:
        named.update(q(scope, 'state', i) for i in range(2))
        named.add(q(scope, 'response_local', 32))
        named.add(q(owner, 'p_release', 2))
    leaves = sorted(named) + bus
    require(len(leaves) == len(set(leaves)), 'external inputs alias state Qs')
    for net in named:
        ds = g.drivers[net]
        require(len(ds) == 1 and ds[0][0] in g.regs and ds[0][1] == 'Q' and
                n.pin(ds[0][0], 'CLK') == 'ram_clk', 'APB state is not a unique source Q')
    bd = BooleanDiagram(leaves)
    bit = lambda net: bd.inputs[net]

    def address(page):
        return bd.all(bit(f'paddr[{i}]') if (page >> (i - 12)) & 1 else
                      bd.invert(bit(f'paddr[{i}]')) for i in range(12, 32))

    valid_word = bd.all([address(0xf8000), bd.invert(bit('paddr[0]')),
                         bd.invert(bit('paddr[1]')),
                         *(bit(f'pstrb[{i}]') for i in range(4))])
    expected = {'ready': 1, 'error': bd.invert(valid_word)}
    for page, scope, owner in reversed(pages):
        select = bd.both(bit('psel'), address(page))
        ready = bd.all([bit(q(owner, 'p_release', 2)),
                        bd.invert(bit(q(scope, 'state', 0))), bit(q(scope, 'state', 1))])
        error = bd.both(ready, bit(q(scope, 'response_local', 32)))
        expected['ready'] = bd.choose(select, ready, expected['ready'])
        expected['error'] = bd.choose(select, error, expected['error'])
    if preboard:
        equations={}
        for endpoint in closure['primitive_endpoints']:
            pin=endpoint.rsplit('/',1)[1];net=n.pin(CPU_BLACKBOX,pin)
            require(g.support(net,cuts=bus)<=set(leaves),'unreviewed APB source input')
            equations[pin]=bd.net(g,net)
        opaque_inputs={}
        for label,wanted in expected.items():
            matches=[pin for pin,equation in equations.items()if equation==wanted]
            require(len(matches)==1,'unique external APB equation absent: '+label)
            opaque_inputs[label]=matches[0]
        require(len(set(opaque_inputs.values()))==2,'external APB input roles alias')
        require(opaque_inputs in (
            {'ready':'n9892_3','error':'n9900_3'},
            {'ready':'n9892_10','error':'n9900_3'},
            {'ready':'n9892_11','error':'n9900_3'}),
            'reviewed external CPU APB pin roles changed')
    opaque = {}
    for label, pin in opaque_inputs.items():
        net = n.pin(CPU_BLACKBOX, pin)
        support = g.support(net, cuts=bus)
        require(support <= set(leaves), 'unreviewed APB response publisher: ' + label)
        require(bd.net(g, net) == expected[label], 'external APB mux equation changed: ' + label)
        opaque[label] = dict(endpoint=CPU_BLACKBOX + '/' + pin, actual_net=net,
                             actual_support=sorted(support), equation_proven=True,
                             treated_as_reset_input=False, CPU_internal_semantics_proven=False)
    return dict(policy=POLICY, source_binding=source, release_register=release,
        release_q=release_q, clear=clear, named_groups=groups,
        complete_closure=closure, complete_closure_sha256=closure_identity(closure),
        named_source_FF_CLEAR_count=403, source_FF_clear_inventory_proven=True,
        external_APB_response_equations=opaque, independent_Boolean_inputs=leaves,
        Boolean_assignments=1 << len(leaves), BDD_nodes=len(bd.nodes),
        illegal_APB_states_included=True, complete_source_handshake_proven=False,
        CPU_internal_semantics_proven=False, destination_proven=False,
        selected_by_sealed_v16_auditor=False, historical_inventory_replaced=False,
        whole_CDC_accepted=False, timing_closed=False, hardware_tested=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'refuse to overwrite evidence')
    stage = args.stage.resolve()
    vg = stage / 'impl/gwsynthesis/custom_138k_integration.vg'
    selected = sources(stage)
    bound_sources = {**selected['root_binding']['source_sha256'], **SOURCES}
    require(all(sha(stage / rel) == expected for rel, expected in bound_sources.items()),
            'reviewed source changed before graph load')
    before = {str(p): sha(p) for p in (vg, stage.parent.parent / 'workstation_profile.json',
                                     *(stage / rel for rel in bound_sources))}
    result = review(protocol_netlist(vg.read_text(), mapping='synthesis'), source=selected)
    require(before == {p: sha(p) for p in before}, 'immutable input changed during review')
    result.update(input_sha256=before, inputs_unchanged=True,
                  reviewer_sha256=sha(__file__), reviewer_path=str(Path(__file__).resolve()))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in
                     ('policy', 'named_source_FF_CLEAR_count', 'Boolean_assignments',
                      'whole_CDC_accepted', 'inputs_unchanged')}))


if __name__ == '__main__':
    main()
