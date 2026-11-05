"""Bounded M CPU-source release comparison against the historical sealed VG.

The 403 asynchronous FF consumers are compared by their complete actual pin
paths. Two AE350 input-cone Boolean functions are compared under the same
explicit registered-state and CPU APB output inputs. This does not establish
the opaque CPU's internal pin roles, sequential state equivalence, the much
larger destination fanout, or physical CDC. No production seal is replaced.
"""
from tools.workstation_recording_phase1_cdc import complete_closure
from tools.workstation_runtime_pcm_cdc import BooleanDiagram, Graph
from tools.workstation_task3_peripheral_releases_audit import (
    CPU_BLACKBOX, PAIRED_CPU_SOURCE_CLOSURE, closure_identity, zero_async_ff)

POLICY = 'task3_m_cpu_source_403_reset_and_opaque_input_cones_v1'
SCOPE = 'u_task3_pair_link/config_cdc'
OPAQUE_PINS = {
    'historical': ('n9887_3', 'n9895_3'),
    'batch': ('n9888_3', 'n9896_3'),
}
STATE_REFS = (
    (SCOPE, 'p_release', 2),
    ('u_ui_control', 'p_release', 2),
    ('u_clock_control', 'p_release', 2),
    *((owner, 'state', bit) for owner in
      (SCOPE, 'u_ui_control', 'u_clock_control', 'u_managed/control_cdc')
      for bit in (0, 1)),
    *((owner, 'response_local', 32) for owner in
      (SCOPE, 'u_ui_control', 'u_clock_control', 'u_managed/control_cdc')),
)


def require(condition, message):
    if not condition:
        raise ValueError('M CPU-source boundary: ' + message)


def _same_boolean(a, av, b, bv, memo=None):
    """Exact canonical BDD comparison with a common ordered input inventory."""
    memo = {} if memo is None else memo
    key = av, bv
    if key not in memo:
        if av < 2 or bv < 2:
            memo[key] = av == bv
        else:
            an, bn = a.nodes[av], b.nodes[bv]
            memo[key] = (an[0] == bn[0] and
                         _same_boolean(a, an[1], b, bn[1], memo) and
                         _same_boolean(a, an[2], b, bn[2], memo))
    return memo[key]


def _inputs(n, g):
    """Resolve exact source register owners and declared CPU output ports."""
    states = {}
    for scope, stem, bit in STATE_REFS:
        path = g.register(scope, stem, bit)
        cell = n.cells[path]
        require(cell['kind'] == 'DFFCE' and
                cell['parameters'].get('INIT', "1'b0") == "1'b0" and
                n.pin(path, 'CLK') == 'ram_clk',
                'opaque cone state primitive/INIT/clock changed: ' + path)
        states[path + '/Q'] = n.pin(path, 'Q')
    require(n.cells[CPU_BLACKBOX]['kind'] == 'RiscV_AE350_SOC',
            'opaque CPU primitive changed')
    buses = {}
    for port, width in (('paddr', 32), ('pstrb', 4), ('psel', 1)):
        bits = g.binding_bits(n.scopes[CPU_BLACKBOX], n.cells[CPU_BLACKBOX]['ports'][port])
        require(len(bits) == width, 'declared CPU output bus width changed: ' + port)
        for bit, local in enumerate(bits):
            net = n.canonical(n.scopes[CPU_BLACKBOX], local)
            require(not g.drivers[net] and net not in g.high | g.low,
                    'CPU APB output cut has another driver/constant: ' + port)
            buses['CPU/' + port + '[' + str(bit) + ']'] = net
    resolved = {**states, **buses}
    require(len(resolved) == len(set(resolved.values())),
            'named state/CPU input cuts alias')
    return resolved


def _source(n, *, role):
    g = Graph(n)
    registers = g.group(SCOPE, 'p_release', 3)
    final_q = n.pin(registers[2], 'Q')
    closure = complete_closure(n, g, [registers[2]])
    require(len(closure['ff_endpoints']) == 403 and
            all(pin.endswith('/CLEAR') and clock == 'ram_clk'
                for pin, clock in closure['ff_endpoints'].items()),
            'source complete FF pin/clock inventory changed')
    require(not closure['top_output_endpoints'], 'unreviewed source top output')
    opaque = {CPU_BLACKBOX + '/' + pin for pin in OPAQUE_PINS[role]}
    require(set(closure['primitive_endpoints']) == opaque and
            all(row == dict(kind='RiscV_AE350_SOC', clock_pins={})
                for row in closure['primitive_endpoints'].values()),
            'source opaque primitive pin inventory changed')
    common = n.pin(registers[0], 'CLEAR')
    for index, path in enumerate(registers):
        zero_async_ff(n, path, clock='ram_clk', clear=common)
        require(n.pin(path, 'CE') in g.high and
                (n.pin(path, 'D') in g.high if index == 0 else
                 n.pin(path, 'D') == n.pin(registers[index - 1], 'Q')),
                'release shift/fill/enable changed')
        if index < 2:
            early = complete_closure(n, g, [path])
            require(early['ff_endpoints'] == {registers[index + 1] + '/D': 'ram_clk'} and
                    not early['primitive_endpoints'] and not early['top_output_endpoints'],
                    'early release extra/bypassed consumer')
    bd = BooleanDiagram([final_q])
    resets = []
    for endpoint in closure['ff_endpoints']:
        path = endpoint.rsplit('/', 1)[0]
        clear = n.pin(path, 'CLEAR')
        zero_async_ff(n, path, clock='ram_clk', clear=clear)
        require(g.support(clear) == {final_q} and
                bd.net(g, clear) == bd.invert(bd.inputs[final_q]),
                'consumer async CLEAR is not exact final release inverse: ' + path)
        resets.append(path)
    inputs = _inputs(n, g)
    ordered = sorted(inputs)
    diagram = BooleanDiagram([inputs[label] for label in ordered])
    cones = []
    for pin in OPAQUE_PINS[role]:
        net = n.pin(CPU_BLACKBOX, pin)
        support = g.support(net, cuts=tuple(inputs.values()))
        require(support <= set(inputs.values()), 'unreviewed opaque cone leaf')
        function = diagram.net(g, net)
        require(function not in (0, 1), 'opaque cone is Boolean constant')
        cones.append(dict(pin=CPU_BLACKBOX + '/' + pin, net=net,
                          inputs=sorted(label for label in ordered if inputs[label] in support),
                          function=function))
    return dict(graph=g, closure=closure, reset_registers=resets,
                release_registers=registers, inputs=inputs,
                diagram=diagram, cones=cones)


def audit(n, *, reference):
    """Compare actual batch VG to actual historical source-sealed VG.

    The historical seal is a prerequisite and remains unchanged. The result
    cannot authorize replacing any complete production consumer seal.
    """
    old = _source(reference, role='historical')
    require(closure_identity(old['closure']) == PAIRED_CPU_SOURCE_CLOSURE,
            'actual historical source closure does not match its frozen seal')
    new = _source(n, role='batch')
    require(new['closure']['ff_endpoints'] == old['closure']['ff_endpoints'],
            'complete actual 403 FF reset endpoints differ from historical source')
    require(set(new['inputs']) == set(old['inputs']), 'opaque cone input identities changed')
    proofs = []
    for before, after in zip(old['cones'], new['cones']):
        require(before['inputs'] == after['inputs'] and
                _same_boolean(old['diagram'], before['function'],
                              new['diagram'], after['function']),
                'opaque CPU input Boolean function changed: ' + after['pin'])
        proofs.append(dict(historical_pin=before['pin'], batch_pin=after['pin'],
                           actual_named_inputs=after['inputs'],
                           input_assignments_proven=1 << len(after['inputs']),
                           input_cone_boolean_equivalence=True,
                           opaque_CPU_internal_pin_role_proven=False))
    return dict(policy=POLICY, historical_source_seal=PAIRED_CPU_SOURCE_CLOSURE,
                historical_seal_changed=False,
                actual_batch_closure_sha256=closure_identity(new['closure']),
                source_release_registers=new['release_registers'],
                actual_reset_registers=new['reset_registers'],
                complete_actual_FF_reset_endpoints_identical=True,
                FF_async_clear_count=403, all_FF_async_clear_inverse_final_release=True,
                all_FF_reset_values_zero=True, all_FF_reset_clocks='ram_clk',
                early_release_consumers_only_next_D=True,
                opaque_CPU_input_cones=proofs,
                comparison_input_registers=sorted(new['inputs']),
                sequential_state_equivalence_proven=False,
                opaque_CPU_internal_pin_roles_proven=False,
                downstream_business_next_Q_proven=False,
                complete_destination_release_consumers_proven=False,
                whole_business_CDC_accepted=False,
                physical_CDC_accepted=False, hardware_tested=False)
