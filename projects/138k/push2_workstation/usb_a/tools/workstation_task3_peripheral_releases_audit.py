"""Actual task3 peripheral release aliases, async clears and complete fanout.

Trace from functional CLEAR pins before selecting any release register.  The
performance chain was merged into TF control; the CPU source chain was merged
into APB.  This is a reset proof, not a payload/handshake or physical CDC proof.
"""
from tools.workstation_recording_phase1_cdc import complete_closure
from tools.workstation_runtime_pcm_cdc import BooleanDiagram, Graph
from tools.workstation_task3_root_reset_audit import (
    POLICY as ROOT_POLICY, ROOT_SOURCE, ROOT_SOURCE_SHA256)

POLICY = 'task3-direct-peripheral-real-release-v1'
PERFORMANCE_BITS = (*range(48), *range(56, 67), *range(96, 416), 446)
SOURCE_CONTROL = ('ack_meta', 'ack_sync', 'request_toggle')
DESTINATION_CONTROL = ('req_meta', 'req_sync', 'req_settled', 'acknowledge_toggle')
CPU_BLACKBOX = 'u_cpu/u_RiscV_AE350_SOC'
CPU_DEFERRED = {CPU_BLACKBOX + '/' + pin for pin in ('n8275_3', 'n8280_3')}


def require(condition, message):
    if not condition:
        raise ValueError('task3 peripheral release audit: ' + message)


def zero_async_ff(n, path, *, clock, clear):
    cell = n.cells[path]
    require(cell['kind'] == 'DFFCE' and
            set(cell['ports']) == {'Q', 'D', 'CLK', 'CE', 'CLEAR'},
            'not the reviewed asynchronous clear FF: ' + path)
    require(cell['parameters'].get('INIT', "1'b0") == "1'b0",
            'nonzero/unsupported effective INIT: ' + path)
    require(n.pin(path, 'CLK') == clock, 'clock changed: ' + path)
    require(n.pin(path, 'CLEAR') == clear, 'functional/common CLEAR changed: ' + path)
    return dict(register=path, primitive=cell['kind'], effective_init=0,
                **{pin.lower(): n.pin(path, pin) for pin in ('Q', 'D', 'CLK', 'CE', 'CLEAR')})


def trace_release(n, g, functional, *, alias_scope, alias_stem, clock,
                  root_q, other_reset, opaque_cpu_reset=False,
                  shared_cpu_source=False, expected_final_count):
    """Follow actual CLEAR -> INV -> Q2 -> D2/Q1 -> D1/Q0 -> one."""
    clear = n.pin(functional, 'CLEAR')
    drivers = g.drivers[clear]
    require(len(drivers) == 1, 'functional CLEAR absent/ambiguous: ' + functional)
    inverter, port = drivers[0]
    require(n.cells[inverter]['kind'] == 'INV' and port == 'O',
            'functional CLEAR is not final release inversion: ' + functional)
    final_q = n.pin(inverter, 'I')
    backwards, net = [], final_q
    for bit in (2, 1, 0):
        drivers = g.drivers[net]
        require(len(drivers) == 1 and drivers[0][1] == 'Q' and drivers[0][0] in g.regs,
                'release trace does not reach unique FF Q at stage ' + str(bit))
        path = drivers[0][0]
        # Only after tracing the real dependency do we check the reviewed alias.
        require(path == g.register(alias_scope, alias_stem, bit),
                'actual release chain uses an unreviewed alias: ' + path)
        backwards.append(path)
        net = n.pin(path, 'D')
    require(net in g.high, 'first release stage does not fill from one')
    registers = list(reversed(backwards))
    common = n.pin(registers[0], 'CLEAR')
    rows = [zero_async_ff(n, path, clock=clock, clear=common) for path in registers]
    require(all(n.pin(path, 'CE') in g.high for path in registers),
            'release stage CE is not continuously enabled')
    named = [root_q, other_reset, *(n.pin(path, 'Q') for path in registers)]
    require(len(named) == len(set(named)), 'release/common reset states alias each other')
    bd = BooleanDiagram(named)
    live = bd.both(bd.inputs[root_q], bd.inputs[other_reset])
    require(bd.net(g, common) == bd.invert(live),
            'common CLEAR is not exact NAND(real root, declared domain reset)')
    require(g.support(common, cuts=(other_reset,) if opaque_cpu_reset else ()) == {root_q, other_reset},
            'unreviewed common reset source')
    require(bd.net(g, clear) == bd.invert(bd.inputs[final_q]),
            'functional CLEAR is not exact inverse final release')
    for bit, path in enumerate(registers):
        next_q = bd.choose(bd.net(g, n.pin(path, 'CLEAR')), 0,
            bd.choose(bd.net(g, n.pin(path, 'CE')), bd.net(g, n.pin(path, 'D')),
                      bd.inputs[n.pin(path, 'Q')]))
        expected = bd.both(live, 1 if bit == 0 else bd.inputs[n.pin(registers[bit-1], 'Q')])
        require(next_q == expected, 'reset-inclusive release next-Q changed: ' + path)
        rows[bit].update(reset_before_enable=True, reset_inclusive_next_q_exact=True,
                         next_q_contract='root & domain_reset' + ('' if bit == 0 else ' & previous_stage'))
    closures = [complete_closure(n, g, [path]) for path in registers]
    for bit in (0, 1):
        c = closures[bit]
        require(c['ff_endpoints'] == {registers[bit+1] + '/D': clock} and
                not c['primitive_endpoints'] and not c['top_output_endpoints'],
                'early release stage has an extra/bypassed consumer: ' + registers[bit])
    final = closures[2]
    require(len(final['ff_endpoints']) == expected_final_count and
            all(endpoint.endswith('/CLEAR') and domain == clock
                for endpoint, domain in final['ff_endpoints'].items()) and
            not final['top_output_endpoints'],
            'final release FF consumer/clock/pin inventory changed: ' + registers[2])
    allowed_opaque = CPU_DEFERRED if shared_cpu_source else set()
    require(set(final['primitive_endpoints']) == allowed_opaque and
            all(row['kind'] == 'RiscV_AE350_SOC' and not row['clock_pins']
                for row in final['primitive_endpoints'].values()),
            'unreviewed opaque release consumer')
    # Shared-owner FF endpoints still require actual asynchronous zero-clear
    # semantics. Opaque APB outputs are kept as explicit unresolved boundaries.
    for endpoint in final['ff_endpoints']:
        zero_async_ff(n, endpoint.rsplit('/', 1)[0], clock=clock, clear=clear)
    return dict(registers=registers, clock=clock, functional_clear=clear,
                functional_clear_inverter=inverter, final_q=final_q,
                common_clear=common, common_reset_sources=[root_q, other_reset],
                opaque_cpu_reset_cut=other_reset if opaque_cpu_reset else None,
                chain_next_q=rows, all_32_reset_and_state_assignments_proven=True,
                first_two_stages_have_only_next_D_consumer=True,
                consumer_closures=closures, release_edges_after_both_resets_high=3,
                deferred_opaque_endpoints=sorted(allowed_opaque),
                physical_recovery_removal_verified=False)


def audit_peripheral_releases(n, *, root):
    g = Graph(n)
    require(root.get('policy') == ROOT_POLICY and root.get('all_state_assignments_proven') is True
            and root.get('actual_state_bits') == 35 and
            root.get('source_sha256', {}).get(ROOT_SOURCE) == ROOT_SOURCE_SHA256,
            'verified task3 real-root startup proof required')
    root_register = root.get('root_register')
    require(root_register in g.regs and root_register == g.register('u_reset', 'started') and
            g.drivers[root.get('root_q')] == [(root_register, 'Q')] and
            root['root_q'] == n.pin(root_register, 'Q') == n.canonical('', 'reset_n'),
            'provided root proof does not refer to actual common reset publisher')
    audio_publisher = g.register('u_audio_clock', 'audio_reset_pipe', 3)
    audio_reset = n.pin(audio_publisher, 'Q')
    require(audio_reset == n.canonical('', 'audio_reset_n') and
            n.cells[audio_publisher]['kind'] == 'DFFCE' and
            n.pin(audio_publisher, 'CLK') == 'audio_clk',
            'audio domain reset is not the declared clock-owner registered output')
    cpu_reset = n.canonical('', 'preset_n')
    require(n.cells[CPU_BLACKBOX]['kind'] == 'RiscV_AE350_SOC' and
            n.pin(CPU_BLACKBOX, 'preset_n') == cpu_reset and not g.drivers[cpu_reset] and
            cpu_reset not in g.high | g.low,
            'declared opaque AE350 preset_n boundary changed')
    chains, scopes = [], []
    configs = (
        ('performance', PERFORMANCE_BITS, 'audio_clk', audio_reset,
         'u_tf_control_cdc', 'source_release', 'u_tf_control_cdc', 410, 413),
        ('cpu', tuple(range(224)), 'ram_clk', cpu_reset,
         'u_managed/control_cdc', 'p_release', 'u_runtime/u_cpu_cdc', 315, 228),
    )
    for name, bits, source_clock, other_reset, source_alias, source_stem, destination_alias, scount, dcount in configs:
        scope = 'u_runtime/u_' + name + '_cdc'
        held = [g.register(scope, 'held_data', bit) for bit in bits]
        destination = [g.register(scope, 'destination_data', bit) for bit in bits]
        source_control = [g.register(scope, stem) for stem in SOURCE_CONTROL]
        destination_control = [g.register(scope, stem) for stem in DESTINATION_CONTROL]
        source_owned, destination_owned = held + source_control, destination + destination_control
        local = []
        for role, functional, alias, stem, clock, count, opaque in (
            ('source', held[0], source_alias, source_stem, source_clock, scount, name == 'cpu'),
            ('destination', destination[0], destination_alias, 'destination_release', 'clk_50m', dcount, False),
        ):
            row = trace_release(n, g, functional, alias_scope=alias, alias_stem=stem,
                clock=clock, root_q=root['root_q'], other_reset=other_reset,
                opaque_cpu_reset=name == 'cpu', shared_cpu_source=opaque, expected_final_count=count)
            row.update(id=name + '-' + role, functional_scope=scope, role=role)
            chains.append(row)
            local.append(row)
        expected_inventory = set(source_owned + destination_owned +
                                 [p for row in local for p in row['registers'] if p.startswith(scope + '/')])
        require({p for p in g.regs if p.startswith(scope + '/')} == expected_inventory,
                'peripheral functional/release register inventory changed: ' + scope)
        functional_rows = []
        for owned, release in zip((source_owned, destination_owned), local):
            for path in owned:
                row = zero_async_ff(n, path, clock=release['clock'], clear=release['functional_clear'])
                require(path + '/CLEAR' in release['consumer_closures'][2]['ff_endpoints'],
                        'owned FF absent from actual final-release closure: ' + path)
                functional_rows.append(row)
        # Preserve the exact held payload destination wiring.  Ingress content
        # and source acceptance CE are observed below, not proved by this audit.
        for source, capture in zip(held, destination):
            require(n.pin(capture, 'D') == n.pin(source, 'Q'),
                    'destination payload is no longer actual corresponding held Q: ' + capture)
        source_ce, destination_ce = (n.pin(paths[-1], 'CE') for paths in (source_control, destination_control))
        require(all(n.pin(path, 'CE') == source_ce for path in held) and
                all(n.pin(path, 'CE') == destination_ce for path in destination),
                'payload FF CE differs from its local request/acknowledge commit CE')
        scopes.append(dict(id=name, scope=scope, retained_payload_bits=list(bits),
            functional_register_count=len(functional_rows), functional_registers=functional_rows,
            all_owned_reset_pins_in_final_release_closure=True,
            corresponding_held_to_destination_D_verified=True,
            payload_commit_CE_consistency_verified=True,
            ingress_data_and_acceptance_logic_proven=False, complete_handshake_proven=False))
    require(len({p for row in chains for p in row['registers']}) == 12,
            'distinct actual peripheral release inventory changed')
    return dict(policy=POLICY, root_register=root_register, root_q=root['root_q'],
        root_source_sha256=root['source_sha256'], audio_reset_publisher=audio_publisher,
        declared_opaque_cpu_reset_cut=cpu_reset, opaque_cpu_reset_internal_logic_proven=False,
        release_chains=chains, release_register_count=12,
        functional_scopes=scopes, functional_register_count=sum(s['functional_register_count'] for s in scopes),
        source_policy='actual functional CLEAR backward trace; reviewed shared alias inventory; exact async release next-Q',
        routed_timing_verified=False, physical_cdc_accepted=False, hardware_tested=False,
        release_ready=False, deployment_allowed=False)
