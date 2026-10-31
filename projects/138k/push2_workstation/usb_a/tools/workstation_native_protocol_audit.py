"""Partial structural proof for the native runtime's existing mailbox SDC.

This audits real synthesis/routed cells, including the display held registers
absorbed into registered RAM reads. It emits no RTL or timing exceptions and
does not certify the remaining CDC inventory, routed timing or hardware.
"""
from pathlib import Path
import argparse
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

TOP = 'workstation_custom_138k_top'
POLICY = 'native-demo-mailbox-structure-v2'
RAM_SCOPE = 'u_managed/observation/frames/'
RAM_STEM = 'g_small_head.memory_g_small_head.memory_0_'
STREAM_SHA256 = '90cb55acd6f83965d74b843993bed625d121ae2eefafbd928eb6fececb6e5376'
PROFILES = ('m-demo-base', 'w-demo-d')


def require(condition, message):
    if not condition:
        raise ValueError('native protocol audit: ' + message)


def audit_native_protocol(n, *, profile, mapping='synthesis'):
    require(profile in PROFILES, 'unknown role/profile')
    require(mapping in ('synthesis', 'routed'), 'unknown native mapping')
    g = Graph(n)
    domains = dict(control='clk_50m', compute='audio_clk', memory='memory_clk', selected='dac_mclk_d')
    ordinary = 73 if profile == 'm-demo-base' else 41
    display_bits = (*range(ordinary), *range(105, 203))
    specifications = (
        ('u_managed/pc_bytes', tuple(range(8)), 8, 'control', 'compute'),
        ('u_managed/health_snapshot', tuple(range(32, 64)), 32, 'selected', 'compute'),
        ('u_managed/display', display_bits, ordinary, 'compute', 'control'),
        ('u_video/u_runtime_display/observation', (*display_bits, 203), len(display_bits) + 1,
         'control', 'memory'),
    )
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
        held_bits = tuple(range(held_width)) if scope.endswith('/display') else bits
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
        if scope == 'u_managed/display':
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
    else:
        require(not any(p.startswith('u_tf_audio/') for p in n.cells), 'W retained retired TF owner')
    controls = audit_control_boundaries(n, g, profile=profile)
    return dict(schema=1, policy=POLICY, profile=profile, mapping=mapping, mailbox_count=len(mailboxes),
                mailboxes=mailboxes, level_proofs=proofs, control_boundaries=controls, exact_payload_driver_closure=True,
                source_stop_loss_bypass_preserved=True, constraints_complete=False,
                routed_timing_verified=False, physical_cdc_accepted=False, hardware_tested=False)


def protocol_netlist(text, *, mapping):
    if mapping == 'synthesis':
        return PcmNetlist(text, TOP)
    # The shared parser accepts Gowin's routed `.DO({...}));` same-line
    # terminators. The stricter PCM adapter currently assumes a closing line
    # of its own. Do not rewrite VO or relax that separate auditor: inspect
    # every local protocol primitive with a complete strict named-port lexer.
    n = SynthesisNetlist(text, TOP)
    prefixes = ('u_managed/pc_bytes/', 'u_managed/health_snapshot/', 'u_managed/display/',
                'u_video/u_runtime_display/observation/', RAM_SCOPE,
                'u_managed/display_observation_health/', 'u_tf_audio/', 'u_managed/pc_')
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


def source_identity(root):
    root = Path(root)
    manifest = json.loads((root / 'vendor/workstation_inputs.json').read_text())
    require(manifest.get('src/migration/gw138k_stream_cdc.sv') == STREAM_SHA256,
            'reviewed stream protocol identity changed')
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in (
        'tools/workstation_native_protocol_audit.py', 'tools/workstation_runtime_profile.py',
        'tools/workstation_runtime_pcm_cdc.py', 'tools/workstation_synthesis_netlist.py',
        'vendor/workstation_inputs.json',
        'rtl/tf_audio/workstation_tf_runtime_service.sv',
        'rtl/workstation/workstation_runtime_controlled.sv', 'rtl/audio/workstation_pcm_observation_bridge.sv',
        'rtl/music/music_async_fifo.sv')}


def validate_native_protocol_sdc(sdc, n, result):
    """Confirm the local installed bounds and protect every subsequent D.

    This is a local pin-selector check. The role audit still owns clock-query
    resolution, other exceptions and complete synthesis/input provenance.
    """
    mandatory = [line for line in protocol_constraints().splitlines()
                 if RAM_SCOPE in line or 'u_managed/display_observation_health/loss_meta_' in line
                 or 'u_managed/pc_health_meta_' in line
                 or result['profile'] == 'm-demo-base' and 'u_tf_audio/held_control_' in line]
    require(len(mandatory) == (12 if result['profile'] == 'm-demo-base' else 10) and
            all(sdc.splitlines().count(line) == 1 for line in mandatory),
            'local RAM/loss/TF/PC constraints missing, duplicated or changed')
    display = next(row for row in result['mailboxes'] if row['scope'] == 'u_managed/display')
    ram_pins = {row['cell'] + '/DO' for row in display['ram']}
    # Both mandatory selectors have fixed local scope prefixes. Index those
    # scopes once so 98 explicit bits never rescan unrelated whole-chip pins.
    all_pins = {p + '/' + port for p, c in n.cells.items()
                if p.startswith((RAM_SCOPE, 'u_managed/display/')) for port in c['ports']}
    queries = re.findall(r'\[get_pins \{([^}]+)\}\]', mandatory[0])
    require(len(queries) == 2, 'registered RAM constraint query shape')
    matches = lambda body: {p for selector in body.split() for p in all_pins if fnmatch.fnmatchcase(p, selector)}
    require(matches(queries[0]) == ram_pins, 'registered RAM selector resolves outside exact reviewed cells')
    captures = {p for p in all_pins if re.fullmatch(r'u_managed/display/destination_data_(\d+)_s\d+/D', p)
                and 105 <= int(re.search(r'destination_data_(\d+)_', p)[1]) <= 202}
    require(len(captures) == 98 and matches(queries[1]) == captures, 'RAM constraint does not cover exact 98 capture bits')
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
    protected.discard(None)
    for line in sdc.splitlines():
        if not line.startswith('set_false_path'):
            continue
        for kind, body in re.findall(r'-to\s+\[(get_pins|get_regs)\s+\{([^}]+)\}\]', line):
            require(not any(fnmatch.fnmatchcase(pin if kind == 'get_pins' else pin.rsplit('/', 1)[0], selector)
                            for selector in body.split() for pin in protected),
                    'timing exception reaches a later synchronizer/settled stage: ' + line)
    return dict(required_local_lines_installed_once=True, registered_ram_source_pins=sorted(ram_pins),
                exact_98_registered_ram_capture_pins=sorted(captures),
                protected_later_stage_pins=sorted(protected), later_stage_setup_hold_exceptions_absent=True,
                tf_control_payload_pins_verified=bool(controls['tf_control']), pc_health_levels_verified=2,
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
