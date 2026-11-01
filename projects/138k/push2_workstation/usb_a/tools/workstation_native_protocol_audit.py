"""Partial structural proof for the native runtime's existing mailbox SDC.

This audits real synthesis/routed cells, including the display held registers
absorbed into registered RAM reads. It emits no RTL or timing exceptions and
does not certify the remaining CDC inventory, routed timing or hardware.
"""
from pathlib import Path
import argparse
import bisect
import fnmatch
import hashlib
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.workstation_runtime_pcm_cdc import BooleanDiagram, Graph, PcmNetlist
from tools.workstation_synthesis_netlist import IDENTIFIER, SynthesisNetlist
from tools.workstation_runtime_profile import protocol_constraints
from tools.workstation_recording_phase1_cdc import complete_closure

TOP = 'workstation_custom_138k_top'
POLICY = 'native-demo-mailbox-structure-v3'
RAM_SCOPE = 'u_managed/observation/frames/'
RAM_STEM = 'g_small_head.memory_g_small_head.memory_0_'
STREAM_SHA256 = '90cb55acd6f83965d74b843993bed625d121ae2eefafbd928eb6fececb6e5376'
PROFILES = ('m-demo-base', 'm-demo-core', 'w-demo-d', 'm-task3-direct')
DELAY = 'u_managed/runtime/service/workstation/runtime_effects.effects/delay_stage'
DMA = 'u_managed/runtime/delay_dma'
APB = 'u_managed/control_cdc'
REVIEWED_BOUNDARY_SOURCES = {
    'rtl/audio/delay_ddr/workstation_runtime_delay_effect_ddr.sv':
        'f1366c86f721e0ac1befb2ccc84e1532528201c1eafb9b1b9ff45c8a01d1eca3',
    'rtl/audio/delay_ddr/workstation_runtime_delay_ddr_dma.sv':
        '4486bddae55e89c191cace04fdfad6163b71af9a1c43b5369e8fabc0d7e42551',
    'rtl/tf_audio/workstation_tf_runtime_service.sv':
        '9dce45ba47ed58314ce4d30a308b6869bbcb815d382777ec868e936cab3fc848',
    'rtl/tf_audio/workstation_tf_frame_bridge.sv':
        'c32000172587a674708d9454b1895b24ada26103d55206b0bda659817bcb4ac5',
}


def require(condition, message):
    if not condition:
        raise ValueError('native protocol audit: ' + message)


def audit_native_protocol(n, *, profile, mapping='synthesis'):
    require(profile in PROFILES, 'unknown role/profile')
    require(mapping in ('synthesis', 'routed'), 'unknown native mapping')
    g = Graph(n)
    domains = dict(control='clk_50m', compute='audio_clk', memory='memory_clk', selected='dac_mclk_d')
    ordinary = 41 if profile == 'w-demo-d' else 73
    # Preserve the old inventories unless the separately named DIRECT owner
    # is selected. Its applied-parameter mailbox uses the exact M25 reviewed
    # 60-bit mapping; do not import unrelated W/headless policy changes.
    direct = profile == 'm-task3-direct'
    hmi = direct and any(p.startswith('u_video/u_applied_parameters_cdc/') for p in n.cells)
    require(not direct or hmi, 'DIRECT applied-parameter mailbox missing')
    hmi_bits = (*range(3, 18), *range(32, 54), *range(67, 80), *range(88, 96), 104, 128) if hmi else ()
    display_extra = tuple(203 + bit for bit in hmi_bits if bit < 128)
    old_display_bits = (*range(ordinary), *range(105, 203))
    display_bits = (*old_display_bits, *display_extra)
    specifications = (
        ('u_managed/pc_bytes', tuple(range(8)), 8, 'control', 'compute'),
        ('u_managed/health_snapshot', tuple(range(32, 64)), 32, 'selected', 'compute'),
        ('u_managed/display', display_bits, display_bits if direct else tuple(range(ordinary)), 'compute', 'control'),
        ('u_video/u_runtime_display/observation', (*old_display_bits, 203), len(old_display_bits) + 1,
         'control', 'memory'),
    )
    if hmi:
        specifications += (('u_video/u_applied_parameters_cdc', hmi_bits, hmi_bits, 'control', 'memory'),)
    proofs, mailboxes = [], []

    def regs(scope, stem, bits):
        found = {}
        for p in g.regs:
            m = re.fullmatch(re.escape(scope + '/' + stem) + r'_(\d+)_s\d+', p)
            if m:
                require(int(m[1]) not in found, 'duplicate bit: ' + p)
                found[int(m[1])] = p
        require(set(found) == set(bits), 'register bit inventory changed: ' + scope + '/' + stem)
        return found

    def clock(p, domain):
        require(n.pin(p, 'CLK') == domains[domain], 'clock changed: ' + p)

    def unconditional(p, domain):
        clock(p, domain)
        require(n.cells[p]['kind'] == 'DFFCE' and n.pin(p, 'CE') in g.high,
                'synchronizer primitive/CE changed: ' + p)

    def chain(scope, source, first, second, source_domain, destination_domain):
        source, first, second = (g.register(scope, x) for x in (source, first, second))
        clock(source, source_domain)
        for p in (first, second):
            unconditional(p, destination_domain)
        require(n.pin(first, 'CLEAR') == n.pin(second, 'CLEAR'), 'chain reset changed: ' + first)
        require(n.pin(first, 'D') == n.pin(source, 'Q') and
                n.pin(second, 'D') == n.pin(first, 'Q'), 'synchronizer bypass/disconnect: ' + first)
        require(set(g.closure([first])['endpoints']) == {second + '/D'},
                'first-stage fanout changed: ' + first)
        return dict(source=source + '/Q', first=first + '/D', second=second + '/D',
                    first_stage_fanout_only_second=True, second_stage_normally_timed=True)

    def common_ce(rows, label):
        values = {n.pin(p, 'CE') for p in rows}
        require(len(values) == 1, 'capture enable differs: ' + label)
        return next(iter(values))

    for scope, bits, held_width, source_domain, destination_domain in specifications:
        request = chain(scope, 'request_toggle', 'req_meta', 'req_sync', source_domain, destination_domain)
        acknowledge = chain(scope, 'acknowledge_toggle', 'ack_meta', 'ack_sync', destination_domain, source_domain)
        settled, sync = g.register(scope, 'req_settled'), g.register(scope, 'req_sync')
        unconditional(settled, destination_domain)
        require(n.pin(settled, 'D') == n.pin(sync, 'Q') and
                n.pin(settled, 'CLEAR') == n.pin(sync, 'CLEAR') and
                set(g.closure([sync])['endpoints']) == {settled + '/D'},
                'third request stage bypass/fanout: ' + scope)
        held_bits = held_width if isinstance(held_width, tuple) else bits
        held, destination = regs(scope, 'held_data', held_bits), regs(scope, 'destination_data', bits)
        for p in held.values():
            clock(p, source_domain)
        for p in destination.values():
            clock(p, destination_domain)
        source_ce, capture_ce = common_ce(held.values(), scope), common_ce(destination.values(), scope)
        request_reg, ack_reg = g.register(scope, 'request_toggle'), g.register(scope, 'acknowledge_toggle')
        require(n.pin(ack_reg, 'D') == n.pin(settled, 'Q') and n.pin(ack_reg, 'CE') == capture_ce,
                'ACK must capture the settled request with the payload: ' + scope)
        # Preserve the actual acceptance gate. Its two other inputs are local
        # release/valid boundaries; do not abstract either ACK or request.
        drivers = g.drivers[source_ce]
        require(len(drivers) == 1, 'acceptance gate driver ambiguous: ' + scope)
        gate, output = drivers[0]
        gate_kind = n.cells[gate]['kind']
        require(gate_kind in ('LUT3', 'LUT4') and output == 'F', 'acceptance gate shape changed: ' + scope)
        leaves = [n.pin(gate, 'I' + str(i)) for i in range(int(gate_kind[3:]))]
        req, ack_sync = n.pin(request_reg, 'Q'), n.pin(g.register(scope, 'ack_sync'), 'Q')
        require(req in leaves and ack_sync in leaves and len(set(leaves)) == len(leaves),
                'acceptance must depend on request and returned ACK: ' + scope)
        bd = BooleanDiagram(leaves)
        accepted = bd.net(g, source_ce)
        equal = bd.invert(bd.different(bd.inputs[req], bd.inputs[ack_sync]))
        require(bd.both(accepted, bd.invert(equal)) == 0,
                'payload can overwrite while request awaits ACK: ' + scope)
        require(bd.net(g, n.pin(request_reg, 'D')) == bd.different(bd.inputs[req], accepted) and
                n.pin(request_reg, 'CE') in g.high,
                'request must toggle exactly with held capture: ' + scope)
        req_settled, ack = n.pin(settled, 'Q'), n.pin(ack_reg, 'Q')
        capture = BooleanDiagram([req_settled, ack])
        require(capture.net(g, capture_ce) == capture.different(capture.inputs[req_settled], capture.inputs[ack]),
                'payload capture must follow third request stage: ' + scope)
        sources = {}
        for bit, p in held.items():
            require(n.pin(destination[bit], 'D') == n.pin(p, 'Q'), 'held payload bit mapping changed: ' + p)
            require(g.drivers[n.pin(p, 'Q')] == [(p, 'Q')], 'held payload has competing driver: ' + p)
            sources[bit] = p + '/Q'
        ram_proof = []
        if scope == 'u_managed/display' and not direct:
            ram_cells = [p for p, c in n.cells.items() if c['kind'] == 'SDPX9B' and p.startswith(RAM_SCOPE)]
            prefixes = ('',) if mapping == 'synthesis' else ('', 'gowin_add_SDPX9B_')
            width = '36' if mapping == 'synthesis' else '18'
            require(set(ram_cells) == {RAM_SCOPE + prefix + RAM_STEM + str(i) + '_s'
                    for prefix in prefixes for i in range(3)},
                    'display registered RAM inventory changed')
            ram_drivers = {}
            for p in ram_cells:
                c = n.cells[p]
                require(c['parameters'].get('READ_MODE') == "1'b0" and
                        c['parameters'].get('BIT_WIDTH_0') == c['parameters'].get('BIT_WIDTH_1') == width and
                        c['parameters'].get('RESET_MODE') == '"SYNC"' and
                        n.pin(p, 'CLKB') == domains[source_domain] and n.pin(p, 'CLKA') == domains['selected'] and
                        n.pin(p, 'CEB') == source_ce and n.pin(p, 'RESET') in g.low and n.pin(p, 'OCE') in g.low,
                        'display RAM read register clock/mode/acceptance changed: ' + p)
                for port in ('BLKSELA', 'BLKSELB'):
                    binding = c['ports'][port]
                    require(all(n.canonical(n.scopes[p], x) in g.low for x in g.binding_bits(n.scopes[p], binding)),
                            'display RAM block select changed: ' + p)
                binding = c['ports']['DO']
                # An escaped flat vector may contain spaces before its bit
                # select. Expand concat members right-to-left explicitly;
                # retain low-to-high bits inside each vector member.
                members = (binding[1:-1] if binding.startswith('{') else binding).split(',')
                out_bits = [bit for member in reversed(members)
                            for bit in g.binding_bits(n.scopes[p], member.strip())]
                require(len(out_bits) == 36, 'RAM DO width changed: ' + p)
                for physical_bit, net in enumerate(out_bits):
                    net = n.canonical(n.scopes[p], net)
                    ram_drivers.setdefault(net, []).append((p, physical_bit))
                ram_proof.append(dict(cell=p, output='DO', clock='CLKB', read_mode=0, bit_width=int(width),
                    synchronous_read_register=True, ce_is_mailbox_acceptance=True))
            for bit in range(105, 203):
                net = n.pin(destination[bit], 'D')
                drivers = ram_drivers.get(net, [])
                require(len(drivers) == 1 and not g.drivers[net],
                        'RAM payload must have one registered DO and no competing driver: ' + str(bit))
                p, physical_bit = drivers[0]
                require(physical_bit < int(width), 'RAM payload uses an unimplemented/padding output bit: ' + str(bit))
                require({(q, pin, role) for q, pin, role in g.fan[net] if (q, pin) != (p, 'DO')} ==
                        {(destination[bit], 'D', 'ff')},
                        'RAM payload destination fanout changed: ' + str(bit))
                sources[bit] = p + '/DO[' + str(physical_bit) + ']'
        require(set(sources) == set(bits), 'payload source closure incomplete: ' + scope)
        mailboxes.append(dict(scope=scope, request=request, acknowledge=acknowledge,
            third_request_stage=settled + '/D', source_clock=domains[source_domain],
            destination_clock=domains[destination_domain], source_enable=source_ce, capture_enable=capture_ce,
            held_ff_bits=len(held), registered_ram_bits=len(bits) - len(held), payload_bits=len(bits),
            payload_sources={str(bit): sources[bit] for bit in bits}, ram=ram_proof,
            source_busy_prevents_overwrite=True, request_toggles_on_capture=True,
            minimum_request_pipeline_stages=3, destination_ack_and_payload_capture_share_enable=True))

    health = 'u_managed/display_observation_health'
    for bit, count_scope, count_stem in ((0, 'u_managed/observation/drops', 'sync_value'),
                                        (1, 'u_managed/display', 'drop_count')):
        sticky = g.register(health, 'source_sticky', bit)
        first, second = g.register(health, 'loss_meta', bit), g.register(health, 'loss_sync', bit)
        unconditional(sticky, 'compute')
        for p in (first, second):
            unconditional(p, 'control')
        require(n.pin(second, 'D') == n.pin(first, 'Q') and
                set(g.closure([first])['endpoints']) == {second + '/D'}, 'loss synchronizer bypass/fanout')
        counters = regs(count_scope, count_stem, range(32))
        for p in counters.values():
            clock(p, 'compute')
        leaves = [n.pin(sticky, 'Q'), *(n.pin(p, 'Q') for p in counters.values())]
        bd = BooleanDiagram(leaves)
        expected = 0
        for leaf in leaves:
            expected = bd.either(expected, bd.inputs[leaf])
        require(bd.net(g, n.pin(first, 'D')) == expected and bd.net(g, n.pin(sticky, 'D')) == expected,
                'loss must retain sticky OR all nonzero counter bits, including final source-stop drop')
        proofs.append(dict(level=first + '/D', source_bits=leaves, sticky_or_nonzero_exact=True,
                           first_drop_without_next_compute_edge_preserved=True, second_stage=second + '/D'))
    if profile == 'm-demo-base':
        proofs.append(chain('u_tf_audio', 'memory_quiet', 'memory_quiet_sync_0', 'memory_quiet_sync_1',
                            'memory', 'control'))
    elif direct:
        from tools.workstation_task3_native_held import audit_direct_tf_owner
        proofs.append(audit_direct_tf_owner(n))
    else:
        require(not any(p.startswith('u_tf_audio/') for p in n.cells), 'TF-disabled profile retained TF owner')
    controls = audit_control_boundaries(n, g, profile=profile)
    timing = audit_timing_boundaries(n, g, profile=profile)
    return dict(schema=1, policy=POLICY, profile=profile, mapping=mapping, mailbox_count=len(mailboxes),
                mailboxes=mailboxes, level_proofs=proofs, control_boundaries=controls,
                timing_boundaries=timing, exact_payload_driver_closure=True,
                source_stop_loss_bypass_preserved=True, constraints_complete=False,
                routed_timing_verified=False, physical_cdc_accepted=False, hardware_tested=False)


def audit_demo_held_boundaries(n, result):
    """Extra closure required only by the explicit DEMO v2 timing owner.

    Reuse the existing mailbox/APB Boolean state proofs. Custom PC reset is
    power-up only; reusable module reset simulation is separate evidence.
    """
    require(result['profile'] != 'm-task3-direct',
            'DIRECT root reset requires its explicit held-boundary proof')
    g = Graph(n)
    scope = 'u_managed/pc_bytes'
    pc = next(row for row in result['mailboxes'] if row['scope'] == scope)
    held, captured = (g.group(scope, stem, 8) for stem in ('held_data', 'destination_data'))
    closure = complete_closure(n, g, held)
    require(closure['ff_endpoints'] == {p + '/D': 'audio_clk' for p in captured} and
            not closure['primitive_endpoints'] and not closure['top_output_endpoints'],
            'DEMO PC held payload exact consumer closure changed')
    reset_rows = []
    for p in sorted(p for p in g.regs if p.startswith(scope + '/')):
        cell = n.cells[p]
        require(cell['kind'] in ('DFFCE', 'DFFRE'), 'DEMO PC reset primitive changed')
        pin = 'CLEAR' if cell['kind'] == 'DFFCE' else 'RESET'
        require(n.pin(p, pin) in g.low and cell['parameters'].get('INIT', "1'b0") == "1'b0",
                'DEMO PC inactive reset or zero power-up INIT changed: ' + p)
        reset_rows.append(dict(register=p, primitive=cell['kind'], reset_pin=pin,
                               inactive_reset=n.pin(p, pin), effective_init=0))
    require(not any(re.search(r'/(source|destination)_release_', row['register']) for row in reset_rows),
            'DEMO PC raw-button release unexpectedly retained')
    chains = []
    for name in ('request', 'acknowledge'):
        chain = pc[name]
        first, second = (chain[key].rsplit('/', 1)[0] for key in ('first', 'second'))
        fanout = complete_closure(n, g, [first])
        require(fanout['ff_endpoints'] == {second + '/D': n.pin(second, 'CLK')} and
                not fanout['primitive_endpoints'] and not fanout['top_output_endpoints'],
                'DEMO PC first-stage complete consumer closure changed')
        chains.append(dict(chain, closure=fanout))
    apb = result['timing_boundaries']['apb_response']
    resets = {}
    for side, stem, clock, controls, groups in (
            ('source', 'p_release', 'ram_clk',
             ('request_toggle', 'state_0', 'state_1', 'ack_meta', 'ack_sync', 'ack_settled'),
             (('request_held', 49), ('response_local', 33))),
            ('destination', 'a_release', 'audio_clk',
             ('acknowledge_toggle', 'req_meta', 'req_sync', 'req_settled', 'request_decoded'),
             (('request_local', 49), ('response_held', 33)))):
        release = g.group(APB, stem, 3)
        require(all(n.canonical('', n.pin(p, 'CLK')) == clock and n.pin(p, 'CE') in g.high and
                    n.cells[p]['kind'] == 'DFFCE' for p in release), 'DEMO APB release clock/CE/primitive changed')
        require(n.pin(release[0], 'D') in g.high and
                all(n.pin(release[i], 'D') == n.pin(release[i - 1], 'Q') for i in (1, 2)) and
                len({n.pin(p, 'CLEAR') for p in release}) == 1, 'DEMO APB release bypass/assertion changed')
        owners = [g.register(APB, s) for s in controls]
        owners += [p for name, width in groups for p in g.group(APB, name, width)]
        require(all(n.cells[p]['kind'] == 'DFFCE' and
                    n.cells[p]['parameters'].get('INIT', "1'b0") == "1'b0" for p in owners + release) and
                len({n.pin(p, 'CLEAR') for p in owners}) == 1, 'DEMO APB shared payload/control reset or INIT changed')
        proof = g.equivalent('DEMO APB ' + side + ' reset inverse third release',
            [n.pin(owners[0], 'CLEAR'), n.pin(release[2], 'Q')], lambda x: x[0] == 1 - x[1])
        resets[side] = dict(release=release, shared_assertion=n.pin(release[0], 'CLEAR'),
                            affected_registers=len(owners), proof=proof)
    require(resets['source']['shared_assertion'] == resets['destination']['shared_assertion'],
            'DEMO APB source/destination common assertion differs')
    resets['common_assertion_proof'] = g.equivalent('DEMO APB common assertion inverse preset_n',
        [resets['source']['shared_assertion'], 'preset_n'], lambda x: x[0] == 1 - x[1], cuts=('preset_n',))
    return dict(pc_source_pins=[p + '/Q' for p in held], pc_capture_pins=[p + '/D' for p in captured],
        pc_payload_closure=closure, pc_chains=chains, pc_actual_reset=dict(mode='custom_top_power_up_only',
            runtime_reset_supported=False, registers=reset_rows, reusable_reset_simulation=False),
        apb_request_source_pins=[p + '/Q' for p in g.group(APB, 'request_held', 49)],
        apb_request_capture_pins=[p + '/D' for p in g.group(APB, 'request_local', 49)],
        apb_resets=resets, new_chains=[chains[0], *apb['chains']], max_delay_ns=13.020,
        pc_minimum_receiving_capture_edge=4, apb_request_minimum_receiving_capture_edge=3,
        physical_timing_verified=False, hardware_tested=False)


def protocol_netlist(text, *, mapping):
    if mapping == 'synthesis':
        return PcmNetlist(text, TOP)
    # The shared parser accepts Gowin's routed `.DO({...}));` same-line
    # terminators. The stricter PCM adapter currently assumes a closing line
    # of its own. Do not rewrite VO or relax that separate auditor: inspect
    # every local protocol primitive with a complete strict named-port lexer.
    n = SynthesisNetlist(text, TOP)
    prefixes = ('u_managed/pc_bytes/', 'u_managed/health_snapshot/', 'u_managed/display/',
                'u_video/u_runtime_display/observation/', 'u_video/u_applied_parameters_cdc/', RAM_SCOPE,
                'u_managed/display_observation_health/', 'u_tf_audio/', 'u_managed/pc_',
                APB + '/', DELAY + '/', DMA + '/')
    expected = {p for p, c in n.cells.items() if c['kind'] not in n.modules and p.startswith(prefixes)}
    require('' in n.frames and len(n.frames) == 1, 'routed mapping must be flat')
    instances = re.compile(r'^[ \t]*(' + IDENTIFIER + r')[ \t]+(' + IDENTIFIER + r')[ \t]*\((.*?)\);', re.M | re.S)
    ports = re.compile(r'\.(?:(\\[^\s]+)[ \t]+|([A-Za-z_$][A-Za-z0-9_$]*))\s*\(\s*([^()]*?)\s*\)')
    seen, port_count = set(), 0
    for match in instances.finditer(text):
        p = match[2].removeprefix('\\')
        if p not in expected:
            continue
        require(p not in seen, 'routed lexical duplicate primitive: ' + p)
        seen.add(p)
        bindings = {}
        for port in ports.finditer(match[3]):
            key = (port[1] or port[2]).removeprefix('\\')
            require(key not in bindings, 'routed lexical duplicate port: ' + p + '/' + key)
            bindings[key] = port[3].strip()
            port_count += 1
        require(not ports.sub('', match[3]).strip(' \t\r\n,'), 'routed unparsed local port: ' + p)
        require(bindings == n.cells[p]['ports'], 'routed lexical/parser disagreement: ' + p)
    require(seen == expected, 'routed lexical local primitive inventory incomplete')
    n.protocol_lexical_audit = dict(local_primitive_count=len(seen), named_port_count=port_count,
        complete_local_named_port_parse=True, original_bytes_rewritten=False, global_parser_modified=False)
    return n


def audit_control_boundaries(n, g, *, profile):
    """Exact maintained TF one-outstanding control and registered PC levels."""
    def register(scope, stem, bit=None):
        return g.register(scope, stem, bit)

    def sync(scope, source, first, second, origin, destination):
        source, first, second = (register(scope, stem) for stem in (source, first, second))
        require(n.pin(source, 'CLK') == origin, 'control source clock changed: ' + source)
        for p in (first, second):
            require(n.cells[p]['kind'] == 'DFFCE' and n.pin(p, 'CLK') == destination and n.pin(p, 'CE') in g.high,
                    'control synchronizer clock/primitive/CE changed: ' + p)
        require(n.pin(first, 'CLEAR') == n.pin(second, 'CLEAR') and
                n.pin(first, 'D') == n.pin(source, 'Q') and n.pin(second, 'D') == n.pin(first, 'Q'),
                'control synchronizer direct connection/reset changed: ' + first)
        require(set(g.closure([first])['endpoints']) == {second + '/D'},
                'control synchronizer first-stage fanout changed: ' + first)
        return dict(source=source + '/Q', first=first + '/D', second=second + '/D')

    tf = None
    if profile == 'm-demo-base':
        scope = 'u_tf_audio'
        reg = lambda stem: register(scope, stem)
        q = lambda stem: n.pin(reg(stem), 'Q')
        held, capture = g.group(scope, 'held_control', 36), g.group(scope, 'compute_control', 36)
        require(all(n.pin(p, 'CLK') == 'clk_50m' for p in held) and
                all(n.pin(p, 'CLK') == 'audio_clk' for p in capture), 'TF control payload clock changed')
        require(all(n.pin(d, 'D') == n.pin(s, 'Q') for s, d in zip(held, capture)), 'TF held payload bit mapping changed')
        enables = {n.pin(p, 'CE') for p in held}
        require(len(enables) == 1, 'TF held payload acceptance enable differs')
        enable = next(iter(enables))
        require(len(g.drivers[enable]) == 1, 'TF control acceptance driver absent/ambiguous')
        gate, port = g.drivers[enable][0]
        require(n.cells[gate]['kind'] == 'LUT3' and port == 'F', 'TF control acceptance gate shape changed')
        leaves = [n.pin(gate, 'I' + str(i)) for i in range(3)]
        request, ack = q('control_request'), n.pin(register(scope, 'ack_sync', 1), 'Q')
        require(request in leaves and ack in leaves and len(set(leaves)) == 3, 'TF control acceptance inputs changed')
        changed = next(x for x in leaves if x not in (request, ack))
        pairs = g.inequality_chain(changed)
        require(len(pairs) == 36 and pairs == {frozenset((n.pin(p, 'Q'), n.pin(p, 'D'))) for p in held},
                'TF held/desired comparison must include every exact payload bit')
        bd = BooleanDiagram(leaves)
        accepted = bd.both(bd.invert(bd.different(bd.inputs[request], bd.inputs[ack])), bd.inputs[changed])
        require(bd.net(g, enable) == accepted, 'TF acceptance must require returned ACK and changed payload')
        require(n.pin(reg('control_request'), 'CE') in g.high and
                bd.net(g, n.pin(reg('control_request'), 'D')) == bd.different(bd.inputs[request], accepted),
                'TF request must toggle exactly with payload capture')
        request_sync = n.pin(register(scope, 'request_sync', 1), 'Q')
        capture_q, ack_q = q('control_capture'), q('control_ack')
        bd = BooleanDiagram([request_sync, capture_q, ack_q])
        settled = bd.both(bd.invert(bd.inputs[capture_q]), bd.different(bd.inputs[request_sync], bd.inputs[ack_q]))
        require(n.pin(reg('control_capture'), 'CLK') == 'audio_clk' and n.pin(reg('control_capture'), 'CE') in g.high and
                bd.net(g, n.pin(reg('control_capture'), 'D')) == settled,
                'TF capture must register settled request and clear after capture')
        require(all(n.pin(p, 'CE') == capture_q for p in capture) and
                n.pin(reg('control_ack'), 'CE') == capture_q and n.pin(reg('control_ack'), 'D') == request_sync,
                'TF ACK and payload must share capture enable')
        chains = [sync(scope, 'control_request', 'request_sync_0', 'request_sync_1', 'clk_50m', 'audio_clk'),
                  sync(scope, 'control_ack', 'ack_sync_0', 'ack_sync_1', 'audio_clk', 'clk_50m')]
        closure = g.closure(held)
        remote = {pin for pin, domain in closure['endpoints'].items() if domain != 'clk_50m'}
        require(remote == {p + '/D' for p in capture}, 'TF held payload remote consumer closure changed')
        tf = dict(payload_bits=36, source_pins=[p + '/Q' for p in held], capture_pins=[p + '/D' for p in capture],
                  acceptance_enable=enable, capture_enable=capture_q, minimum_destination_wait_edges=3,
                  held_desired_comparison_all_bits=True, busy_prevents_overwrite=True, request_toggles_on_capture=True,
                  registered_capture_next_q_verified=True, payload_and_ack_share_capture=True,
                  chains=chains, capture_state=reg('control_capture') + '/D', closure=closure,
                  only_remote_consumers_are_exact_36_capture_pins=True)
    levels = []
    for bit, stem in ((0, 'pc_framing_sticky'), (1, 'pc_drop_seen_50')):
        row = sync('u_managed', stem, 'pc_health_meta_' + str(bit), 'pc_health_sync_' + str(bit), 'clk_50m', 'audio_clk')
        source = register('u_managed', stem)
        if bit == 0:
            require(n.pin(source, 'D') in g.high, 'PC framing source must retain sticky-set data')
        else:
            counter = g.group('u_managed/pc_bytes', 'drop_count', 32)
            require(all(n.pin(p, 'CLK') == 'clk_50m' for p in counter), 'PC diagnostic count source clock changed')
            leaves = [n.pin(p, 'Q') for p in counter]
            bd, expected = BooleanDiagram(leaves), 0
            for leaf in leaves:
                expected = bd.either(expected, bd.inputs[leaf])
            require(n.pin(source, 'CE') in g.high and bd.net(g, n.pin(source, 'D')) == expected,
                    'PC drop reduction must be registered before crossing')
        levels.append(dict(**row, source_registered_before_crossing=True, first_stage_only_second_consumer=True))
    return dict(tf_control=tf, pc_health_levels=levels, complete_cdc_accepted=False)


def audit_timing_boundaries(n, g, *, profile):
    """Measured native heartbeat, APB response and TF held quiesce paths.

    Counter arithmetic and stopped-source cancellation retain their reviewed
    source identities and semantic regressions. Netlist proof independently
    closes the actual register, synchronizer and held-response consumers.
    """
    def reg(scope, stem):
        return g.register(scope, stem)

    def clock(p):
        # Hierarchical formal resolution can return a top-level buffer name
        # once; resolve that real IBUF/BUFG alias again before comparison.
        return n.canonical('', n.pin(p, 'CLK'))

    def unconditional(p, domain, kind='DFFCE'):
        require(n.cells[p]['kind'] == kind and clock(p) == domain and n.pin(p, 'CE') in g.high,
                'timing-boundary register clock/primitive/CE changed: ' + p)

    def stages(scope, source, first, second, domain, third=None):
        a, b = reg(scope, first), reg(scope, second)
        for p in (a, b):
            unconditional(p, domain)
        require(n.pin(a, 'D') == n.pin(source, 'Q') and n.pin(b, 'D') == n.pin(a, 'Q') and
                n.pin(a, 'CLEAR') == n.pin(b, 'CLEAR'), 'timing-boundary synchronizer bypass/reset changed: ' + a)
        closure = complete_closure(n, g, [a])
        require(closure['ff_endpoints'] == {b + '/D': n.pin(b, 'CLK')} and
                not closure['primitive_endpoints'] and not closure['top_output_endpoints'],
                'timing-boundary first-stage has another consumer: ' + a)
        result = dict(source=source + '/Q', first=a + '/D', second=b + '/D',
                      first_stage_only_second_consumer=True, second_stage_normally_timed=True)
        if third:
            c = reg(scope, third)
            unconditional(c, domain)
            require(n.pin(c, 'D') == n.pin(b, 'Q') and n.pin(c, 'CLEAR') == n.pin(b, 'CLEAR'),
                    'timing-boundary third synchronizer stage bypass/reset changed: ' + c)
            result['third'] = c + '/D'
        return result

    heartbeats = []
    for origin, destination, source_clock, destination_clock in (
            (DELAY, DMA, 'audio_clk', 'memory_clk'), (DMA, DELAY, 'memory_clk', 'audio_clk')):
        source = reg(origin, 'heartbeat_counter_4')
        unconditional(source, source_clock)
        row = stages(destination, source, 'peer_meta', 'peer_sync', destination_clock)
        closure = complete_closure(n, g, [source])
        remote = {pin for pin, domain in closure['ff_endpoints'].items() if domain != source_clock}
        require(remote == {row['first']} and not closure['primitive_endpoints'] and
                not closure['top_output_endpoints'], 'delay heartbeat remote consumer closure changed')
        row.update(source_clock=source_clock, destination_clock=destination_clock,
                   source_is_registered_counter_bit=4, reviewed_source_counter_width=5,
                   reviewed_source_free_running_increment=True, counter_arithmetic_equivalence_proven=False,
                   exact_remote_consumer=sorted(remote), closure=closure)
        heartbeats.append(row)

    q = lambda stem: n.pin(reg(APB, stem), 'Q')
    request, ack = reg(APB, 'request_toggle'), reg(APB, 'acknowledge_toggle')
    held, capture = g.group(APB, 'response_held', 33), g.group(APB, 'response_local', 33)
    require(clock(request) == 'ram_clk' and clock(ack) == 'audio_clk' and
            all(clock(p) == 'audio_clk' for p in held) and all(clock(p) == 'ram_clk' for p in capture),
            'APB response clock changed')
    source_enables, capture_enables = {n.pin(p, 'CE') for p in held}, {n.pin(p, 'CE') for p in capture}
    require(len(source_enables) == len(capture_enables) == 1, 'APB response payload enable differs')
    source_ce, capture_ce = next(iter(source_enables)), next(iter(capture_enables))
    require(n.pin(ack, 'CE') == source_ce and n.pin(ack, 'D') == q('req_settled') and
            len({n.pin(p, 'CLEAR') for p in (*held, ack)}) == 1,
            'APB ACK and response publication must share edge/reset')
    require(all(n.pin(d, 'D') == n.pin(s, 'Q') for s, d in zip(held, capture)), 'APB response payload bit mapping changed')
    closure = complete_closure(n, g, held)
    require(closure['ff_endpoints'] == {p + '/D': 'ram_clk' for p in capture} and
            not closure['primitive_endpoints'] and not closure['top_output_endpoints'],
            'APB response exact consumer closure changed')
    chains = [stages(APB, request, 'req_meta', 'req_sync', 'audio_clk', 'req_settled'),
              stages(APB, ack, 'ack_meta', 'ack_sync', 'ram_clk', 'ack_settled')]
    # Prove the actual local ready/reset cone. Independent service-ready
    # branches are unrestricted Boolean inputs, a conservative abstraction:
    # no value of any such branch may permit publication after ACK. Do not
    # assume M and W retain the same LUT factorization.
    valid_inputs = {q('req_settled'), q('acknowledge_toggle'), q('request_decoded'),
                    n.pin(reg(APB, 'a_release_2'), 'Q')}
    external_ready = set()

    def local_support(net, active=()):
        if net in g.high | g.low:
            return set()
        require(net not in active, 'APB publication combinational cycle')
        ds = g.drivers[net]
        if not ds or len(ds) == 1 and not ds[0][0].startswith(APB + '/'):
            require(not net.startswith(APB + '/'), 'APB publication local driver missing: ' + net)
            external_ready.add(net)
            return {net}
        require(len(ds) == 1, 'APB publication driver ambiguous: ' + net)
        p, port = ds[0]
        if p in g.regs:
            return {net}
        kind = n.cells[p]['kind']
        require(kind == 'INV' or re.fullmatch('LUT[1-6]', kind), 'APB publication local primitive changed')
        inputs = ['I'] if kind == 'INV' else ['I' + str(i) for i in range(int(kind[3:]))]
        return set().union(*(local_support(n.pin(p, pin), (*active, net)) for pin in inputs))

    leaves = sorted(local_support(source_ce))
    require(valid_inputs.issubset(leaves), 'APB publication must depend on request, ACK, decode and reset')
    bd = BooleanDiagram(leaves)
    expected = bd.all([bd.different(bd.inputs[q('req_settled')], bd.inputs[q('acknowledge_toggle')]),
                       bd.inputs[q('request_decoded')], bd.inputs[n.pin(reg(APB, 'a_release_2'), 'Q')]])
    accepted = bd.net(g, source_ce)
    require(accepted != 0 and bd.both(accepted, bd.invert(expected)) == 0,
            'APB command-valid may publish after ACK or before decode/reset')
    req_sync, req_settled, ack_q = q('req_sync'), q('req_settled'), q('acknowledge_toggle')
    bd = BooleanDiagram([req_sync, req_settled, ack_q])
    decoded = bd.both(bd.invert(bd.different(bd.inputs[req_sync], bd.inputs[req_settled])),
                      bd.different(bd.inputs[req_settled], bd.inputs[ack_q]))
    unconditional(reg(APB, 'request_decoded'), 'audio_clk')
    require(bd.net(g, n.pin(reg(APB, 'request_decoded'), 'D')) == decoded,
            'APB request decode must wait for settled request and outstanding ACK')
    state0, state1, req, ack_settled = q('state_0'), q('state_1'), q('request_toggle'), q('ack_settled')
    toggle_drivers = g.drivers[n.pin(request, 'D')]
    require(len(toggle_drivers) == 1, 'APB request toggle driver ambiguous')
    toggle_gate, output = toggle_drivers[0]
    request_held = g.group(APB, 'request_held', 49)
    request_ces = {n.pin(p, 'CE') for p in request_held}
    require(len(request_ces) == 1 and all(n.cells[p]['kind'] == 'DFFCE' and clock(p) == 'ram_clk' and
                n.pin(p, 'CLEAR') == n.pin(request, 'CLEAR') for p in request_held),
            'APB request payload capture CE/clock/reset differs')
    request_ce = next(iter(request_ces))
    request_local = g.group(APB, 'request_local', 49)
    request_capture_ces = {n.pin(p, 'CE') for p in request_local}
    require(len(request_capture_ces) == 1 and all(n.cells[p]['kind'] == 'DFFCE' and clock(p) == 'audio_clk' and
                n.pin(p, 'CLEAR') == n.pin(reg(APB, 'req_settled'), 'CLEAR') for p in request_local),
            'APB request local payload capture CE/clock/reset differs')
    require(all(n.pin(d, 'D') == n.pin(s, 'Q') for s, d in zip(request_held, request_local)),
            'APB request held/local payload bit mapping changed')
    request_payload_closure = complete_closure(n, g, request_held)
    require(request_payload_closure['ff_endpoints'] == {p + '/D': n.pin(p, 'CLK') for p in request_local} and
            not request_payload_closure['primitive_endpoints'] and not request_payload_closure['top_output_endpoints'],
            'APB request payload exact consumer closure changed')
    request_capture_bd = BooleanDiagram([req_sync, req_settled])
    require(request_capture_bd.net(g, next(iter(request_capture_ces))) ==
            request_capture_bd.different(request_capture_bd.inputs[req_sync], request_capture_bd.inputs[req_settled]),
            'APB request local capture must wait for third request stage')
    require(n.cells[request]['kind'] == 'DFFCE' and clock(request) == 'ram_clk',
            'APB request toggle clock/primitive changed')
    inverse_mapping = None
    if n.cells[toggle_gate]['kind'] == 'LUT4' and output == 'F':
        inputs = [n.pin(toggle_gate, 'I' + str(i)) for i in range(4)]
        require({state0, state1, req}.issubset(inputs) and len(set(inputs)) == 4,
                'APB launch gate input inventory changed')
        launch_inputs = [x for x in inputs if x not in (state0, state1, req)]
        unconditional(request, 'ram_clk')
        launch_mapping = 'unconditional_toggle_xor_lut4'
        launch_drivers = g.drivers[request_ce]
        require(len(launch_drivers) == 1, 'APB request payload CE driver ambiguous')
        launch_gate, launch_output = launch_drivers[0]
        launch_kind = n.cells[launch_gate]['kind']
        require(launch_output == 'F' and launch_kind in ('LUT3', 'LUT4'),
                'APB request payload CE structure changed')
        capture_inputs = [n.pin(launch_gate, 'I' + str(i)) for i in range(int(launch_kind[3:]))]
        if launch_kind == 'LUT3':
            require(set(capture_inputs) == {state0, state1, *launch_inputs},
                    'APB request payload CE shared launch input changed')
        else:
            # M10b duplicates psel&&penable into a LUT2 feeding the toggle
            # LUT4, while payload CE retains the two leaves separately.
            # Prove that exact AND rather than abstracting its output in one
            # cone and accidentally expanding it in the other.
            require({state0, state1}.issubset(capture_inputs) and len(set(capture_inputs)) == 4,
                    'APB split launch CE input inventory changed')
            combined = launch_inputs[0]
            launch_inputs = [x for x in capture_inputs if x not in (state0, state1)]
            require(not set(launch_inputs) & ({req, ack_settled} | g.high | g.low),
                    'APB split launch leaves must be independent')
            combined_drivers = g.drivers[combined]
            require(len(combined_drivers) == 1, 'APB split launch AND driver ambiguous')
            combined_gate, combined_output = combined_drivers[0]
            require(n.cells[combined_gate]['kind'] == 'LUT2' and combined_output == 'F' and
                    n.cells[combined_gate]['parameters'].get('INIT') == "4'h8" and
                    {n.pin(combined_gate, 'I0'), n.pin(combined_gate, 'I1')} == set(launch_inputs),
                    'APB split launch AND function changed')
            launch_mapping = 'unconditional_toggle_xor_lut4_split_launch_and2'
    else:
        # W9b maps exactly the same request update into the DFFCE enable:
        # D=~Q, CE=IDLE && psel && penable. Both launch leaves stay free;
        # neither a candidate signal name nor its sampled value is assumed.
        inverse_mapping = ('INV' if n.cells[toggle_gate]['kind'] == 'INV' and output == 'O' and
                           n.pin(toggle_gate, 'I') == req else
                           'LUT1_exact_2h1' if n.cells[toggle_gate]['kind'] == 'LUT1' and output == 'F' and
                           n.cells[toggle_gate]['parameters'].get('INIT') == "2'h1" and
                           n.pin(toggle_gate, 'I0') == req else None)
        require(inverse_mapping is not None, 'APB request toggle feedback must invert Q')
        require(n.pin(request, 'CE') == request_ce, 'APB request toggle CE differs from payload capture')
        enable_drivers = g.drivers[request_ce]
        require(len(enable_drivers) == 1, 'APB request launch CE driver ambiguous')
        enable_gate, enable_output = enable_drivers[0]
        require(n.cells[enable_gate]['kind'] == 'LUT4' and enable_output == 'F',
                'APB request launch CE must retain exact LUT4 structure')
        inputs = [n.pin(enable_gate, 'I' + str(i)) for i in range(4)]
        require({state0, state1}.issubset(inputs) and len(set(inputs)) == 4,
                'APB request launch CE state/input inventory changed')
        launch_inputs = [x for x in inputs if x not in (state0, state1)]
        require(not set(launch_inputs) & ({req, ack_settled} | g.high | g.low),
                'APB request launch CE leaves must be independent')
        launch_mapping = 'invert_feedback_with_exact_idle_launch_ce'
    bd = BooleanDiagram([state0, state1, req, ack_settled, *launch_inputs])
    launch = bd.all([bd.inputs[x] for x in launch_inputs])
    idle = bd.both(bd.invert(bd.inputs[state0]), bd.invert(bd.inputs[state1]))
    wait = bd.both(bd.inputs[state0], bd.invert(bd.inputs[state1]))
    complete = bd.both(bd.invert(bd.inputs[state0]), bd.inputs[state1])
    equal = bd.invert(bd.different(bd.inputs[req], bd.inputs[ack_settled]))
    captured = bd.both(wait, equal)
    launch_accept = bd.both(idle, launch)
    require(bd.net(g, request_ce) == launch_accept, 'APB request payload can launch outside IDLE')
    request_next = bd.choose(bd.net(g, n.pin(request, 'CE')), bd.net(g, n.pin(request, 'D')), bd.inputs[req])
    require(request_next == bd.different(bd.inputs[req], launch_accept),
            'APB request can launch outside IDLE')
    require(bd.net(g, capture_ce) == captured, 'APB response capture must wait for third ACK stage')
    for stem, expected in (
            ('state_0', bd.either(launch_accept, bd.both(wait, bd.invert(equal)))),
            ('state_1', bd.either(captured, bd.both(complete, bd.invert(launch))))):
        state = reg(APB, stem)
        require(n.cells[state]['kind'] == 'DFFCE' and clock(state) == 'ram_clk' and
                all(n.pin(p, 'CLEAR') == n.pin(state, 'CLEAR') for p in capture), 'APB local state clock/reset changed')
        # Synthesis can move the hold mux into CE. Compare effective next-Q
        # rather than requiring M's unconditional-state implementation.
        next_q = bd.choose(bd.net(g, n.pin(state, 'CE')), bd.net(g, n.pin(state, 'D')), bd.inputs[q(stem)])
        require(next_q == expected, 'APB one-outstanding state transition changed: ' + stem)
    request_closure = complete_closure(n, g, [request])
    request_consumers = {request + '/D': 'ram_clk', reg(APB, 'req_meta') + '/D': 'audio_clk',
                         **{p + '/CE': 'ram_clk' for p in capture}}
    for stem in ('state_0', 'state_1'):
        for port in ('D', 'CE'):
            request_consumers[reg(APB, stem) + '/' + port] = 'ram_clk'
    require(set(request_closure['ff_endpoints']).issubset(request_consumers) and
            all(domain == request_consumers[pin] for pin, domain in request_closure['ff_endpoints'].items()) and
            {request + '/D', reg(APB, 'req_meta') + '/D'}.issubset(request_closure['ff_endpoints']) and
            not request_closure['primitive_endpoints'] and not request_closure['top_output_endpoints'],
            'APB request toggle has an unreviewed consumer')
    response = dict(scope=APB, source_pins=[p + '/Q' for p in held], capture_pins=[p + '/D' for p in capture],
        payload_bits=33, source_clock='audio_clk', destination_clock='ram_clk', source_enable=source_ce,
        capture_enable=capture_ce, chains=chains, source_publication_requires_outstanding_request=True,
        publication_local_boolean_leaf_count=len(leaves),
        publication_unrestricted_service_ready_leaves=sorted(external_ready),
        request_launch_mapping=launch_mapping, request_launch_free_leaves=launch_inputs,
        request_inverse_mapping=inverse_mapping,
        request_next_state_boolean_assignments=1 << len(bd.inputs), request_payload_bits=49,
        request_payload_common_capture_ce_clock_reset=True, request_toggle_consumer_closure=request_closure,
        request_payload_bit_mapping_exact=True, request_payload_consumer_closure=request_payload_closure,
        request_local_capture_on_third_request_stage=True, request_local_capture_common_ce_clock_reset=True,
        response_and_ack_share_publication=True, request_launch_only_idle=True, exact_state_transitions_verified=True,
        minimum_response_pipeline_stages=3, minimum_capture_edge_after_publication=4,
        max_delay_ns=20.0, only_hold_exception=True, closure=closure,
        payload_stable_until_next_request_round_trip=True)

    quiesce = None
    if profile == 'm-demo-base':
        source = reg('u_tf_audio', 'source_quiesce')
        unconditional(source, 'clk_50m', 'DFFPE')
        row = stages('u_tf_audio/frames', source, 'quiesce_sync_0', 'quiesce_sync_1', 'audio_clk')
        closure = complete_closure(n, g, [source])
        remote = {pin for pin, domain in closure['ff_endpoints'].items()
                  if n.canonical('', domain) != 'clk_50m'}
        require(remote == {row['first']} and not closure['top_output_endpoints'], 'TF quiesce remote consumer closure changed')
        require(all(pin.endswith('/WRE') and row['kind'] == 'RAM16SDP4' and
                    row['clock_pins'] == {'CLK': 'clk_50m'} for pin, row in closure['primitive_endpoints'].items()),
                'TF quiesce opaque primitive is not a local FIFO write enable')
        quiesce = dict(**row, source_initially_quiet=True, registered_source_level=True,
            exact_remote_consumer=sorted(remote), local_primitive_endpoints=closure['primitive_endpoints'],
            local_ff_endpoints=len(closure['ff_endpoints']) - 1,
            stopped_source_semantics='held quiesce; combinational invalidate and final Gray generation remain separate',
            stopped_source_regression_required=True)
    return dict(delay_heartbeats=heartbeats, apb_response=response, tf_quiesce=quiesce,
                complete_cdc_accepted=False)


def source_identity(root):
    root = Path(root)
    manifest = json.loads((root / 'vendor/workstation_inputs.json').read_text())
    require(manifest.get('src/migration/gw138k_stream_cdc.sv') == STREAM_SHA256,
            'reviewed stream protocol identity changed')
    require(manifest.get('src/migration/gw138k_apb_cdc.sv') ==
            '61047b3c2be74af1bc96567e2aed37be2d78773cd31364eb6bdb1eb4d9d9409a',
            'reviewed APB input identity changed')
    for name, expected in REVIEWED_BOUNDARY_SOURCES.items():
        require(hashlib.sha256((root / name).read_bytes()).hexdigest() == expected,
                'reviewed heartbeat/quiesce source identity changed: ' + name)
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in (
        'tools/workstation_native_protocol_audit.py', 'tools/workstation_runtime_profile.py',
        'tools/workstation_runtime_pcm_cdc.py', 'tools/workstation_synthesis_netlist.py',
        'tools/workstation_recording_phase1_cdc.py', 'tools/workstation_resource_timing.py',
        'vendor/workstation_inputs.json',
        'rtl/tf_audio/workstation_tf_runtime_service.sv',
        'rtl/workstation/workstation_runtime_controlled.sv', 'rtl/audio/workstation_pcm_observation_bridge.sv',
        'rtl/music/music_async_fifo.sv', *REVIEWED_BOUNDARY_SOURCES)}


def validate_native_protocol_sdc(sdc, n, result, *, demo_held_handshakes=None):
    """Confirm the local installed bounds and protect every subsequent D.

    This is a local pin-selector check. The role audit still owns clock-query
    resolution, other exceptions and complete synthesis/input provenance.
    """
    direct = result['profile'] == 'm-task3-direct'
    direct_scopes = ('u_managed/display/', 'u_video/u_applied_parameters_cdc/')
    mandatory = [line for line in protocol_constraints().splitlines()
                 if (not direct and RAM_SCOPE in line) or 'u_managed/display_observation_health/loss_meta_' in line
                 or 'u_managed/pc_health_meta_' in line
                 or APB + '/response_held_' in line or DELAY + '/' in line or DMA + '/peer_' in line
                 or result['profile'] == 'm-demo-base' and
                    ('u_tf_audio/held_control_' in line or 'u_tf_audio/frames/quiesce_sync_' in line)
                 or direct and RAM_SCOPE not in line and any(scope in line for scope in direct_scopes)]
    require(len(mandatory) == (26 if direct else 20 if result['profile'] == 'm-demo-base' else 16) and
            all(sdc.splitlines().count(line) == 1 for line in mandatory),
            'local RAM/loss/TF/PC/heartbeat/APB constraints missing, duplicated or changed')
    display = next(row for row in result['mailboxes'] if row['scope'] == 'u_managed/display')
    ram_pins = {row['cell'] + '/DO' for row in display['ram']}
    # Both mandatory selectors have fixed local scope prefixes. Index those
    # scopes once so 98 explicit bits never rescan unrelated whole-chip pins.
    all_pins = {p + '/' + port for p, c in n.cells.items()
                if p.startswith((RAM_SCOPE, 'u_managed/display/')) for port in c['ports']}
    matches = lambda body: {p for selector in body.split() for p in all_pins if fnmatch.fnmatchcase(p, selector)}
    captures = {p for p in all_pins if re.fullmatch(r'u_managed/display/destination_data_(\d+)_s\d+/D', p)
                and 105 <= int(re.search(r'destination_data_(\d+)_', p)[1]) <= 202}
    direct_display_bounds, direct_hold, direct_bounded = [], set(), set()
    if direct:
        require(not ram_pins and display['held_ff_bits'] == display['payload_bits'] == 230,
                'DIRECT display must use exact 230 held FFs')
        retired = [line for line in protocol_constraints().splitlines() if RAM_SCOPE in line]
        require(len(retired) == 2 and not any(line in sdc.splitlines() for line in retired),
                'DIRECT retained obsolete RAM-output display constraints')
        full_pins = {p + '/' + port for p, cell in n.cells.items() for port in cell['ports']}
        for scope, width in zip(direct_scopes, (230, 60)):
            mailbox = next(row for row in result['mailboxes'] if row['scope'] == scope[:-1])
            require(mailbox['held_ff_bits'] == mailbox['payload_bits'] == width and not mailbox['ram'],
                    'DIRECT held FF bit inventory changed: ' + scope)
            sources = list(mailbox['payload_sources'].values())
            capture = [pin.rsplit('/', 1)[0].replace('/held_data_', '/destination_data_') + '/D'
                       for pin in sources]
            rows = [line for line in mandatory if scope in line]
            expected = [
                ('set_max_delay 20.000 ', (sources, capture)),
                ('set_false_path -hold ', (sources, capture)),
                ('set_false_path -to ', ([mailbox['request']['first']],)),
                ('set_max_delay 2.000 ', ([mailbox['request']['first'].rsplit('/', 1)[0] + '/Q'],
                                         [mailbox['request']['second']])),
                ('set_false_path -to ', ([mailbox['acknowledge']['first']],)),
                ('set_max_delay 2.000 ', ([mailbox['acknowledge']['first'].rsplit('/', 1)[0] + '/Q'],
                                         [mailbox['acknowledge']['second']]))]
            require(len(rows) == len(expected) == 6, 'DIRECT display/HMI SDC inventory changed')
            for line, (prefix, inventories) in zip(rows, expected):
                bodies = re.findall(r'\[get_pins \{([^}]+)\}\]', line)
                require(line.startswith(prefix) and len(bodies) == len(inventories),
                        'DIRECT display/HMI SDC command/query changed')
                for body, wanted in zip(bodies, inventories):
                    actual = {pin for selector in body.split() for pin in full_pins
                              if fnmatch.fnmatchcase(pin, selector)}
                    require(actual == set(wanted), 'DIRECT display/HMI exact query inventory changed')
                direct_display_bounds.append(line)
            direct_hold.add(rows[1])
            direct_bounded.update(capture)
            direct_bounded.update(mailbox[key]['second'] for key in ('request', 'acknowledge'))
        captures = set()
    else:
        queries = re.findall(r'\[get_pins \{([^}]+)\}\]', mandatory[0])
        require(len(queries) == 2, 'registered RAM constraint query shape')
        require(matches(queries[0]) == ram_pins, 'registered RAM selector resolves outside exact reviewed cells')
        require(len(captures) == 98 and matches(queries[1]) == captures,
                'RAM constraint does not cover exact 98 capture bits')
    protected = {row[key]['second'] for row in result['mailboxes'] for key in ('request', 'acknowledge')}
    protected.update(row['third_request_stage'] for row in result['mailboxes'])
    for row in result['level_proofs']:
        protected.add(row.get('second_stage', row.get('second')))
    controls = result['control_boundaries']
    protected.update(row['second'] for row in controls['pc_health_levels'])
    if controls['tf_control']:
        tf = controls['tf_control']
        protected.update(row['second'] for row in tf['chains'])
        protected.add(tf['capture_state'])
        tf_lines = [line for line in mandatory if 'u_tf_audio/held_control_' in line]
        queries = re.findall(r'\[get_pins \{([^}]+)\}\]', tf_lines[0])
        pins = {p + '/' + port for p, c in n.cells.items() if p.startswith('u_tf_audio/') for port in c['ports']}
        for body, expected in zip(queries, (tf['source_pins'], tf['capture_pins'])):
            actual = {pin for selector in body.split() for pin in pins if fnmatch.fnmatchcase(pin, selector)}
            require(actual == set(expected) and len(actual) == 36, 'TF held constraint source/capture inventory changed')
    timing = result['timing_boundaries']
    apb = timing['apb_response']
    pins = {p + '/' + port for p, c in n.cells.items()
            if p.startswith((APB + '/', DELAY + '/', DMA + '/', 'u_tf_audio/')) for port in c['ports']}

    def exact_queries(line, expected):
        bodies = re.findall(r'\[get_pins \{([^}]+)\}\]', line)
        require(len(bodies) == len(expected), 'timing-boundary SDC query count changed')
        for body, wanted in zip(bodies, expected):
            actual = {pin for selector in body.split() for pin in pins if fnmatch.fnmatchcase(pin, selector)}
            require(actual == set(wanted), 'timing-boundary SDC source/capture inventory changed')

    apb_lines = [line for line in mandatory if APB + '/response_held_' in line]
    require(len(apb_lines) == 2 and apb_lines[0].startswith('set_max_delay 20.000 ') and
            apb_lines[1].startswith('set_false_path -hold '), 'APB response must retain finite setup and waive only hold')
    for line in apb_lines:
        exact_queries(line, (apb['source_pins'], apb['capture_pins']))
    boundary_chains = [*timing['delay_heartbeats'], *([timing['tf_quiesce']] if timing['tf_quiesce'] else [])]
    for row in boundary_chains:
        protected.add(row['second'])
        selected = [line for line in mandatory if row['first'].rsplit('_s', 1)[0] + '_s*/D' in line]
        require(len(selected) == 1 and selected[0].startswith('set_false_path -from '),
                'registered level first-stage exception must name its exact source')
        exact_queries(selected[0], ([row['source']], [row['first']]))
        bound = [line for line in mandatory if row['second'].rsplit('_s', 1)[0] + '_s*/D' in line]
        require(len(bound) == 1 and bound[0].startswith('set_max_delay 2.000 '), 'level second stage lacks 2ns bound')
        exact_queries(bound[0], ([row['first'].rsplit('/', 1)[0] + '/Q'], [row['second']]))
    for row in apb['chains']:
        protected.update((row['second'], row['third']))
    protected.update(apb['capture_pins'])
    protected.update(direct_bounded)
    allowed_hold = {apb_lines[1], *direct_hold}
    demo_resolved = []
    if demo_held_handshakes is not None:
        demo = result.get('demo_held_handshakes')
        require(isinstance(demo, dict), 'selected DEMO held-handshake graph proof absent')
        selected = demo_held_handshakes.splitlines()
        require(len(selected) == 10 and all(sdc.splitlines().count(line) == 1 for line in selected),
                'DEMO held-handshake constraints missing, duplicated or changed')
        pc_ack_lines = [line for line in protocol_constraints().splitlines()
                        if 'u_managed/pc_bytes/ack_meta_' in line]
        require(len(pc_ack_lines) == 2 and all(sdc.splitlines().count(line) == 1 for line in pc_ack_lines),
                'DEMO existing PC ACK constraints missing, duplicated or changed')
        # Resolve every selector over the whole actual netlist: a wider glob
        # retaining the local bits must still fail if it reaches another owner.
        local_pins = sorted(p + '/' + port for p, cell in n.cells.items() for port in cell['ports'])

        def resolved(body):
            actual = set()
            for pattern in body.split():
                prefix = pattern[:next((i for i, char in enumerate(pattern) if char in '*?['), len(pattern))]
                first = bisect.bisect_left(local_pins, prefix)
                last = bisect.bisect_right(local_pins, prefix + '\U0010ffff')
                actual.update(pin for pin in local_pins[first:last] if fnmatch.fnmatchcase(pin, pattern))
            return actual
        expected = []
        for source, capture in ((demo['pc_source_pins'], demo['pc_capture_pins']),
                                (demo['apb_request_source_pins'], demo['apb_request_capture_pins'])):
            expected.extend((('set_max_delay 13.020 ', source, capture),
                             ('set_false_path -hold ', source, capture)))
            protected.update(capture)
        for row in demo['new_chains']:
            expected.extend((('set_false_path ', [row['source']], [row['first']]),
                             ('set_max_delay 2.000 ', [row['first'].rsplit('/', 1)[0] + '/Q'], [row['second']])))
        for line, (prefix, source, capture) in zip(selected, expected):
            require(line.startswith(prefix) and (prefix != 'set_false_path ' or '-hold' not in line),
                    'DEMO payload setup must remain finite; only first-stage toggle setup may be cut')
            bodies = re.findall(r'\[get_pins \{([^}]+)\}\]', line)
            require(len(bodies) == 2 and 'get_clocks' not in line, 'DEMO held-handshake query shape changed')
            for body, wanted in zip(bodies, (source, capture)):
                actual = resolved(body)
                require(actual == set(wanted), 'DEMO held-handshake exact source/capture inventory changed')
            if prefix == 'set_false_path -hold ':
                allowed_hold.add(line)
            demo_resolved.append(dict(constraint=line, source_pins=source, capture_pins=capture))
        # A second, weaker max-delay command must not override the finite
        # payload/second-stage bounds while the mandatory line still exists.
        bounded_targets = set(demo['pc_capture_pins'] + demo['apb_request_capture_pins'] + apb['capture_pins']) | direct_bounded
        bounded_targets.update(row['second'] for row in demo['new_chains'])
        finite_lines = set(selected + apb_lines + pc_ack_lines + direct_display_bounds)
        for raw in sdc.splitlines():
            line = raw.strip()
            if not line.startswith('set_max_delay'):
                continue
            for kind, body in re.findall(r'-to\s+\[(get_pins|get_regs)\s+\{([^}]+)\}\]', line):
                if any(fnmatch.fnmatchcase(pin if kind == 'get_pins' else pin.rsplit('/', 1)[0], pattern)
                       for pattern in body.split() for pin in bounded_targets):
                    require(line in finite_lines, 'DEMO held-handshake finite setup bound overridden')
    protected.discard(None)
    for raw in sdc.splitlines():
        line = raw.strip()
        if not line.startswith('set_false_path'):
            continue
        if demo_held_handshakes is not None and 'get_clocks' in line:
            from tools.workstation_runtime_cdc import MODE_EXCLUSIONS
            require(line in MODE_EXCLUSIONS, 'DEMO held-handshake whole-clock setup cut is forbidden')
        if line in allowed_hold:
            continue
        for kind, body in re.findall(r'-to\s+\[(get_pins|get_regs)\s+\{([^}]+)\}\]', line):
            require(not any(fnmatch.fnmatchcase(pin if kind == 'get_pins' else pin.rsplit('/', 1)[0], selector)
                            for selector in body.split() for pin in protected),
                    'timing exception reaches a later synchronizer/settled stage: ' + line)
    return dict(required_local_lines_installed_once=True, registered_ram_source_pins=sorted(ram_pins),
                exact_98_registered_ram_capture_pins=sorted(captures),
                protected_later_stage_pins=sorted(protected), later_stage_setup_hold_exceptions_absent=True,
                tf_control_payload_pins_verified=bool(controls['tf_control']), pc_health_levels_verified=2,
                apb_response_payload_pins_verified=33, delay_heartbeat_crossings_verified=2,
                demo_held_handshake_constraints=demo_resolved,
                direct_display_hmi_ff_bounds_verified=bool(direct_display_bounds),
                tf_quiesce_first_stage_verified=bool(timing['tf_quiesce']),
                global_clock_exception_audit_complete=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--netlist', type=Path, required=True)
    parser.add_argument('--profile', choices=PROFILES, required=True)
    parser.add_argument('--mapping', choices=('synthesis', 'routed'), default='synthesis')
    parser.add_argument('--sdc', type=Path, help='Optional actual installed role SDC; no timing-engine execution')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source_before = source_identity(ROOT)
    data = args.netlist.read_bytes()
    sdc_data = args.sdc.read_bytes() if args.sdc else None
    netlist = protocol_netlist(data.decode(), mapping=args.mapping)
    result = audit_native_protocol(netlist, profile=args.profile, mapping=args.mapping)
    result['lexical_audit'] = (netlist.lexical_connection_audit if args.mapping == 'synthesis'
                               else netlist.protocol_lexical_audit)
    result.update(netlist=str(args.netlist), netlist_sha256=hashlib.sha256(data).hexdigest(),
                  reviewed_stream_sha256=STREAM_SHA256, maintained_source_sha256=source_before,
                  integration_source_seal_verified=False, installed_sdc_queries_verified=False)
    if args.sdc:
        result['installed_local_sdc'] = validate_native_protocol_sdc(sdc_data.decode(), netlist, result)
        result['installed_sdc_sha256'] = hashlib.sha256(sdc_data).hexdigest()
        result['installed_sdc_queries_verified'] = True
    require(source_before == source_identity(ROOT), 'maintained audit/contract source changed during verification')
    require(data == args.netlist.read_bytes(), 'netlist changed during verification')
    require(not args.sdc or sdc_data == args.sdc.read_bytes(), 'installed SDC changed during verification')
    result['source_seal'] = dict(maintained_source_stable_before_after=True,
        netlist_stable_before_after=True, installed_sdc_stable_before_after=bool(args.sdc),
        scope='audit code, maintained contracts and selected netlist/SDC only; no compilation-input seal')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('policy', 'profile', 'mailbox_count',
          'exact_payload_driver_closure', 'source_stop_loss_bypass_preserved', 'physical_cdc_accepted')}))


if __name__ == '__main__':
    main()
