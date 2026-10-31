"""Opt-in DEMO producer-local release for the locked generated event FIFO.

The frozen FIFO and its existing audio reset/drain semantics stay authoritative.
Only four USB-domain reset groups and write admission are adapted. Retire this
exact, identity-checked adapter when an independently verified maintained native
FIFO preserves its memory, output buffer, Gray and cancellation contracts.
"""
from pathlib import Path
import hashlib
import re

FIFO = 'src/usb_host/gw138k_usb_event_fifo.v'
SOURCE = 'rtl/workstation/workstation_fifo_write_reset.sv'
TOOL = 'tools/workstation_usb_fifo_reset.py'
POLICY = 'demo_usb_fifo_producer_local_release_v1'
INPUT_SHA256 = '2084bead34bf421610fd20489ece66601823b87f72887228be25de5374a956c6'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('USB FIFO local-reset exact anchor drift: ' + old[:100])
    return text.replace(old, new, 1)


def changes():
    anchor = "  assign w_rdy = ~ w_full;"
    replacement = '''  wire write_reset, write_ready;
  workstation_fifo_write_reset write_domain_reset (
    .clk_i(usb_clk), .reset_i(usb_rst),
    .reset_o(write_reset), .ready_o(write_ready)
  );
  assign w_rdy = write_ready & ~w_full;'''
    pairs = [(anchor, replacement)]
    for name in ('produce_w_bin', 'produce_w_gry', 'consume_w_bin', 'w_level'):
        old = ("  always_ff @(posedge usb_clk, posedge usb_rst)\n"
               "    if (usb_rst) " + name + " <= 7'h00;")
        new = ("  always_ff @(posedge usb_clk, posedge write_reset)\n"
               "    if (write_reset) " + name + " <= 7'h00;")
        pairs.append((old, new))
    return pairs


def adapt(payload, *, enabled=False):
    """Default-off is byte-for-byte identical, including legacy line endings."""
    if not enabled:
        return payload
    if sha(payload) != INPUT_SHA256:
        raise ValueError('USB FIFO local-reset locked generated input identity drift')
    text = payload.decode()
    for old, new in changes():
        text = once(text, old, new)
    return text.encode()


def prepare(root, stage, *, enabled=False):
    if not enabled:
        return None
    root, stage = Path(root), Path(stage)
    path = stage / FIFO
    old = path.read_bytes()
    new = adapt(old, enabled=True)
    source = root / SOURCE
    if not source.is_file():
        raise FileNotFoundError('USB FIFO local-reset maintained source missing')
    path.write_bytes(new)
    return dict(policy=POLICY, enabled=True, fifo=FIFO, input_sha256=sha(old),
        output_sha256=sha(new), source=SOURCE, source_sha256=sha(source.read_bytes()),
        tool=TOOL, tool_sha256=sha((root / TOOL).read_bytes()),
        write_reset_groups=['produce_w_bin', 'produce_w_gry', 'consume_w_bin', 'w_level'],
        write_release_usb_edges=2, audio_reset_and_drain_unchanged=True,
        async_assertion_preserved=True, false_paths_added=False,
        exit_plan='Replace adapter only after a maintained native FIFO proves identical storage/output/Gray/cancellation contracts.',
        physical_recovery_removal_accepted=False, hardware_tested=False)


def verify_prepared(stage, evidence):
    stage = Path(stage)
    if not isinstance(evidence, dict) or evidence.get('policy') != POLICY or evidence.get('enabled') is not True:
        raise ValueError('USB FIFO local-reset prepared policy missing or changed')
    fixed = dict(fifo=FIFO, write_reset_groups=['produce_w_bin', 'produce_w_gry', 'consume_w_bin', 'w_level'],
        write_release_usb_edges=2, audio_reset_and_drain_unchanged=True,
        async_assertion_preserved=True, false_paths_added=False,
        physical_recovery_removal_accepted=False, hardware_tested=False)
    if any(evidence.get(key) != value or type(evidence.get(key)) is not type(value) for key, value in fixed.items()):
        raise ValueError('USB FIFO local-reset prepared semantics or acceptance forged')
    payload = (stage / FIFO).read_bytes()
    if sha(payload) != evidence.get('output_sha256'):
        raise ValueError('USB FIFO local-reset prepared output identity drift')
    text = payload.decode()
    for old, new in reversed(changes()):
        text = once(text, new, old)
    original = text.encode()
    if sha(original) != INPUT_SHA256 or evidence.get('input_sha256') != INPUT_SHA256:
        raise ValueError('USB FIFO local-reset canonical generated input drift')
    for key, path in (('source', SOURCE), ('tool', TOOL)):
        if evidence.get(key) != path or sha((stage / path).read_bytes()) != evidence.get(key + '_sha256'):
            raise ValueError('USB FIFO local-reset sealed implementation drift: ' + key)
    if adapt(original, enabled=True) != payload:
        raise ValueError('USB FIFO local-reset exact transformation drift')
    return dict(evidence, prepared_identity_verified=True,
        unchanged_bytes_outside_five_unique_adaptations_verified=True)


def verify_demo_selection(stage, configuration, evidence, enabled_inputs, *, expected_configuration=None):
    """New configurations require the gate; sealed old inputs replay exactly."""
    if not isinstance(configuration, dict) or configuration.get('demo_role') not in ('M', 'W'):
        raise ValueError('USB FIFO local-reset selected DEMO configuration missing')
    if expected_configuration is not None:
        legacy = dict(expected_configuration)
        if legacy.pop('usb_fifo_reset_policy', None) != POLICY:
            raise ValueError('USB FIFO local-reset authoritative configuration changed')
        if configuration not in (expected_configuration, legacy):
            raise ValueError('USB FIFO local-reset DEMO configuration identity changed')
    selected = configuration.get('usb_fifo_reset_policy')
    if selected is None:
        if (evidence is not None or SOURCE in enabled_inputs or
                sha((Path(stage) / FIFO).read_bytes()) != INPUT_SHA256):
            raise ValueError('USB FIFO local-reset policy omitted from changed inputs')
        return dict(mode='sealed_legacy_original_fifo', fifo_sha256=INPUT_SHA256,
            explicit_local_release_selected=False)
    if selected != POLICY:
        raise ValueError('USB FIFO local-reset unknown or forged selected policy')
    if list(enabled_inputs).count(SOURCE) != 1:
        raise ValueError('USB FIFO local-reset selected maintained source missing or duplicated')
    return dict(mode='explicit_demo_producer_local_release',
        prepared=verify_prepared(stage, evidence), explicit_local_release_selected=True)


def audit_synthesis(netlist, *, fifo_scope='u_native_usb/input_owner/events/fifo/unbuffered'):
    """Prove actual reset clocks/consumers; this does not waive STA endpoints."""
    from tools.workstation_runtime_pcm_cdc import Graph, COMB
    n, g = netlist, Graph(netlist)

    def require(ok, message):
        if not ok:
            raise ValueError('USB FIFO local-reset synthesis audit: ' + message)

    def regs(scope, stem, bits):
        found = {}
        for p, c in n.cells.items():
            match = re.fullmatch(re.escape(scope + '/' + stem) + r'_(\d+)_s\d+', p)
            if match and c['kind'].startswith('DFF'):
                bit = int(match[1])
                require(bit not in found, 'duplicate register bit: ' + stem)
                found[bit] = p
        require(set(found) == set(bits), 'exact register inventory changed: ' + stem)
        return found

    require(n.frames.get(fifo_scope, {}).get('kind') == 'gw138k_usb_event_fifo.fifo.unbuffered',
            'actual FIFO hierarchy missing')
    scope = fifo_scope + '/write_domain_reset'
    require(n.frames.get(scope, {}).get('kind') == 'workstation_fifo_write_reset',
            'maintained write reset module missing')
    release = regs(scope, 'release_q', range(2))
    read_scope = fifo_scope + '/rst_cdc'
    read_regs = [p for p, c in n.cells.items() if p.startswith(read_scope + '/') and c['kind'].startswith('DFF')]
    require(len(read_regs) == 2 and all(n.cells[p]['kind'] == 'DFFPE' for p in read_regs),
            'original audio reset release inventory changed')
    usb = n.pin(release[0], 'CLK')
    audio = n.pin(read_regs[0], 'CLK')
    assertion = n.pin(read_regs[0], 'PRESET')
    require(usb != audio, 'FIFO clocks collapsed')
    for p in release.values():
        require(n.cells[p]['kind'] == 'DFFCE' and n.pin(p, 'CLK') == usb and
                n.pin(p, 'CLEAR') == assertion and n.pin(p, 'CE') in g.high,
                'write release clock/asynchronous assertion/enable changed')
    require(n.pin(release[0], 'D') in g.high and
            n.pin(release[1], 'D') == n.pin(release[0], 'Q'), 'write release is not two real USB edges')
    require(g.fan[n.pin(release[0], 'Q')] == [(release[1], 'D', 'ff')],
            'first release stage has extra consumers')
    producers = regs(fifo_scope, 'produce_w_bin', range(7))
    local = n.pin(producers[0], 'CLEAR')
    q = n.pin(release[1], 'Q')
    reset_logic = g.equivalent('only final USB release deasserts write reset',
        [local, q], lambda x: x[0] == 1 - x[1], cuts={q})
    groups = {}
    for stem, bits in (('produce_w_bin', range(7)), ('produce_w_gry', range(6)),
                       ('consume_w_bin', ()), ('w_level', ())):
        # Both unused level diagnostics are removed by the real compiler in
        # the unchanged baseline as well. The byte-checked source transform
        # proves their reset edits; the 13 actual pointer registers stay live.
        group = regs(fifo_scope, stem, bits)
        for p in group.values():
            require(n.cells[p]['kind'] == 'DFFCE' and n.pin(p, 'CLK') == usb and
                    n.pin(p, 'CLEAR') == local,
                    'real producer state lacks local USB reset: ' + p)
        groups[stem] = group
    expected = sorted((p, 'CLEAR', 'ff') for group in groups.values() for p in group.values())
    require(sorted(g.fan[local]) == expected, 'write local reset must own only four state groups')
    # Gowin can absorb/rename w_rdy across the owner boundary. Bind admission
    # to its actual single packet-memory CEA and the effective producer Q0
    # increment, rather than requiring an incidental output-port spelling.
    memories = [p for p, c in n.cells.items() if p.startswith(fifo_scope + '/') and c['kind'] == 'SDPX9B']
    require(len(memories) == 1 and n.pin(memories[0], 'CLKA') == usb and n.pin(memories[0], 'CLKB') == audio,
            'actual packet memory clock/identity changed')
    grant = n.pin(memories[0], 'CEA')
    reachable, todo = {q}, [q]
    while todo:
        net = todo.pop()
        for cell, _, category in g.fan[net]:
            if category != 'comb':
                continue
            for port in COMB[n.cells[cell]['kind']]:
                target = n.pin(cell, port)
                if target not in reachable:
                    reachable.add(target);todo.append(target)
    def frontier(net, active=()):
        if net == q or net not in reachable:
            return {net}
        require(net not in active, 'write admission combinational cycle')
        drivers = g.drivers[net]
        require(len(drivers) == 1, 'write admission driver missing/ambiguous')
        cell = drivers[0][0];kind = n.cells[cell]['kind']
        require(kind == 'INV' or re.fullmatch('LUT[1-6]', kind), 'unreviewed write admission primitive')
        ports = ['I'] if kind == 'INV' else ['I' + str(i) for i in range(int(kind[3:]))]
        return set().union(*(frontier(n.pin(cell, port), (*active, net)) for port in ports))
    inputs = frontier(grant)
    require(q in inputs, 'actual packet write admission lacks final USB release')
    admission = g.equivalent('actual packet memory cannot write before local release',
        [grant, q], lambda x: bool(x[1]) or x[0] == 0, cuts=inputs)
    input_list = sorted(inputs)
    require(any(g.value(grant, {net: (value >> bit) & 1 for bit, net in enumerate(input_list)})
                for value in range(1 << len(input_list))), 'FIFO admission optimized to constant zero')
    p = producers[0];previous = n.pin(p, 'Q')
    increment = g.equivalent('effective producer Q0 toggles exactly on the real packet-memory write',
        [n.pin(p, 'D'), n.pin(p, 'CE'), previous, grant],
        lambda x: (x[0] if x[1] else x[2]) == (x[2] ^ x[3]), cuts={previous, grant})
    require(all(n.pin(p, 'CLK') == audio and n.pin(p, 'PRESET') == assertion for p in read_regs),
            'original audio reset boundary changed')
    return dict(policy=POLICY, actual_write_state_registers=sum(map(len, groups.values())),
        write_groups=groups, release_registers=release, usb_clock=usb, audio_clock=audio,
        async_assertion_net=assertion, local_reset_net=local,
        reset_function=reset_logic, admission_function=admission, pointer_increment_function=increment,
        actual_memory_write_pin=memories[0] + '/CEA',
        original_audio_reset_registers=read_regs, no_pointer_reset_false_paths_added=True,
        two_domains_verified=True, physical_recovery_removal_accepted=False,
        hardware_tested=False)
