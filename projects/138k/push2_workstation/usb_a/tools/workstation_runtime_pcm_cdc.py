"""Partial native PCM/context CDC source audit and explicit constraints; no EDA.

The reviewed native bridge/serializer composition owns these contracts. This
module neither emits RTL nor reconstructs accepted baselines. Unknown or changed
FF/consumer inventories fail; revise this policy after a separate source review.
"""
from collections import defaultdict
from pathlib import Path
import argparse
import fnmatch
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.workstation_custom_clocks import clock_bundle
from tools.workstation_custom_usb2_cdc import pattern, query
from tools.workstation_runtime_clock_audit import (
    AUDIT_SOURCES as CLOCK_SOURCES, MODE_EXCLUSIONS, VG_RELATIVE,
    audit_runtime_clocks, digest, file_sha, verify_synthesis_identity,
)
from tools.workstation_synthesis_netlist import IDENTIFIER, SynthesisNetlist

TOP = 'workstation_custom_138k_top'
POLICY = 'native-runtime-pcm-context-cdc-v2'
CONSTRAINT_REVISIONS = ('paired-nextq-v2', 'legacy-v1')
R = 'u_managed/runtime'
B, Z, T = R + '/bridge', R + '/serializer', R + '/clocks/transaction'
AUDIT_SOURCES = (*CLOCK_SOURCES, 'tools/workstation_custom_usb2_cdc.py',
                 'tools/workstation_runtime_pcm_cdc.py', 'sim/test_workstation_runtime_pcm_cdc.py',
                 'tools/WORKSTATION_RUNTIME_PCM_CDC.md')
# (scope, stem, bit indexes or None for scalar, pin). Each bit is selected
# explicitly; suffix wildcards may match only its one actual synthesis FF.
def ref(scope, stem, width=None, port='D', start=0):
    return (scope, stem, tuple(range(start, start + width)) if width is not None else None, port)

REQUEST = (ref(B, 'render_44k1_o'), ref(B, 'render_epoch_o', 32), ref(B, 'render_sequence_o', 32))
REPLY = (ref(Z, 'current_error'), ref(Z, 'current_pcm', 32), ref(Z, 'current_sequence', 32, 'CE'),
         ref(Z, 'have_next'), ref(Z, 'have_next', port='CE'), ref(Z, 'next_error'),
         ref(Z, 'next_error', port='CE'), ref(Z, 'next_pcm', 32), ref(Z, 'next_pcm', 32, 'CE'),
         ref(Z, 'playing'), ref(Z, 'request_o'), ref(Z, 'request_sequence_o', 32),
         ref(Z, 'request_sequence_o', 32, 'CE'), ref(Z, 'underrun_count_o', 1),
         ref(Z, 'underrun_count_o', 31, 'CE', 1), ref(Z, 'wanted_sequence', 1),
         ref(Z, 'wanted_sequence', 31, 'CE', 1))
# Only these already registered consumers may migrate between D and CE.
# Their effective next-Q is independently proved below. All other closure pins
# remain exact, and each flexible FF must still have exactly one actual pin.
REPLY_FLEX = (ref(Z, 'underrun_count_o', 1), ref(Z, 'wanted_sequence', 31, start=1))
REPLY_PAIRED = REPLY + (ref(Z, 'underrun_count_o', 1, 'CE'), ref(Z, 'wanted_sequence', 31, start=1))
CONTEXT = (ref(R, 'pending_rate'), ref(R, 'pending_epoch', 32))
SERIAL = (ref(R, 'serial_rate'), ref(R, 'serial_epoch', 32))
READY_FIRST = (ref(R, 'serial_context_ready', 1),)
# Feedback/comparator endpoints in the source domain are also enumerated. No
# clock or prefix filter is allowed to hide an extra consumer from the closure.
LOCAL = (ref(T, 'active_44k1_o', port='CE'), ref(T, 'active_valid_o'), ref(T, 'applied_o'),
         ref(T, 'audio_reset_no'), ref(T, 'booting'), ref(T, 'quiesce_o'), ref(T, 'dac_mute_o'), ref(T, 'clock_select_o', 2),
         ref(T, 'clock_select_o', 2, 'CE'), ref(T, 'failed_o'), ref(T, 'fault_code_o', 3),
         ref(T, 'state', 4), ref(T, 'stream_epoch_o', 32, 'CE'), ref(T, 'timer', 21),
         ref(R, 'context_payload', 33, 'CE'), ref(R, 'context_sent', port='CE'), ref(R, 'context_toggle'))
PAYLOADS = (
    ('request', (ref(B, 'held_request', 65, 'Q'),), REQUEST, REQUEST, 'selected', 'compute', 13.020, 2),
    ('reply', (ref(B, 'held_reply', 98, 'Q'),), REPLY_PAIRED, REPLY, 'compute', 'selected', 13.020, 2),
    ('context', (ref(R, 'context_payload', 33, 'Q'),), CONTEXT,
     CONTEXT + READY_FIRST + LOCAL, 'control', 'compute', 13.020, 3),
    ('serial-context', (ref(T, 'pending_44k1', port='Q'), ref(T, 'pending_epoch', 32, 'Q')), SERIAL,
     SERIAL + READY_FIRST + LOCAL + (ref(T, 'active_44k1_o'), ref(T, 'stream_epoch_o', 32),
                                   ref(R, 'context_payload', 33)), 'control', 'selected', 20.000, None),
)
# Single-bit sources are exact register Qs or named composition boundaries.
# The latter are independently checked below; they are not discovered from D0.
SYNCS = (
    (B, 'request_sync', 'compute', B, 'request_toggle'),
    (B, 'request_ack_sync', 'selected', B, 'request_ack'),
    (B, 'reply_sync', 'selected', B, 'reply_toggle'),
    (B, 'reply_ack_sync', 'compute', B, 'reply_ack'),
    (B, 'source_quiet_sync', 'compute', B, 'source_quiet'),
    (R, 'context_sync', 'compute', R, 'context_toggle'),
    (R, 'ack_sync', 'control', R, 'context_ack'),
    (B, 'serial_quiesce_sync', 'selected', None, 'quiesce'),
    (B, 'compute_quiesce_sync', 'compute', None, 'quiesce'),
    (R, 'serial_quiesce', 'selected', None, 'quiesce'),
    (R, 'serial_resume', 'selected', None, 'resume'),
    (R, 'serial_context_ready', 'selected', None, 'ready'),
    (R, 'quiet_sync', 'control', R, 'all_quiet'),
    (R, 'fault_sync', 'control', None, 'fault'),
    (R, 'prefill_sync', 'control', None, 'prefill'),
    (R, 'running_sync', 'control', Z, 'output_running_o'),
)
RESETS = ((B, 'compute_release', 2, 'compute', 'compute_reset_n'),
          (B, 'serial_release', 2, 'selected', 'serial_reset_n'),
          (R, 'control_release', 3, 'control', None),
          (R, 'compute_release', 3, 'compute', None),
          (R, 'memory_release', 3, 'memory', None))
COMB = {'INV': ('O',), 'IBUF': ('O',), 'OBUF': ('O',), 'BUFG': ('O',),
        'TBUF': ('O',), 'VCC': ('V',), 'GND': ('G',), 'ALU': ('SUM', 'COUT'),
        **{'LUT' + str(i): ('F',) for i in range(1, 7)},
        **{'MUX2_LUT' + str(i): ('O',) for i in range(5, 9)}}


def require(condition, message):
    if not condition:
        raise ValueError('runtime PCM CDC audit: ' + message)


def prepared_reset_policy(stage):
    """Select only the explicit, sealed custom-board common-reset wiring."""
    stage = Path(stage)
    relative = 'rtl/workstation/gw138k_push_workstation_top.v'
    text = (stage / relative).read_text()
    instances = re.findall(r'workstation_runtime_controlled\s*#\((.*?)\)\s*u_managed\s*\((.*?)\);', text, re.S)
    require(len(instances) == 1, 'staged runtime instance missing/duplicate')
    parameters, ports = instances[0]
    selected = re.findall(r'\.SEPARATE_COMMON_RESET\s*\(\s*([^()]+)\s*\)', parameters)
    if not selected or selected == ['0']:
        return dict(mode='legacy-global')
    require(selected == ['1'], 'staged common-reset selection is not explicit')
    custom = text.split('`else', 1)[0]
    require('module workstation_custom_138k_top' in custom and
            len(re.findall(r"\bwire\s+button1_n\s*=\s*1'b1\s*;", custom)) == 1 and
            re.search(r'\.common_reset_ni\s*\(\s*button1_n\s*\)', ports) is not None and
            re.search(r'\.rst_ni\s*\(\s*runtime_reset_n\s*\)', ports) is not None and
            len(re.findall(r'\bwire\s+runtime_reset_n\s*=\s*reset_n\s*&&\s*memory_guard_started\s*;', text)) == 1,
            'staged raw button/common assertion or startup grant changed')
    sources = [relative]
    for relative in ('rtl/workstation/workstation_runtime_controlled.sv',
                     'rtl/workstation/workstation_runtime_audio.sv',
                     'rtl/audio/workstation_audio_clock_domain.sv'):
        source = (stage / relative).read_text()
        require(len(re.findall(r'\bwire\s+common_reset_n\s*=\s*SEPARATE_COMMON_RESET\s*\?\s*common_reset_ni\s*:\s*rst_ni\s*;', source)) == 1,
                'staged common-reset selection changed: ' + relative)
        if relative != 'rtl/audio/workstation_audio_clock_domain.sv':
            require('.SEPARATE_COMMON_RESET(SEPARATE_COMMON_RESET)' in source and
                    '.common_reset_ni(common_reset_n)' in source,
                    'staged common-reset forwarding changed: ' + relative)
        sources.append(relative)
    return dict(mode='separate-raw-button', raw_button_constant=1,
                source_sha256={relative: file_sha(stage / relative) for relative in sources})


def selectors(refs):
    return [pattern(scope, stem + ('_' + str(bit) if bit is not None else ''), pin)
            for scope, stem, bits, pin in refs for bit in (bits if bits is not None else (None,))]


def prepared_context_ack_policy(stage):
    """Bind the ACK variant to its sealed source; never infer it from a VG."""
    relative = 'rtl/workstation/workstation_runtime_audio.sv'
    path = Path(stage) / relative
    source = path.read_text()
    guards = re.findall(r'CFG_ACK\s*:\s*if\s*\(([^()]*)\)\s*begin', source)
    require(len(guards) == 1, 'staged context ACK guard missing/duplicate')
    guard = re.sub(r'\s+', '', guards[0])
    require(guard in ('config_applied', 'config_applied&&!integration_fault'),
            'staged context ACK guard changed')
    return dict(mode='fault-sticky' if 'integration_fault' in guard else 'legacy',
                source_sha256={relative: file_sha(path)})


def runtime_pcm_cdc_bundle(root, *, constraint_revision=CONSTRAINT_REVISIONS[0]):
    require(constraint_revision in CONSTRAINT_REVISIONS, 'unknown constraint revision')
    clocks = clock_bundle(root)['plan']
    hz = {x['name']: x['frequency_hz'] for x in (*clocks['primary'], *clocks['generated'])}
    require(hz['audio_76m8'] == 76800000 and hz['clk_50m'] == 50000000,
            'reviewed destination/launch budgets require unchanged clocks')
    lines, groups = [], []
    for name, source, capture, closure, origin, destination, budget, edges in PAYLOADS:
        if name == 'reply' and constraint_revision == 'legacy-v1':
            capture = REPLY
        src, dst = selectors(source), selectors(capture)
        path = '-from ' + query(' '.join(src)) + ' -to ' + query(' '.join(dst))
        lines.extend((f'set_max_delay {budget:.3f} {path}', 'set_false_path -hold ' + path))
        groups.append(dict(id=name, source_domain=origin, destination_domain=destination,
            width=len(src), capture_pin_count=len(dst), max_delay_ns=budget,
            minimum_destination_wait_edges=edges, selectors=dict(source=src, capture=dst),
            stability_basis=('actual config-application ACK, returned control ACK, two selected ready stages, guard0 capture'
                             if edges is None else f'payload/toggle same event; capture no earlier than {edges} destination edges')))
    for scope, stem, domain, _, _ in SYNCS:
        first, second = pattern(scope, stem + '_0', 'D'), pattern(scope, stem + '_1', 'D')
        lines.extend(('set_false_path -to ' + query(first), 'set_max_delay 2.000 -from ' +
                      query(pattern(scope, stem + '_0', 'Q')) + ' -to ' + query(second)))
    for scope, stem, width, domain, last in RESETS:
        stages = [(scope, stem + '_' + str(i)) for i in range(width)] + ([(scope, last)] if last else [])
        for (s0, f0), (s1, f1) in zip(stages, stages[1:]):
            lines.append('set_max_delay 2.000 -from ' + query(pattern(s0, f0, 'Q')) +
                         ' -to ' + query(pattern(s1, f1, 'D')))
    require(len(lines) == 50, 'constraint inventory changed')
    return dict(policy=POLICY, constraint_revision=constraint_revision, source='tools/workstation_runtime_pcm_cdc.py',
        source_sha256=file_sha(Path(root) / 'tools/workstation_runtime_pcm_cdc.py'),
        payload_groups=groups, synchronization_groups=16, global_release_groups=5,
        sdc='\n'.join(lines) + '\n', source_policy='native maintained bridge/context/serializer composition; fail on endpoint or contract drift',
        exit_conditions=['Exact source/consumer topology and new negative controls after any implementation change',
                         'Fresh prepare/synthesis seal, Gowin query resolution and both selected-mode routed flight/setup/hold',
                         'Independent reset assertion/recovery/removal/pulse and observation FIFO RAM ownership/data proof'],
        constraints_complete=False, reset_inventory_complete=False, physical_cdc_accepted=False,
        release_ready=False, deployment_allowed=False)


class PcmNetlist(SynthesisNetlist):
    """Preserve the maintained parser; resolve escaped scalar formal aliases.

    Gowin uses an escaped scalar actual at a child output and the unescaped
    identifier as its formal key. Only a declared formal may remove the escape.
    Remove this adapter after the shared parser carries the same regression.
    """
    def __init__(self, text, top):
        super().__init__(text, top)
        # Repair only connection dictionaries from the original instance text.
        # cells/modules/frames intentionally retain the shared instance object.
        # The original VG bytes and the maintained parser remain unchanged.
        instances = re.compile(r'^[ \t]*(' + IDENTIFIER + r')[ \t]+(' + IDENTIFIER + r')[ \t]*\((.*?)^[ \t]*\);', re.M | re.S)
        ports = re.compile(r'\.(?:(\\[^\s]+)[ \t]+|([A-Za-z_$][A-Za-z0-9_$]*))\(\s*([^()]*?)\s*\)')
        escaped, total = 0, 0
        for module in re.finditer(r'^module\s+(' + IDENTIFIER + r')\s*\((.*?)^endmodule\b', text, re.M | re.S):
            kind = module[1].removeprefix('\\')
            seen_instances = set()
            for match in instances.finditer(module[2]):
                label = match[2].removeprefix('\\')
                require(label not in seen_instances, 'duplicate lexical instance binding')
                seen_instances.add(label)
                bindings = {}
                for port in ports.finditer(match[3]):
                    name = (port[1] or port[2]).removeprefix('\\')
                    require(name not in bindings, 'duplicate/ambiguous named port: ' + kind + '/' + label + '/' + name)
                    bindings[name] = port[3].strip()
                    escaped += bool(port[1])
                    total += 1
                require(not ports.sub('', match[3]).strip(' \t\r\n,'), 'unparsed named-port binding: ' + kind + '/' + label)
                original = self.modules[kind][label]['ports']
                require(all(bindings.get(k) == v for k, v in original.items()), 'original named-port parse disagrees with strict lexer')
                original.clear()
                original.update(bindings)
            require(seen_instances == set(self.modules[kind]), 'strict instance inventory differs from maintained parser')
        self.lexical_connection_audit = dict(original_text_sha256=digest(text.encode()),
            named_port_count=total, escaped_named_port_count=escaped, duplicate_bindings_rejected=True,
            original_vg_rewritten=False, shared_parser_modified=False)

    def canonical(self, scope, net, seen=()):
        if scope and net.startswith('\\') and net[1:] in self.frames[scope]['ports']:
            net = net[1:]
        return super().canonical(scope, net, seen)


class Graph:
    """Scalar combinational graph. Other primitives are explicit terminals."""
    def __init__(self, n):
        self.n = n
        self.regs = {p: c for p, c in n.cells.items() if c['kind'].startswith('DFF')}
        self.fan, self.drivers = defaultdict(list), defaultdict(list)
        self.names, self.pin_groups = defaultdict(list), defaultdict(set)
        for p, c in n.cells.items():
            if c['kind'] in n.modules or '_s' not in p:
                continue
            stem = p.rsplit('_s', 1)[0]
            self.pin_groups[stem].update(p + '/' + port for port in c['ports'])
            if p in self.regs:
                self.names[stem].append(p)
        self.high, self.low = {"1'b1"}, {"1'b0"}
        for p, c in n.cells.items():
            if c['kind'] in n.modules:
                continue
            kind = c['kind']
            if kind in ('VCC', 'GND'):
                (self.high if kind == 'VCC' else self.low).add(n.pin(p, 'V' if kind == 'VCC' else 'G'))
            for port, binding in c['ports'].items():
                if p in self.regs or kind in COMB:
                    net = n.pin(p, port)
                    if port == 'Q' and p in self.regs or port in COMB.get(kind, ()):
                        self.drivers[net].append((p, port))
                    else:
                        self.fan[net].append((p, port, 'ff' if p in self.regs else 'comb'))
                else:
                    for bit in self.binding_bits(n.scopes[p], binding):
                        self.fan[n.canonical(n.scopes[p], bit)].append((p, port, 'unsupported'))

    def binding_bits(self, scope, binding):
        try:
            return self.n.concatenation_bits(scope, binding if binding.startswith('{') else '{' + binding + '}')
        except ValueError:
            # Escaped identifiers may contain brackets: \\envelope_pipe[4] [17:0].
            result = []
            for member in (binding[1:-1] if binding.startswith('{') else binding).split(','):
                member = member.strip()
                try:
                    result.extend(self.n.concatenation_bits(scope, '{' + member + '}'))
                    continue
                except ValueError:
                    pass
                m = re.fullmatch(r'(\\[^\s]+)\s+\[(\d+)(?::(\d+))?\]', member)
                require(m is not None, 'unsupported vector binding: ' + binding)
                left, right = int(m[2]), int(m[3] or m[2])
                result.extend(m[1] + ' [' + str(i) + ']' for i in range(right, left + (1 if left >= right else -1), 1 if left >= right else -1))
            return result

    def register(self, scope, stem, bit=None):
        exact = scope + '/' + stem + ('_' + str(bit) if bit is not None else '')
        found = self.names[exact]
        require(len(found) == 1, 'exact register missing/duplicate: ' + exact)
        p = found[0]
        require(self.drivers[self.n.pin(p, 'Q')] == [(p, 'Q')], 'register Q has multiple drivers: ' + p)
        return p

    def group(self, scope, stem, width=None):
        count = range(width) if width is not None else (None,)
        regs = [self.register(scope, stem, bit) for bit in count]
        expected = set(regs)
        matched = {p for p in self.regs if re.fullmatch(re.escape(scope + '/' + stem) +
                  (r'_\d+' if width is not None else '') + r'_s\d+', p)}
        require(matched == expected, 'register bit inventory drift: ' + scope + '/' + stem)
        return regs

    def resolve(self, refs):
        result = set()
        for scope, stem, bits, pin in refs:
            for bit in bits if bits is not None else (None,):
                p = self.register(scope, stem, bit)
                require(pin in self.regs[p]['ports'], 'required FF pin absent: ' + p + '/' + pin)
                result.add(p + '/' + pin)
        return result

    def closure(self, sources):
        endpoints, cells, nets, todo = {}, set(), set(), [self.n.pin(p, 'Q') for p in sources]
        while todo:
            net = todo.pop()
            if net in nets:
                continue
            nets.add(net)
            for p, pin, role in self.fan[net]:
                require(role != 'unsupported', 'payload/synchronizer reaches unsupported primitive: ' + p + '/' + pin)
                if role == 'ff':
                    endpoints[p + '/' + pin] = self.n.pin(p, 'CLK')
                else:
                    cells.add(p)
                    todo.extend(self.n.pin(p, output) for output in COMB[self.n.cells[p]['kind']])
        return dict(endpoints=dict(sorted(endpoints.items())), combinational_cells=len(cells),
                    primitive_kinds=sorted({self.n.cells[p]['kind'] for p in cells}))

    def support(self, net, cuts=(), active=()):
        if net in cuts:
            return {net}
        if net in self.high | self.low:
            return set()
        require(net not in active, 'Boolean combinational cycle: ' + net)
        d = self.drivers[net]
        require(len(d) == 1, 'Boolean driver absent/ambiguous: ' + net)
        p, port = d[0]
        if p in self.regs:
            return {net}
        kind = self.n.cells[p]['kind']
        require(kind == 'INV' or re.fullmatch('LUT[1-6]', kind), 'unsupported Boolean primitive: ' + p)
        inputs = ['I'] if kind == 'INV' else ['I' + str(i) for i in range(int(kind[3:]))]
        return set().union(*(self.support(self.n.pin(p, x), cuts, (*active, net)) for x in inputs))

    def value(self, net, assignment):
        if net in self.high | self.low:
            return int(net in self.high)
        if net in assignment:
            return assignment[net]
        p, _ = self.drivers[net][0]
        c = self.n.cells[p]
        if c['kind'] == 'INV':
            return 1 - self.value(self.n.pin(p, 'I'), assignment)
        width = int(c['kind'][3:])
        init = re.fullmatch(r"(\d+)'h([0-9a-fA-F]+)", c['parameters'].get('INIT', ''))
        require(init is not None and int(init[1]) == 1 << width, 'LUT truth table format: ' + p)
        index = sum(self.value(self.n.pin(p, 'I' + str(i)), assignment) << i for i in range(width))
        return (int(init[2], 16) >> index) & 1

    def equivalent(self, label, nets, predicate, cuts=()):
        support = sorted(set().union(*(self.support(x, cuts) for x in nets)))
        require(len(support) <= 16, 'Boolean support exceeds reviewed bound: ' + label)
        for v in range(1 << len(support)):
            a = {net: (v >> bit) & 1 for bit, net in enumerate(support)}
            require(predicate([self.value(x, a) for x in nets]), 'Boolean contract changed: ' + label)
        return dict(contract=label, support=support, cuts=sorted(cuts), exhaustive_assignments=1 << len(support))

    def inequality_chain(self, net):
        """GW5A NE=3 COUT: (I0 != I1) or CIN; prim_sim.v ALU NE.

        Walk the actual chain to its zero seed (or XOR seed). Every operand
        pair is returned, so swapped/missing/duplicated tag bits fail below.
        """
        pairs, seen = set(), set()
        while net not in self.low:
            require(net not in seen, 'comparison carry cycle')
            seen.add(net)
            ds = self.drivers[net]
            require(len(ds) == 1, 'comparison carry driver absent/ambiguous')
            p, port = ds[0]
            c = self.n.cells[p]
            if c['kind'] == 'LUT2' and c['parameters'].get('INIT') == "4'h6":
                require(port == 'F', 'comparison XOR output')
                pair = frozenset(self.n.pin(p, x) for x in ('I0', 'I1'))
                require(len(pair) == 2 and pair not in pairs, 'comparison duplicate seed pair')
                pairs.add(pair)
                break
            require(c['kind'] == 'ALU' and port == 'COUT' and c['parameters'].get('ALU_MODE') == '3'
                    and self.n.pin(p, 'I3') in self.low, 'comparison is not reviewed NE carry: ' + p)
            pair = frozenset(self.n.pin(p, x) for x in ('I0', 'I1'))
            require(len(pair) == 2 and pair not in pairs, 'comparison duplicate operand pair')
            pairs.add(pair)
            net = self.n.pin(p, 'CIN')
        return pairs

    def carry_frontier(self, net):
        todo, seen, outputs = [net], set(), set()
        while todo:
            net = todo.pop()
            if net in seen or net in self.high | self.low:
                continue
            seen.add(net)
            ds = self.drivers[net]
            require(len(ds) == 1, 'capture header driver absent/ambiguous')
            p, port = ds[0]
            if p in self.regs:
                continue
            kind = self.n.cells[p]['kind']
            if kind == 'ALU':
                outputs.add(net)
                continue
            require(kind == 'INV' or re.fullmatch('LUT[1-6]', kind), 'capture header primitive unsupported')
            todo.extend(self.n.pin(p, x) for x in self.n.cells[p]['ports'] if x not in COMB[kind])
        return outputs


class BooleanDiagram:
    """Reduced ordered BDD, with exact LUT truth tables and named leaf inputs.

    Nodes 0/1 are constants. Shannon expansion and unique (variable, low, high)
    nodes give a canonical Boolean function for the fixed variable ordering.
    This avoids enumerating the 32-bit increment/saturation state space. There
    is no sampling, register abstraction, ALU approximation or unknown leaf.
    """
    def __init__(self, inputs):
        require(len(inputs) == len(set(inputs)) <= 120, 'next-Q named input inventory')
        self.nodes, self.unique, self.cache = [None, None], {}, {}
        self.inputs = {net: self.node(i, 0, 1) for i, net in enumerate(inputs)}

    def node(self, variable, low, high):
        if low == high:
            return low
        key = (variable, low, high)
        if key not in self.unique:
            require(len(self.nodes) < 200000, 'next-Q BDD exceeds reviewed node bound')
            self.unique[key] = len(self.nodes)
            self.nodes.append(key)
        return self.unique[key]

    def choose(self, condition, yes, no):
        if condition == 1 or yes == no:
            return yes
        if condition == 0:
            return no
        if yes == 1 and no == 0:
            return condition
        key = (condition, yes, no)
        if key not in self.cache:
            variable = min(self.nodes[x][0] for x in key if x > 1)
            split = lambda x, side: self.nodes[x][side] if x > 1 and self.nodes[x][0] == variable else x
            self.cache[key] = self.node(variable,
                self.choose(*(split(x, 1) for x in key)),
                self.choose(*(split(x, 2) for x in key)))
        return self.cache[key]

    def invert(self, value):
        return self.choose(value, 0, 1)

    def both(self, left, right):
        return self.choose(left, right, 0)

    def either(self, left, right):
        return self.choose(left, 1, right)

    def different(self, left, right):
        return self.choose(left, self.invert(right), right)

    def all(self, values):
        result = 1
        for value in values:
            result = self.both(result, value)
        return result

    def lut(self, inputs, truth):
        if not inputs:
            return truth & 1
        half = 1 << (len(inputs) - 1)
        return self.choose(inputs[-1], self.lut(inputs[:-1], truth >> half),
                           self.lut(inputs[:-1], truth & ((1 << half) - 1)))

    def net(self, graph, net, memo=None, active=()):
        memo = {} if memo is None else memo
        if net in self.inputs:
            return self.inputs[net]
        if net in graph.high | graph.low:
            return int(net in graph.high)
        if net in memo:
            return memo[net]
        require(net not in active, 'next-Q combinational cycle: ' + net)
        ds = graph.drivers[net]
        require(len(ds) == 1, 'next-Q driver absent/ambiguous: ' + net)
        p, port = ds[0]
        cell, n = graph.n.cells[p], graph.n
        require(p not in graph.regs, 'next-Q unexpected register publisher: ' + p)
        kind = cell['kind']
        require(kind == 'INV' or re.fullmatch('LUT[1-6]', kind), 'next-Q unsupported primitive: ' + p)
        if kind == 'INV':
            require(port == 'O', 'next-Q inverter output changed')
            value = self.invert(self.net(graph, n.pin(p, 'I'), memo, (*active, net)))
        else:
            width = int(kind[3:])
            init = re.fullmatch(r"(\d+)'h([0-9a-fA-F]+)", cell['parameters'].get('INIT', ''))
            require(port == 'F' and init is not None and int(init[1]) == 1 << width
                    and int(init[2], 16) < 1 << (1 << width), 'next-Q LUT truth table format: ' + p)
            values = [self.net(graph, n.pin(p, 'I' + str(i)), memo, (*active, net)) for i in range(width)]
            value = self.lut(values, int(init[2], 16))
        memo[net] = value
        return value


def audit_runtime_pcm_cdc(root, text, clocks, *, reset_policy=None, context_ack_policy=None):
    n = PcmNetlist(text, TOP)
    return audit_netlist(root, n, clocks, reset_policy=reset_policy, context_ack_policy=context_ack_policy)


def audit_netlist(root, n, clocks, *, reset_policy=None, context_ack_policy=None):
    """The object form supports in-memory actual-VG negatives, never sealing."""
    g = Graph(n)
    base = clocks.get('base_clock_audit', clocks.get('base_13_clock_audit'))['clocks']
    domains = {k: base[v]['net'] for k, v in dict(control='clk_50m', compute='audio_76m8', memory='ddr_ui100').items()}
    domains['selected'] = clocks['dcs']['output_net']
    reg = lambda s, x: g.register(s, x)
    q = lambda s, x: n.pin(reg(s, x), 'Q')
    bitq = lambda s, x, b: n.pin(g.register(s, x, b), 'Q')
    proofs, resolved, payloads, chains, resets, levels = [], {}, [], [], [], []
    bundle = runtime_pcm_cdc_bundle(root)

    def exact(refs):
        wanted = g.resolve(refs)
        for selector in selectors(refs):
            stem = selector.rsplit('_s*/', 1)[0]
            actual = {pin for pin in g.pin_groups[stem] if fnmatch.fnmatchcase(pin, selector)}
            require(actual and actual <= wanted and len(actual) == 1, 'selector not one exact FF pin: ' + selector)
            resolved[selector] = sorted(actual)
        return wanted

    def ff(p, domain, clear, preset=False):
        pin = 'PRESET' if preset else 'CLEAR'
        require(n.cells[p]['kind'] == ('DFFPE' if preset else 'DFFCE') and n.pin(p, 'CLK') == domains[domain]
                and n.pin(p, pin) == clear, 'FF primitive/clock/reset changed: ' + p)

    def common_ce(regs, label):
        ces = {n.pin(p, 'CE') for p in regs}
        require(len(ces) == 1, 'capture CE differs: ' + label)
        return next(iter(ces))

    reset_policy = reset_policy or dict(mode='legacy-global')
    require(reset_policy.get('mode') in ('legacy-global', 'separate-raw-button'), 'unknown reset policy')
    separate = reset_policy['mode'] == 'separate-raw-button'
    reset_proofs = []
    # Bind the global assertion to the reviewed top-level reset composition.
    # Constant CLEAR is permitted only after the sealed source selected the
    # raw custom-board button, whose input is tied high in this board top.
    first_reset = g.register(R, 'control_release', 0)
    common = n.pin(first_reset, 'CLEAR')
    if separate:
        require(common in g.low and 'button1_n' not in n.directions[TOP], 'raw button common assertion changed')
    else:
        d = g.drivers[common]
        require(len(d) == 1, 'global assertion driver ambiguous')
        p, _ = d[0]
        require(n.cells[p]['kind'] == 'LUT2' and n.cells[p]['parameters'].get('INIT') == "4'h7" and
                {n.pin(p, x) for x in ('I0', 'I1')} == {'reset_n', 'memory_guard_started'}, 'global runtime assertion composition changed')

    def reset_next_q(p, domain, inputs, expected):
        cell = n.cells[p]
        require(cell['kind'] in ('DFFCE', 'DFFRE') and n.pin(p, 'CLK') == domains[domain]
                and n.pin(p, 'CE') in g.high, 'startup/release FF primitive/clock/CE changed: ' + p)
        if cell['kind'] == 'DFFCE':
            require(n.pin(p, 'CLEAR') in g.low, 'startup/release raw assertion changed: ' + p)
        named = list(dict.fromkeys([*inputs, n.pin(p, 'Q')]))
        bd = BooleanDiagram(named)
        actual = bd.net(g, n.pin(p, 'D'))
        if cell['kind'] == 'DFFRE':
            actual = bd.choose(bd.net(g, n.pin(p, 'RESET')), 0, actual)
        require(actual == expected(bd), 'startup/release effective next-Q changed: ' + p)
        reset_proofs.append(dict(register=p, clock=domains[domain], primitive=cell['kind'],
            named_inputs=named, effective_next_q_verified=True, bdd_node_count=len(bd.nodes)))

    def granted_release(scope, regs, domain):
        stem = dict(control='startup_control', compute='startup_compute', memory='startup_memory')[domain]
        startup = g.group(scope, stem, 2)
        first, second = startup
        reset_next_q(first, domain, ['reset_n', 'memory_guard_started'],
            lambda bd: bd.both(bd.inputs['reset_n'], bd.inputs['memory_guard_started']))
        require(g.fan[n.pin(first, 'Q')] == [(second, 'D', 'ff')], 'startup first-stage fanout changed: ' + first)
        reset_next_q(second, domain, [n.pin(first, 'Q')], lambda bd: bd.inputs[n.pin(first, 'Q')])
        grant = n.pin(second, 'Q')
        for i, p in enumerate(regs):
            previous = n.pin(regs[i - 1], 'Q') if i else grant
            require(n.pin(p, 'D') == previous, 'startup release shift changed: ' + p)
            reset_next_q(p, domain, [grant, previous],
                lambda bd, previous=previous: bd.both(bd.inputs[grant], bd.inputs[previous]))
            if i < len(regs) - 1:
                require(g.fan[n.pin(p, 'Q')] == [(regs[i + 1], 'D', 'ff')], 'reset release intermediate fanout: ' + p)
    local = {}
    for scope, stem, width, domain, last in RESETS:
        regs = g.group(scope, stem, width)
        if last:
            regs.append(reg(scope, last))
        if separate and scope == R:
            granted_release(scope, regs, domain)
        else:
            for i, p in enumerate(regs):
                ff(p, domain, n.pin(p, 'CLEAR') if separate else common)
                require(not separate or n.pin(p, 'CLEAR') in g.low, 'bridge raw common assertion changed: ' + p)
                require(n.pin(p, 'CE') in g.high, 'reset release conditional enable: ' + p)
                require(n.pin(p, 'D') in g.high if not i else n.pin(p, 'D') == n.pin(regs[i - 1], 'Q'), 'reset release shift/first constant: ' + p)
                if i < len(regs) - 1:
                    require(g.fan[n.pin(p, 'Q')] == [(regs[i + 1], 'D', 'ff')], 'reset release intermediate fanout: ' + p)
        local[(scope, domain)] = n.pin(regs[-1], 'Q')
        resets.append(dict(scope=scope, stem=stem, registers=regs, domain=domain, assertion_net=common))

    def clear_for(scope, domain):
        output = local[(B if scope == B else R, domain)]
        consumers = [n.pin(p, 'CLEAR') for p in g.regs if p.startswith(scope + '/') and 'CLEAR' in n.cells[p]['ports']]
        candidates = [x for x in set(consumers) if len(g.drivers[x]) == 1 and n.cells[g.drivers[x][0][0]]['kind'] == 'INV'
                      and n.pin(g.drivers[x][0][0], 'I') == output]
        require(len(candidates) == 1, 'local reset inverse absent/ambiguous: ' + scope + '/' + domain)
        return candidates[0]
    clear = {('bridge', d): clear_for(B, d) for d in ('selected', 'compute')}
    clear.update({('runtime', d): clear_for(R, d) for d in ('control', 'compute')})
    # Selected stream assertion is a separate functional reset, not global FIFO
    # reset. Its exact named composition is checked with an exhaustive gate.
    serial_assertion = n.pin(reg(R, 'serial_reset_n'), 'CLEAR')
    fault = R + '/compute_fault'
    audio_reset = R + '/audio_reset_n'
    serial_fault = bitq(R, 'fault_sync', 1)
    proofs.append(g.equivalent('stream reset assertion', [serial_assertion, serial_fault, audio_reset], lambda x: x[0] == (x[1] or not x[2]), {audio_reset}))

    serializer_clear = n.pin(reg(Z, 'configured'), 'CLEAR')
    proofs.append(g.equivalent('serializer local stream reset', [serializer_clear, q(R, 'serial_reset_n')], lambda x: x[0] == (not x[1])))
    clock_reset = R + '/clocks'
    owner_release = [*g.group(clock_reset, 'control_reset_pre', 2), reg(clock_reset, 'control_reset_n')]
    if separate:
        granted_release(clock_reset, owner_release, 'control')
    else:
        for i, p in enumerate(owner_release):
            ff(p, 'control', common)
            require(n.pin(p, 'CE') in g.high and (n.pin(p, 'D') in g.high if not i else n.pin(p, 'D') == n.pin(owner_release[i - 1], 'Q')), 'clock transaction release source changed')
    clock_clear = n.pin(reg(T, 'pending_44k1'), 'CLEAR')
    ds = g.drivers[clock_clear]
    require(len(ds) == 1 and n.cells[ds[0][0]]['kind'] == 'INV' and n.pin(ds[0][0], 'I') == n.pin(owner_release[-1], 'Q'), 'clock transaction payload reset owner changed')

    for entry in bundle['payload_groups']:
        spec = next(x for x in PAYLOADS if x[0] == entry['id'])
        _, source_refs, capture_refs, closure_refs, origin, destination, _, _ = spec
        src = exact(source_refs)
        sources = sorted(x.rsplit('/', 1)[0] for x in src)
        # Source widths are exact, including rejecting unexpected appended bits.
        for scope, stem, bits, _ in source_refs:
            g.group(scope, stem, len(bits) if bits is not None else None)
        for p in sources:
            ff(p, origin, clear[('bridge' if p.startswith(B + '/') else 'runtime', origin)] if not p.startswith(T + '/') else clock_clear, preset=p == g.register(T, 'pending_epoch', 0))
        expected, capture = exact(closure_refs), exact(capture_refs)
        closure = g.closure(sources)
        actual = set(closure['endpoints'])
        if entry['id'] == 'reply':
            flexible = {p.rsplit('/', 1)[0] for p in exact(REPLY_FLEX)}
            fixed = {p for p in expected if p.rsplit('/', 1)[0] not in flexible}
            require({p for p in actual if p.rsplit('/', 1)[0] not in flexible} == fixed,
                    'complete payload consumer closure changed: reply')
            for p in flexible:
                pins = {ep for ep in actual if ep.rsplit('/', 1)[0] == p}
                require(len(pins) == 1 and pins <= {p + '/D', p + '/CE'},
                        'reply fixed next-Q FF must have exactly one D/CE consumer: ' + p)
            require({p.rsplit('/', 1)[0] for p in actual} == {p.rsplit('/', 1)[0] for p in expected},
                    'reply complete consumer FF identities changed')
        else:
            require(actual == expected, 'complete payload consumer closure changed: ' + entry['id'])
        for endpoint, clock in closure['endpoints'].items():
            if endpoint in capture:
                domain = destination
                p = endpoint.rsplit('/', 1)[0]
                assertion = (serializer_clear if p.startswith(Z + '/') else serial_assertion) if domain == 'selected' else clear[('bridge' if p.startswith(B + '/') else 'runtime', domain)]
                ff(p, domain, assertion)
            elif endpoint in g.resolve(READY_FIRST):
                domain = 'selected'
            else:
                domain = 'control'
            require(clock == domains[domain], 'consumer destination clock changed: ' + endpoint)
        payloads.append(dict(**entry, source_registers=sources, capture_pins=sorted(capture), closure=closure,
                             source_enable=common_ce(sources, entry['id'])))

    # Every sync source is predetermined from an owner/boundary; no source=None
    # or unknown-consumer filtering can make a shifted chain appear valid.
    mute = q(T, 'dac_mute_o')
    resume_inverters = [(p, n.pin(p, 'O')) for p, c in n.cells.items()
                        if n.scopes[p] == R and c['kind'] == 'INV' and n.pin(p, 'I') == mute]
    require(len(resume_inverters) == 1, 'registered mute must have exactly one reviewed resume inverter')
    boundaries = dict(quiesce=q(T, 'quiesce_o'), resume=resume_inverters[0][1], ready=R + '/rate_context_ready', fault=fault, prefill=R + '/serial_prefill')
    for scope, stem, domain, source_scope, source_stem in SYNCS:
        regs = g.group(scope, stem, 2)
        source = q(source_scope, source_stem) if source_scope else boundaries[source_stem]
        if source_scope:
            origin = {'request_sync': 'selected', 'request_ack_sync': 'compute', 'reply_sync': 'compute', 'reply_ack_sync': 'selected', 'source_quiet_sync': 'selected', 'context_sync': 'control', 'ack_sync': 'compute', 'quiet_sync': 'compute', 'running_sync': 'selected'}[stem]
            source_reset = serializer_clear if source_scope == Z else clear[('bridge' if source_scope == B else 'runtime', origin)]
            ff(reg(source_scope, source_stem), origin, source_reset)
        assertion = serial_assertion if scope == R and domain == 'selected' else clear[('bridge' if scope == B else 'runtime', domain)]
        preset = 'quiesce' in stem
        for i, p in enumerate(regs):
            ff(p, domain, assertion, preset=preset)
            require(n.pin(p, 'CE') in g.high and n.pin(p, 'D') == (source if i == 0 else n.pin(regs[0], 'Q')), 'sync source/shift/enable changed: ' + p)
        require(g.fan[n.pin(regs[0], 'Q')] == [(regs[1], 'D', 'ff')], 'sync first-stage fanout: ' + regs[0])
        chains.append(dict(scope=scope, stem=stem, registers=regs, domain=domain, source_net=source, assertion_net=assertion))
        exact((ref(scope, stem, 1), ref(scope, stem, 1, 'Q'), ref(scope, stem, 1, start=1)))
    # Explicit source-domain qualification for combinational control levels.
    for key, domain in [('quiesce', 'control'), ('resume', 'control'), ('ready', 'control'), ('fault', 'compute'), ('prefill', 'selected')]:
        # Traverse backwards through all combinational primitives. Multi-bit
        # comparators are allowed here; no truth table semantics are assumed.
        todo, seen, leaves = [boundaries[key]], set(), set()
        while todo:
            net = todo.pop()
            if net in seen or net in g.high | g.low:
                continue
            seen.add(net)
            ds = g.drivers[net]
            require(len(ds) == 1, 'control level producer absent/ambiguous: ' + key)
            p, _ = ds[0]
            if p in g.regs:
                require(n.pin(p, 'CLK') == domains[domain], 'control level crosses before first sync: ' + key)
                leaves.add(p)
            else:
                kind = n.cells[p]['kind']
                require(kind in COMB, 'control level producer primitive unsupported: ' + p)
                todo.extend(n.pin(p, x) for x in n.cells[p]['ports'] if x not in COMB[kind])

        if key in ('quiesce', 'resume'):
            owner = reg(T, 'quiesce_o' if key == 'quiesce' else 'dac_mute_o')
            require(leaves == {owner}, 'registered clock transaction level owner changed: ' + key)
            ff(owner, 'control', clock_clear, preset=True)
            require(n.pin(owner, 'CE') in g.high, 'registered transaction level conditional CE: ' + key)
            proofs.append(g.equivalent('registered transaction level ' + key, [boundaries[key], n.pin(owner, 'Q')], lambda x: x[0] == (x[1] if key == 'quiesce' else not x[1])))
        elif key == 'ready':
            owners = set(g.group(R, 'context_payload', 33) + g.group(T, 'pending_epoch', 32) + [reg(T, 'pending_44k1'), reg(R, 'context_sent'), reg(R, 'context_toggle'), g.register(R, 'ack_sync', 1), g.register(R, 'fault_sync', 1)])
            require(leaves == owners, 'context ready source owner changed')
        elif key == 'prefill':
            owners = set(g.group(Z, 'startup_frames', 11) + [reg(Z, 'configured'), reg(Z, 'have_next'), g.register(R, 'serial_quiesce', 1)])
            require(leaves == owners, 'serializer prefill source owner changed')
        levels.append(dict(id=key, net=boundaries[key], domain=domain, source_registers=sorted(leaves)))

    # Producer data and credit ownership.
    req_src = g.group(B, 'held_request', 65)
    reply_src = g.group(B, 'held_reply', 98)
    ctx_src = g.group(R, 'context_payload', 33)
    staged = [*g.group(T, 'pending_epoch', 32), reg(T, 'pending_44k1')]
    expected_request = [*g.group(Z, 'request_sequence_o', 32), *g.group(Z, 'epoch', 32), reg(Z, 'mode_44k1')]
    for source, data in zip(req_src, expected_request):
        require(n.pin(source, 'D') == n.pin(data, 'Q'), 'request producer tuple mapping changed')
    reply_tags = [reg(B, 'render_44k1_o'), *reversed(g.group(B, 'render_epoch_o', 32)), *reversed(g.group(B, 'render_sequence_o', 32))]
    expected_reply = [q(R + '/final_pcm', 'frame_error_o'), *[n.pin(p, 'Q') for p in g.group(R + '/final_pcm', 'frame_pcm_o', 32)], *[n.pin(p, 'Q') for p in reversed(reply_tags)]]
    for source, data in zip(reply_src, expected_reply):
        require(n.pin(source, 'D') == data, 'reply producer tuple mapping changed')
    for source, data in zip(ctx_src, staged):
        require(n.pin(source, 'D') == n.pin(data, 'Q'), 'context producer tuple mapping changed')
    for name, sources, toggle_scope, toggle in [('request', req_src, B, 'request_toggle'), ('reply', reply_src, B, 'reply_toggle'), ('context', ctx_src, R, 'context_toggle')]:
        p = reg(toggle_scope, toggle)
        ce = common_ce(sources, name)
        require(n.pin(p, 'CLK') == n.pin(sources[0], 'CLK') and n.pin(p, 'CLEAR') == n.pin(sources[0], 'CLEAR'), 'payload/toggle clock or reset differs: ' + name)
        proofs.append(g.equivalent(name + ' payload/toggle same publication', [n.pin(p, 'D'), n.pin(p, 'Q'), n.pin(p, 'CE'), ce], lambda x: (x[2] & (x[0] ^ x[1])) == x[3], {ce} if name != 'reply' else set()))
    ce = common_ce(req_src, 'request')
    nets = [ce, q(B, 'request_toggle'), bitq(B, 'request_ack_sync', 1), q(Z, 'request_o'), bitq(B, 'serial_quiesce_sync', 1), q(B, 'serial_reset_n'), q(R, 'serial_reset_n')]
    proofs.append(g.equivalent('request publication owns free credit', nets, lambda x: x[0] == (x[1] == x[2] and x[3] and not x[4] and x[5] and x[6])))
    ce = common_ce(reply_src, 'reply')
    proofs.append(g.equivalent('reply publication owns free credit', [ce, q(R + '/final_pcm', 'frame_valid_o'), q(B, 'render_busy_o'), bitq(B, 'compute_quiesce_sync', 1), q(B, 'reply_toggle'), bitq(B, 'reply_ack_sync', 1)], lambda x: x[0] == (x[1] and x[2] and not x[3] and x[4] == x[5])))
    # Context's 33-bit equality carry cone is an explicit partial proof boundary;
    # its handshake gating and exact D tuple are proved, equality semantics are
    # checked separately by structure rather than pretending 2^66 enumeration.
    ctx_ce = common_ce(ctx_src, 'context')
    driver = g.drivers[ctx_ce][0][0]
    inputs = [n.pin(driver, 'I' + str(i)) for i in range(4)]
    known = {q(R, 'context_sent'), q(R, 'context_toggle'), bitq(R, 'ack_sync', 1)}
    comparison = set(inputs) - known
    require(n.cells[driver]['kind'] == 'LUT4' and len(comparison) == 1, 'context publication gate topology changed')
    equal = comparison.pop()
    proofs.append(g.equivalent('context never overwrites unacknowledged payload', [ctx_ce, equal, *[q(R, 'context_sent'), q(R, 'context_toggle'), bitq(R, 'ack_sync', 1)]], lambda x: x[0] == ((x[1] or not x[2]) and x[3] == x[4]), {equal}))

    context_pairs = {frozenset((n.pin(x, 'Q'), n.pin(y, 'Q'))) for x, y in zip(ctx_src, staged)}
    require(g.inequality_chain(equal) == context_pairs, 'context comparison operand identity changed')
    ready_carries = g.carry_frontier(boundaries['ready'])
    ready_rate_pair = frozenset((n.pin(ctx_src[32], 'Q'), q(T, 'pending_44k1')))
    require(len(ready_carries) == 1, 'ready comparison carry count changed')
    ready_diff = next(iter(ready_carries))
    ready_pairs = g.inequality_chain(ready_diff)
    # These two observed synthesis forms have the same complete 33-bit
    # semantics. The scalar form must prove its missing rate pair in the gate.
    require(ready_pairs in (context_pairs, context_pairs - {ready_rate_pair}), 'ready comparison operand identity changed')
    ready_scalar_rate = ready_pairs != context_pairs
    ready_inputs = [boundaries['ready'], q(R, 'context_sent'), q(R, 'context_toggle'), bitq(R, 'ack_sync', 1), ready_diff, bitq(R, 'fault_sync', 1)]
    if ready_scalar_rate:
        ready_inputs += [n.pin(ctx_src[32], 'Q'), q(T, 'pending_44k1')]
    proofs.append(g.equivalent('context ready only returned matching tuple', ready_inputs, lambda x: x[0] == (x[1] and x[2] == x[3] and not x[4] and not x[5] and (not ready_scalar_rate or x[6] == x[7])), {ready_diff}))

    # The reply has no destination mailbox FF: match is a combinational header
    # qualifier shared by next_pcm and the current_pcm frame-boundary bypass.
    next_regs = g.group(Z, 'next_pcm', 32) + [reg(Z, 'next_error')]
    next_ce = common_ce(next_regs, 'serializer next tuple')
    header_carries = g.carry_frontier(next_ce)
    header_pairs = set()
    for carry in header_carries:
        current = g.inequality_chain(carry)
        require(not header_pairs & current, 'reply header comparisons overlap')
        header_pairs.update(current)
    expected_pairs = {frozenset((n.pin(reply_src[i + 65], 'Q'), bitq(Z, 'epoch', i))) for i in range(32)}
    expected_pairs |= {frozenset((n.pin(reply_src[i + 33], 'Q'), bitq(Z, 'wanted_sequence', i))) for i in range(32)}
    high_epoch_pair = frozenset((n.pin(reply_src[96], 'Q'), bitq(Z, 'epoch', 31)))
    require(header_pairs in (expected_pairs, expected_pairs - {high_epoch_pair}), 'reply header bit comparison identity changed')
    reply_scalar_epoch = header_pairs != expected_pairs
    incoming = [q(Z, 'configured'), bitq(R, 'serial_quiesce', 1), q(B, 'serial_reset_n'), q(R, 'serial_reset_n'), bitq(B, 'serial_quiesce_sync', 1), bitq(B, 'reply_sync', 1), q(B, 'reply_ack'), q(Z, 'have_next'), q(Z, 'requested'), n.pin(reply_src[97], 'Q'), q(Z, 'mode_44k1')]
    carries = sorted(header_carries)
    reply_inputs = [next_ce, *incoming, *carries]
    if reply_scalar_epoch:
        reply_inputs += [n.pin(reply_src[96], 'Q'), bitq(Z, 'epoch', 31)]
    carry_end = 12 + len(carries)
    proofs.append(g.equivalent('reply next capture requires live matching header', reply_inputs, lambda x: x[0] == (x[1] and not x[2] and x[3] and x[4] and not x[5] and x[6] != x[7] and not x[8] and x[9] and x[10] == x[11] and not any(x[12:carry_end]) and (not reply_scalar_epoch or x[carry_end] == x[carry_end + 1])), set(carries)))
    for i, p in enumerate(g.group(Z, 'next_pcm', 32)):
        require(n.pin(p, 'D') == n.pin(reply_src[i + 1], 'Q'), 'reply next PCM tuple mapping changed')
    require(n.pin(reg(Z, 'next_error'), 'D') == n.pin(reply_src[0], 'Q'), 'reply next error mapping changed')
    rack = reg(B, 'reply_ack')
    proofs.append(g.equivalent('reply ACK only consume or stream discard', [n.pin(rack, 'CE'), *incoming[:8]], lambda x: x[0] == ((x[6] != x[7]) and (x[5] or not x[4] or (x[1] and not x[8] and not x[2])))))
    require(n.pin(rack, 'D') == bitq(B, 'reply_sync', 1), 'reply ACK token changed')

    # Independent effective-next-Q proof, including both observed D/CE forms.
    # Leaf identities come from the maintained serializer's named state and
    # bridge publishers, never by discovering whatever drives a destination D.
    # The only internal cuts are the header NE predicates just proved above.
    wanted = g.group(Z, 'wanted_sequence', 32)
    underrun = g.group(Z, 'underrun_count_o', 32)
    half = g.group(Z, 'half_count', 2)
    position = g.group(Z, 'bit_position', 6)
    startup = g.group(Z, 'startup_frames', 11)
    playing, bck, resume = reg(Z, 'playing'), reg(Z, 'bck_o'), g.register(R, 'serial_resume', 1)
    serializer_state = wanted + underrun + half + position + startup + [playing, bck]
    for p in serializer_state:
        ff(p, 'selected', serializer_clear)
    state_q = lambda regs: [n.pin(p, 'Q') for p in regs]
    named_inputs = list(dict.fromkeys([*carries, *incoming, *state_q(serializer_state), n.pin(resume, 'Q'),
                                      *([n.pin(reply_src[96], 'Q'), bitq(Z, 'epoch', 31)] if reply_scalar_epoch else [])]))
    bd = BooleanDiagram(named_inputs)
    v = bd.inputs.__getitem__
    inv, both, either, allof = bd.invert, bd.both, bd.either, bd.all
    # This match equation is independently the complete live reply gate; the
    # same source/credit/header predicate also passed the exhaustive gate proof.
    live_match = allof([v(incoming[0]), inv(v(incoming[1])), v(incoming[2]), v(incoming[3]),
        inv(v(incoming[4])), bd.different(v(incoming[5]), v(incoming[6])), inv(v(incoming[7])),
        v(incoming[8]), inv(bd.different(v(incoming[9]), v(incoming[10]))),
        *[inv(v(carry)) for carry in carries],
        *([inv(bd.different(v(n.pin(reply_src[96], 'Q')), v(bitq(Z, 'epoch', 31))))] if reply_scalar_epoch else [])])
    half_q = [v(x) for x in state_q(half)]
    half_end = bd.choose(v(q(Z, 'mode_44k1')), both(inv(half_q[0]), half_q[1]),
                         both(half_q[0], inv(half_q[1])))
    startup_done = allof([v(n.pin(p, 'Q')) if (1028 >> i) & 1 else inv(v(n.pin(p, 'Q')))
                          for i, p in enumerate(startup)])
    next_available = either(v(q(Z, 'have_next')), live_match)
    advance = allof([v(q(Z, 'configured')), inv(v(bitq(R, 'serial_quiesce', 1))),
        half_end, v(n.pin(bck, 'Q')), allof(v(x) for x in state_q(position)), startup_done,
        v(n.pin(resume, 'Q')), either(v(n.pin(playing, 'Q')), next_available)])
    memo, next_q_rows = {}, []

    def prove_next(p, expected, contract):
        actual = bd.choose(bd.net(g, n.pin(p, 'CE'), memo), bd.net(g, n.pin(p, 'D'), memo), v(n.pin(p, 'Q')))
        require(actual == expected, 'effective next-Q contract changed: ' + contract + ': ' + p)
        next_q_rows.append(dict(register=p, contract=contract, d_net=n.pin(p, 'D'), ce_net=n.pin(p, 'CE')))

    carry = 1
    for p in wanted:
        current = v(n.pin(p, 'Q'))
        prove_next(p, bd.different(current, both(advance, carry)), 'wanted sequence increments only on admitted frame')
        carry = both(carry, current)
    count_q = [v(x) for x in state_q(underrun)]
    increment_count = allof([advance, inv(next_available), inv(allof(count_q))])
    prove_next(underrun[0], bd.different(count_q[0], increment_count), 'underrun bit0 saturates and increments only without next frame')
    next_q_proof = dict(method='canonical reduced ordered Boolean decision diagrams',
        effective_update='Q_next = CE ? D : Q (outside independently checked async assertion)',
        named_inputs=named_inputs, header_predicate_cuts=carries, header_operand_pairs_verified=True,
        startup_frames_constant=1028, registers=next_q_rows, proved_register_count=len(next_q_rows),
        flexible_consumer_register_count=32, bdd_node_count=len(bd.nodes), all_assignments=True,
        sampling_used=False, unknown_leaf_inputs_allowed=False, entire_serializer_fsm_proved=False)

    # Consumer mappings and enables include all four held payloads.
    for source, destinations in [(req_src, [*g.group(B, 'render_sequence_o', 32), *g.group(B, 'render_epoch_o', 32), reg(B, 'render_44k1_o')]), (ctx_src, [*g.group(R, 'pending_epoch', 32), reg(R, 'pending_rate')]), (staged, [*g.group(R, 'serial_epoch', 32), reg(R, 'serial_rate')])]:
        for s, d in zip(source, destinations):
            require(n.pin(d, 'D') == n.pin(s, 'Q'), 'consumer held tuple mapping changed: ' + d)
        common_ce(destinations, 'consumer tuple')
    cfg = [bitq(R, 'config_state', i) for i in range(3)]
    proofs.append(g.equivalent('context capture only CFG_SETTLE', [n.pin(reg(R, 'pending_rate'), 'CE'), *cfg], lambda x: x[0] == (x[1] and not x[2] and not x[3])))
    ack = reg(R, 'context_ack')
    applied, service_rate = R + '/config_applied', R + '/service_rate'
    context_ack_policy = context_ack_policy or dict(mode='legacy')
    require(context_ack_policy.get('mode') in ('legacy', 'fault-sticky'), 'unknown context ACK policy')
    sticky = context_ack_policy['mode'] == 'fault-sticky'
    ack_inputs = [n.pin(ack, 'CE'), *cfg, applied, service_rate, q(R, 'pending_rate')]
    context_failure_proof = None
    if sticky:
        context_fault = reg(R, 'integration_fault')
        require(n.cells[context_fault]['kind'] == 'DFFCE' and n.pin(context_fault, 'CLK') == domains['compute'] and
                n.pin(context_fault, 'CLEAR') == n.pin(ack, 'CLEAR') and n.pin(context_fault, 'D') in g.high,
                'sticky context fault primitive/clock/reset/set changed')
        ack_inputs.append(n.pin(context_fault, 'Q'))
        context_failure_proof = g.equivalent('context fault sticks after invalid state or mismatched ACK',
            [n.pin(context_fault, 'CE'), *cfg, applied, service_rate, q(R, 'pending_rate'), n.pin(context_fault, 'Q')],
            lambda x: x[0] == ((x[1] + 2*x[2] + 4*x[3] > 4) or
                (not x[1] and not x[2] and x[3] and x[4] and x[5] != x[6] and not x[7])),
            {applied, service_rate})
    proofs.append(g.equivalent('context ACK only actual matching application', ack_inputs,
        lambda x: x[0] == (not x[1] and not x[2] and x[3] and x[4] and x[5] == x[6] and
                          (not sticky or not x[7])), {applied, service_rate}))
    require(n.pin(ack, 'D') == bitq(R, 'context_sync', 1), 'context ACK token changed')
    guard = [bitq(R, 'serial_guard', i) for i in range(4)]
    sync_state = [q(R, 'serial_reset_n'), bitq(R, 'serial_context_ready', 1), bitq(R, 'serial_quiesce', 1)]
    proofs.append(g.equivalent('serial config capture at guard0 only', [n.pin(reg(R, 'serial_rate'), 'CE'), *sync_state, *guard], lambda x: x[0] == (not x[1] and x[2] and not x[3] and not any(x[4:]))))
    reset = reg(R, 'serial_reset_n')
    proofs.append(g.equivalent('serializer release after guard7', [n.pin(reset, 'CE'), *sync_state, *guard], lambda x: x[0] == (not x[1] and x[2] and not x[3] and all(x[4:7]) and not x[7])))
    require(n.pin(reset, 'D') in g.high, 'serializer release does not assert ready')
    # Actual request capture/ACK shared gate; all eligibility inputs are proved.
    capture = n.pin(reg(B, 'render_44k1_o'), 'CE')
    driver = g.drivers[capture][0][0]
    pending = [bitq(B, 'request_sync', 1), q(B, 'request_ack'), bitq(B, 'compute_quiesce_sync', 1)]
    eligibility = {n.pin(driver, 'I' + str(i)) for i in range(4)} - set(pending)
    require(n.cells[driver]['kind'] == 'LUT4' and len(eligibility) == 1, 'request capture gate topology changed')
    eligible = eligibility.pop()
    proofs.append(g.equivalent('request capture/ACK cancellation', [capture, n.pin(reg(B, 'request_ack'), 'CE'), *pending, eligible], lambda x: x[0] == (x[2] != x[3] and not x[4] and x[5]) and x[1] == (x[2] != x[3] and (x[4] or x[5])), {eligible}))
    state = [bitq(R + '/final_pcm', 'state', i) for i in range(2)]
    # A duplicated fault decode need not traverse the named boundary net.
    # Expand that independently clock-checked owner boundary, rather than
    # inventing an alias cut or enlarging the exhaustive scalar bound.
    fault_owners = next(x['source_registers'] for x in levels if x['id'] == 'fault')
    eligibility_inputs = list(dict.fromkeys([*[n.pin(p, 'Q') for p in fault_owners], *state,
        local[(R, 'compute')], q(B, 'render_busy_o'), q(B, 'reply_toggle'), bitq(B, 'reply_ack_sync', 1),
        *cfg, q(R, 'compute_context_valid')]))
    eligibility_bd = BooleanDiagram(eligibility_inputs)
    ev = eligibility_bd.inputs.__getitem__
    actual_eligibility = eligibility_bd.net(g, eligible)
    expected_eligibility = eligibility_bd.all([eligibility_bd.invert(eligibility_bd.net(g, fault)),
        *[eligibility_bd.invert(ev(x)) for x in state], ev(local[(R, 'compute')]),
        eligibility_bd.invert(ev(q(B, 'render_busy_o'))),
        eligibility_bd.invert(eligibility_bd.different(ev(q(B, 'reply_toggle')), ev(bitq(B, 'reply_ack_sync', 1)))),
        *[eligibility_bd.invert(ev(x)) for x in cfg], ev(q(R, 'compute_context_valid'))])
    require(actual_eligibility == expected_eligibility, 'Boolean contract changed: request eligibility actual renderer state')
    proofs.append(dict(contract='request eligibility actual renderer state', support=eligibility_inputs,
        cuts=[], method='canonical reduced ordered Boolean decision diagrams', all_assignments=True,
        named_fault_boundary=fault, fault_owner_registers=fault_owners,
        bdd_node_count=len(eligibility_bd.nodes)))
    for body in re.findall(r'\[get_pins \{([^}]+)\}\]', bundle['sdc']):
        for selector in body.split():
            stem = selector.rsplit('_s*/', 1)[0]
            actual = sorted(pin for pin in g.pin_groups[stem] if fnmatch.fnmatchcase(pin, selector))
            require(len(actual) == 1, 'bundle selector missing/ambiguous: ' + selector)
            resolved[selector] = actual
    consumer_regs = {ep.rsplit('/', 1)[0] for row in payloads for ep in row['closure']['endpoints']}
    consumer_regs.update(g.group(R, 'serial_guard', 4))
    protected = sorted({p + '/' + pin for p in consumer_regs for pin in ('CLEAR', 'PRESET') if pin in n.cells[p]['ports']} | {p + '/' + pin for row in resets + chains for p in row['registers'] for pin in ('CLEAR', 'PRESET') if pin in n.cells[p]['ports']} | {p + '/' + pin for row in payloads for p in row['source_registers'] for pin in ('CLEAR', 'PRESET') if pin in n.cells[p]['ports']} | {reg(R, 'serial_reset_n') + '/CLEAR'})
    return dict(schema=1, policy=POLICY, acceptance_scope='partial native PCM/context source contracts only', lexical_connection_audit=n.lexical_connection_audit, payload_groups=payloads, payload_source_bits=229, synchronization_groups=chains,
        reset_release_groups=resets, reset_policy=reset_policy, reset_startup_next_q_proofs=reset_proofs,
        context_ack_policy=context_ack_policy, context_failure_proof=context_failure_proof,
        level_source_boundaries=levels, boolean_contracts=proofs, resolved_pin_selectors=resolved,
        protected_async_pins=protected, candidate_constraints_installed=False,
        static_source_contracts_verified=True, complete_payload_closure_verified=True, selector_static_resolution_verified=True,
        context_comparison_semantics_verified=True, reply_capture_header_gate_verified=True,
        reply_effective_next_q_verified=True, reply_next_q_proof=next_q_proof,
        comparison_topologies=dict(ready_carry_pair_count=len(ready_pairs), ready_scalar_rate=ready_scalar_rate,
            reply_carry_pair_count=len(header_pairs), reply_scalar_epoch31=reply_scalar_epoch),
        constraints_complete=False, held_payload_complete=False, fifo_payload_complete=False,
        reset_inventory_complete=False, physical_cdc_accepted=False, routed_propagation_verified=False,
        tool_query_resolution_verified=False, hardware_tested=False, release_ready=False, deployment_allowed=False)


def validate_constraints(root, sdc, result, *, installed=False, constraint_revision=CONSTRAINT_REVISIONS[0]):
    """Validate installed lines or scan an older SDC without claiming install."""
    bundle = runtime_pcm_cdc_bundle(root, constraint_revision=constraint_revision)
    expected = bundle['sdc'].splitlines()
    actual = sdc.splitlines()
    counts = [actual.count(line) for line in expected]
    require(all(x == 1 for x in counts) if installed else all(x == 0 for x in counts),
            'installed PCM lines missing/duplicate' if installed else 'proposal audit must not silently accept partial/already installed bundle')
    protected = set(result['protected_async_pins'])
    source = {p + '/Q' for row in result['payload_groups'] for p in row['source_registers']}
    sinks = {p for row in result['payload_groups'] for p in row['capture_pins']}
    first = {row['registers'][0] + '/D' for row in result['synchronization_groups']}
    stage = {row['registers'][1] + '/D' for row in result['synchronization_groups']}
    stage_sources = {row['registers'][0] + '/Q' for row in result['synchronization_groups']}
    for row in result['reset_release_groups']:
        stage.update(p + '/D' for p in row['registers'][1:])
        stage_sources.update(p + '/Q' for p in row['registers'][:-1])
    regex = re.compile(r'\[(get_pins|get_regs|get_ports|get_clocks)\s+\{([^{}]+)\}\]')
    def matches(line, side, pins):
        rows = re.findall(r'-' + side + r'\s+\[(get_pins|get_regs|get_ports)\s+\{([^{}]+)\}\]', line)
        require(len(rows) <= 1, 'repeated endpoint query unsupported: ' + line)
        return not rows or any(fnmatch.fnmatchcase(p if kind == 'get_pins' else p.rsplit('/', 1)[0], pattern)
            for kind, body in rows if kind != 'get_ports' for pattern in body.split() for p in pins)
    for raw in actual:
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        require(not any(x in line for x in (';', '$', '\\')), 'Tcl evaluation/continuation unsupported')
        shape = regex.sub('QUERY', line)
        require('[' not in shape and ']' not in shape, 'unsupported query syntax: ' + line)
        command = line.split()[0]
        require(command in ('create_clock', 'create_generated_clock', 'set_false_path', 'set_max_delay', 'set_min_delay', 'set_input_delay', 'report_timing'), 'unsupported timing command: ' + line)
        if command.startswith('create_') or command in ('set_input_delay', 'report_timing'):
            continue
        if 'get_clocks' in line:
            require(line in MODE_EXCLUSIONS, 'whole-clock exception forbidden')
            continue
        if matches(line, 'to', protected):
            require(line in expected, 'unreviewed async reset exception')
        if matches(line, 'to', sinks) and matches(line, 'from', source):
            require(line in expected, 'unreviewed payload timing exception')
        if matches(line, 'to', stage) and (command == 'set_false_path' or matches(line, 'from', stage_sources)):
            require(line in expected, 'synchronizer/release stage path masked/overridden')
        if command == 'set_false_path' and matches(line, 'to', first):
            require(line in expected, 'unreviewed first-stage cut')
    selected = {row['id']: {pin for selector in row['selectors']['capture']
                            for pin in result['resolved_pin_selectors'][selector]}
                for row in bundle['payload_groups']}
    uncovered = {row['id']: sorted((set(row['closure']['endpoints']) & set(row['capture_pins'])) - selected[row['id']])
                 for row in result['payload_groups']}
    covered = not any(uncovered.values())
    # Explicit historical audit is never an installation of the new paired
    # policy. In particular e855 has a valid source closure but its old sealed
    # reply lines miss actual D/CE paths; record those pins without promoting it.
    return dict(candidate_constraints_installed=installed and constraint_revision == CONSTRAINT_REVISIONS[0] and covered,
                legacy_constraints_installed=installed and constraint_revision == 'legacy-v1',
                selected_constraint_bundle_installed=installed, constraint_revision=constraint_revision,
                selected_constraint_capture_coverage_verified=covered, uncovered_payload_pins=uncovered,
                current_paired_constraint_revision=CONSTRAINT_REVISIONS[0], proposal_only=not installed,
                reviewed_line_count=50, static_exception_scan_verified=True,
                tool_query_resolution_verified=False, routed_propagation_verified=False)


def run_audit(root, stage, evidence, *, installed=False, constraint_revision=CONSTRAINT_REVISIONS[0]):
    root, stage = Path(root), Path(stage)
    before = verify_synthesis_identity(stage, evidence)
    sources = {p: file_sha(root / p) for p in AUDIT_SOURCES}
    text = (stage / VG_RELATIVE).read_text()
    clocks = audit_runtime_clocks(root, stage, text)
    result = audit_runtime_pcm_cdc(root, text, clocks, reset_policy=prepared_reset_policy(stage),
                                   context_ack_policy=prepared_context_ack_policy(stage))
    sdc = (stage / 'constraints/custom_138k.sdc').read_text()
    installation = validate_constraints(root, sdc, result, installed=installed, constraint_revision=constraint_revision)
    result['constraint_installation'] = installation
    after = verify_synthesis_identity(stage, evidence)
    require(before == after and sources == {p: file_sha(root / p) for p in AUDIT_SOURCES}, 'synthesis or audit inputs changed during audit')
    identity = digest(json.dumps(dict(policy=POLICY, synthesis=before, audit_sources=sources,
                                      installed=installed, constraint_revision=constraint_revision), sort_keys=True).encode())
    result.update(identity='runtime-pcm-context-source-v2-' + identity[:16], source_set_sha256=identity,
        synthesis=before, audit_source_sha256=sources, source_seal_before_and_after=True,
        candidate_constraints_installed=installation['candidate_constraints_installed'],
        selected_constraint_capture_coverage_verified=installation['selected_constraint_capture_coverage_verified'],
        proposal_only=not installed, clock_audit=clocks)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--synthesis-evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--installed', action='store_true', help='Require the exact bundle in sealed synthesis inputs; default is proposal only')
    parser.add_argument('--constraint-revision', choices=CONSTRAINT_REVISIONS, default=CONSTRAINT_REVISIONS[0],
                        help='Explicit historical review only; legacy-v1 never claims paired policy installation')
    args = parser.parse_args()
    result = run_audit(ROOT, args.project, args.synthesis_evidence, installed=args.installed,
                       constraint_revision=args.constraint_revision)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({key: result[key] for key in ('identity', 'payload_source_bits', 'candidate_constraints_installed', 'proposal_only', 'constraints_complete', 'physical_cdc_accepted')}))


if __name__ == '__main__':
    main()
