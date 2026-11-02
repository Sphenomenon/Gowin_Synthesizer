"""Actual M paired merged-release chains and their four exact SDC queries.

The root and local release state transitions are proved, including assertion
polarity and reset-before-enable. Complete final consumer inventories are
bound separately from downstream business functions, which remain deferred.
No candidate, historical SDC, source profile or hardware state is modified.
"""
import fnmatch

from tools.workstation_recording_phase1_cdc import complete_closure
from tools.workstation_runtime_pcm_cdc import BooleanDiagram, Graph
from tools.workstation_task3_root_reset_audit import (
    PAIRED_PROVIDER, M_PHONE_PROVIDER, validate_root_publisher)
from tools.workstation_task3_peripheral_releases_audit import (
    closure_identity, zero_async_ff, PAIRED_CPU_SOURCE_CLOSURE,
    PAIRED_CPU_DESTINATION_CLOSURE)
from tools.workstation_task3_tf_direct import paired_release_constraint_mappings

POLICY = 'task3_m_paired_real_release_sdc_inventory_v1'
# Functional consumer -> reviewed surviving three-stage register owner.
CHAINS = (
    ('cpu-source', 'u_runtime/u_cpu_cdc', 'held_data', 0,
     'u_task3_pair_link/config_cdc', 'p_release', 'ram_clk', True,
     PAIRED_CPU_SOURCE_CLOSURE),
    ('cpu-destination', 'u_runtime/u_cpu_cdc', 'destination_data', 0,
     'u_task3_pair_link/config_cdc', 'a_release', 'clk_50m', True,
     PAIRED_CPU_DESTINATION_CLOSURE),
    ('transport-source', 'u_managed/runtime/g_direct_tf.transport_health_mailbox',
     'held_data', 0, 'u_task3_m_final_tap', 'source_release', 'dac_mclk_d', False,
     '495453ad101e7567b95feca4b879a69a045f3b3fe0e743bd64fe4147be66d8ab'),
    ('midi-destination', 'u_managed/midi_bytes', 'acknowledge_toggle', None,
     'u_task3_m_pcm_commands', 'a_release', 'audio_clk', False,
     '401f63730ad5f2c0b9be436d56a108982f2db213ca9211b85b50264fbaabe052'),
)


def require(ok, message):
    if not ok:
        raise ValueError('M paired release audit: ' + message)


def audit_paired_release_sdc(n, sdc, *, root):
    require(root.get('selected_provider') in (PAIRED_PROVIDER, M_PHONE_PROVIDER) and
            root.get('all_state_assignments_proven') is True and
            root.get('actual_state_bits') == 35, 'verified explicit paired M root required')
    g = Graph(n)
    root_q = validate_root_publisher(n, g, root)
    pins = {p + '/' + pin for p, cell in n.cells.items() for pin in cell['ports']}
    mappings = paired_release_constraint_mappings()
    rows = []
    for config, (retired, selected) in zip(CHAINS, mappings):
        label, scope, stem, bit, owner, release_stem, domain, cpu, expected_sha = config
        require(retired not in sdc and sdc.count(selected) == 1,
                'exact installed paired release selector absent/duplicated: ' + label)
        functional = g.register(scope, stem, bit)
        registers = g.group(owner, release_stem, 3)
        selected_pins = {pin for pin in pins if fnmatch.fnmatchcase(pin, selected)}
        require(selected_pins == {p + '/CLEAR' for p in registers},
                'release selector reaches a missing/unreviewed CLEAR pin: ' + label)
        clear = n.pin(functional, 'CLEAR')
        common = n.pin(registers[0], 'CLEAR')
        final_q = n.pin(registers[2], 'Q')
        named = [root_q, *(n.pin(p, 'Q') for p in registers)]
        if cpu:
            named.append(n.canonical('', 'preset_n'))
        require(len(named) == len(set(named)), 'release/common assertion inputs alias')
        bd = BooleanDiagram(named)
        live = bd.inputs[root_q]
        if cpu:
            live = bd.both(live, bd.inputs[n.canonical('', 'preset_n')])
        require(g.support(common, cuts=(n.canonical('', 'preset_n'),) if cpu else ()) ==
                ({root_q, n.canonical('', 'preset_n')} if cpu else {root_q}) and
                bd.net(g, common) == bd.invert(live),
                'release common CLEAR root/domain polarity changed: ' + label)
        require(g.support(clear) == {final_q} and
                bd.net(g, clear) == bd.invert(bd.inputs[final_q]),
                'functional CLEAR is not the actual final release inverse: ' + label)
        next_rows, closures = [], []
        for index, p in enumerate(registers):
            zero_async_ff(n, p, clock=domain, clear=common)
            require(n.pin(p, 'CE') in g.high and
                    (n.pin(p, 'D') in g.high if index == 0 else
                     n.pin(p, 'D') == n.pin(registers[index-1], 'Q')),
                    'three-stage release fill/shift/enable changed: ' + label)
            next_q = bd.choose(bd.net(g, common), 0, bd.choose(
                bd.net(g, n.pin(p, 'CE')), bd.net(g, n.pin(p, 'D')), bd.inputs[n.pin(p, 'Q')]))
            expected = bd.both(live, 1 if index == 0 else bd.inputs[n.pin(registers[index-1], 'Q')])
            require(next_q == expected, 'reset-inclusive release state update changed: ' + p)
            next_rows.append(dict(register=p, reset_before_enable=True,
                                  reset_inclusive_next_q_exact=True))
            closure = complete_closure(n, g, [p])
            if index < 2:
                require(closure['ff_endpoints'] == {registers[index+1] + '/D': domain} and
                        not closure['primitive_endpoints'] and not closure['top_output_endpoints'],
                        'early release bypass/extra consumer: ' + p)
            else:
                require(closure_identity(closure) == expected_sha,
                        'paired final release complete consumer inventory changed: ' + label)
                for endpoint, clock in closure['ff_endpoints'].items():
                    if endpoint.endswith('/CLEAR'):
                        require(clock == domain, 'async clear crosses a different domain')
                        zero_async_ff(n, endpoint.rsplit('/', 1)[0], clock=domain, clear=clear)
            closures.append(closure)
        final = closures[-1]
        rows.append(dict(id=label, functional_register=functional, functional_clear=clear,
            actual_release_registers=registers, release_clock=domain,
            selector=selected, exact_release_CLEAR_pins=sorted(selected_pins),
            root_q=root_q, domain_reset=n.canonical('', 'preset_n') if cpu else None,
            common_assertion_exact=True, release_next_q=next_rows,
            boolean_assignments_proven=1 << len(named),
            first_two_stage_only_next_D_consumer=True,
            complete_final_consumer_inventory_sha256=expected_sha,
            final_consumer_closure=final,
            deferred_business_ff_pins=sum(not p.endswith('/CLEAR') for p in final['ff_endpoints']),
            deferred_business_primitive_pins=len(final['primitive_endpoints']),
            deferred_business_top_outputs=len(final['top_output_endpoints']),
            downstream_business_function_proven=False))
    return dict(policy=POLICY, selected_provider=root['selected_provider'],
        actual_root_register=root['root_register'], root_q=root_q,
        actual_release_chains=rows, distinct_release_FFs=12,
        exact_installed_release_CLEAR_pins=12,
        reset_inclusive_next_q_and_assertion_polarity_proven=True,
        complete_consumer_inventories_verified=True,
        whole_business_CDC_accepted=False, physical_recovery_removal_verified=False,
        routed_timing_verified=False, hardware_tested=False)
