"""Strict task3 DIRECT/paired root startup proof over actual mapped cells.

No profile selection, RTL, SDC or historical acceptance is changed here.
The consumed source binding and every root state bit are checked separately
from the runtime reset-release and held-boundary proofs owned by the caller.
"""
from pathlib import Path
import hashlib
import re
import xml.etree.ElementTree as ET

from tools.workstation_runtime_pcm_cdc import BooleanDiagram, Graph
from tools.workstation_task3_tf_direct import selected_direct_top

POLICY = 'task3-direct-real-root-startup-v1'
PROVIDER = 'rtl/workstation/workstation_profile_task3_m_direct_tf.sv'
ROOT_SOURCE = 'src/platform/reset_release.v'
TOP_SOURCE = 'rtl/workstation/gw138k_push_workstation_top.v'
ROOT_SOURCE_SHA256 = 'b5d153b9b0660e3ea9db722d41662a4a7f6f151bc40275b81bfedb15c4e9eac1'
PROVIDER_SHA256 = '1a857e684cde13a83e598cf5d183858ba57e224d46048623974fa6b3716be071'
PAIRED_PROVIDER = 'rtl/workstation/workstation_profile_task3_m_paired.sv'
PAIRED_PROVIDER_SHA256 = 'e5e2764eafdcc59fc9904eae93f4f457cb2bd59595336ac88e878d0bb1e65169'
W_PAIRED_PROVIDER = 'rtl/workstation/workstation_profile_task3_w_paired.sv'
W_PAIRED_PROVIDER_SHA256 = 'a13cd5e6285e7d288a7e1eafe2179831dd339be7f8f8d98b243559124d322dac'


def require(condition, message):
    if not condition:
        raise ValueError('task3 root reset audit: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_binding(stage):
    stage = Path(stage)
    project = stage / 'Prj1.gprj'
    selected = [row.get('path') for row in ET.parse(project).find('FileList')
                if row.get('enable') == '1']
    provider, provider_sha = PROVIDER, PROVIDER_SHA256
    paired = set(selected).intersection((PAIRED_PROVIDER, W_PAIRED_PROVIDER))
    worker = W_PAIRED_PROVIDER in paired
    if paired:
        from tools.workstation_profile import PROFILE_REGISTRY
        providers = {row['provider'] for row in PROFILE_REGISTRY.values()}
        selected_pair = W_PAIRED_PROVIDER if worker else PAIRED_PROVIDER
        require([path for path in selected if path in providers] == [selected_pair],
                'paired root requires unique explicit role provider')
        from tools.workstation_task3_tf_storage_selection import unwrap_paired_top
        parent, role = unwrap_paired_top(stage, (stage / TOP_SOURCE).read_text())
        if worker:
            from tools.workstation_task3_w_paired_profile import PARENT_TOP_SHA256, digest
        else:
            from tools.workstation_task3_m_paired_profile import PARENT_TOP_SHA256, digest
        require(role == ('W' if worker else 'M') and digest(parent) == PARENT_TOP_SHA256,
                'paired root exact common/role source inverse changed')
        provider, provider_sha = ((W_PAIRED_PROVIDER, W_PAIRED_PROVIDER_SHA256) if worker else
                                  (PAIRED_PROVIDER, PAIRED_PROVIDER_SHA256))
    require(selected.count(provider) == 1 and selected.count(ROOT_SOURCE) == 1,
            'exact DIRECT provider/root source not uniquely selected')
    require(sha(stage / ROOT_SOURCE) == ROOT_SOURCE_SHA256,
            'reviewed reset_release source/HOLD_CYCLES changed')
    require(sha(stage / provider) == provider_sha,
            'reviewed DIRECT provider bytes changed')
    raw_top = (stage / TOP_SOURCE).read_text()
    if worker:
        # The exact paired role inverse above binds every source edit. Unlike
        # M, W has no DIRECT TF provider; its managed PC common assertion is
        # explicitly rebound from button1_n to the actual reset_n root.
        selected_top = raw_top
        instance = re.search(r'workstation_runtime_controlled\s*#\(.*?\)\s*u_managed\s*\(.*?\);',
                             raw_top, re.S)
        require(instance is not None and instance[0].count('.SEPARATE_COMMON_RESET(1)') == 1 and
                instance[0].count('.common_reset_ni(reset_n)') == 1,
                'W paired managed owner common-root binding changed')
    else:
        selected_top, direct = selected_direct_top(stage, raw_top)
        require(direct, 'DIRECT profile not selected')
    # This selector resolves DIRECT conditionals only. The actual parsed top
    # below must still be workstation_custom_138k_top. Bind the custom-side
    # constant and the exact unparameterized root instance without selecting
    # or replacing unrelated preprocessor branches.
    compact = re.sub(r'\s+', '', re.sub(r'//[^\n]*|/\*.*?\*/', '', selected_top, flags=re.S))
    custom = compact.split('moduleworkstation_custom_138k_top', 1)
    require(len(custom) == 2, 'custom top declaration absent')
    custom = custom[1].split('modulegw138k_push_workstation_top', 1)[0]
    require(custom.count("wirebutton1_n=1'b1;") == 1,
            'custom root external assertion is not fixed high')
    require(compact.count('reset_releaseu_reset(.clk(clk_50m),.ext_reset_n(button1_n),.reset_n(reset_n));') == 1,
            'root instance/clock/default HOLD/ext binding changed')
    if not worker:
        require(compact.count('wireruntime_common_reset_n=reset_n;') == 1,
                'DIRECT common reset is not the real root output')
    files = (project, stage / provider, stage / ROOT_SOURCE, stage / TOP_SOURCE)
    return dict(source_sha256={str(path.relative_to(stage)): sha(path) for path in files},
                selected_provider=provider, default_hold_cycles=1024,
                custom_external_reset_constant=1,
                selected_top_root_binding_verified=True)


def validate_root_publisher(n, g, root):
    """Bind the reviewed source policy to the actual positive root FF output.

    The paired top adds terminal_ready consumers, so Gowin chooses that name
    for the same reset_release.started Q and removes the reset_n wire alias.
    Select that one reviewed spelling only for the exact paired provider;
    never accept an arbitrary named reset or an equivalent-looking cone.
    """
    paired = root.get('selected_provider') == PAIRED_PROVIDER
    require(root.get('selected_provider') in (PROVIDER, PAIRED_PROVIDER, W_PAIRED_PROVIDER),
            'root publisher provider is not reviewed')
    alias = 'terminal_ready' if paired else 'reset_n'
    started = g.register('u_reset', 'started')
    q = n.pin(started, 'Q')
    require(root.get('root_register') == started and root.get('root_q') == q and
            root.get('mapped_common_root_name') == alias and
            root.get('common_root_output_polarity') == 1 and
            n.canonical('', alias) == q and q not in g.high | g.low and
            g.drivers[q] == [(started, 'Q')],
            'common root is constant, inverted or disconnected from actual started FF')
    if 'u_reset' in n.frames:
        outputs = [name for name, direction in n.directions[n.frames['u_reset']['kind']].items()
                   if direction == 'output']
        require(len(outputs) == 1 and n.canonical('u_reset', outputs[0]) == q,
                'actual reset_release output is not directly positive started Q')
    else:
        # Routed VO is flat. Its actual reviewed top-net alias must still be
        # the unique FF Q above; a partially parsed hierarchy is not allowed.
        require(set(n.frames) == {''}, 'root hierarchy absent from a non-flat mapping')
    return q


class RootDiagram(BooleanDiagram):
    """Exact LUT/INV plus only GW5A ADD=0 with I3 grounded.

    Official prim_sim.v: S=I0 XOR I1; C=I0; SUM=S XOR CIN;
    COUT=S ? CIN : C. Every other ALU mode and output fails closed.
    """
    def net(self, graph, net, memo=None, active=()):
        memo = {} if memo is None else memo
        if net in self.inputs or net in graph.high | graph.low or net in memo:
            return super().net(graph, net, memo, active)
        drivers = graph.drivers[net]
        if len(drivers) == 1 and graph.n.cells[drivers[0][0]]['kind'] == 'ALU':
            path, output = drivers[0]
            n, cell = graph.n, graph.n.cells[path]
            require(cell['parameters'].get('ALU_MODE') == '0' and
                    n.pin(path, 'I3') in graph.low and output in ('SUM', 'COUT'),
                    'unreviewed root arithmetic primitive: ' + path)
            require(net not in active, 'root arithmetic cycle')
            i0, i1, cin = [self.net(graph, n.pin(path, pin), memo, (*active, net))
                           for pin in ('I0', 'I1', 'CIN')]
            different = self.different(i0, i1)
            value = self.different(different, cin) if output == 'SUM' else self.choose(different, cin, i0)
            memo[net] = value
            return value
        return super().net(graph, net, memo, active)


def audit_root_startup(n, *, stage):
    source = source_binding(stage)
    require(n.frames.get('', {}).get('kind') == 'workstation_custom_138k_top', 'wrong actual top')
    g = Graph(n)
    started = g.register('u_reset', 'started')
    sync = g.group('u_reset', 'sync_ff', 2)
    count = g.group('u_reset', 'startup_count', 32)
    registers = [*sync, *count, started]
    require({path for path in g.regs if path.startswith('u_reset/')} == set(registers),
            'root state register inventory changed')
    for path in registers:
        cell = n.cells[path]
        require(cell['kind'] in ('DFFCE', 'DFFRE') and
                cell['parameters'].get('INIT', "1'b0") == "1'b0",
                'root state primitive/zero INIT changed: ' + path)
        require(n.canonical('', n.pin(path, 'CLK')) == 'clk_50m',
                'root state clock changed: ' + path)
        reset_pin = 'CLEAR' if cell['kind'] == 'DFFCE' else 'RESET'
        require(set(cell['ports']) == {'Q', 'D', 'CLK', 'CE', reset_pin},
                'root state FF port inventory changed: ' + path)
    root_q = n.pin(started, 'Q')
    binding = dict(source, root_register=started, root_q=root_q,
                   mapped_common_root_name=('terminal_ready' if source['selected_provider'] == PAIRED_PROVIDER
                                            else 'reset_n'), common_root_output_polarity=1)
    validate_root_publisher(n, g, binding)
    named = [*(n.pin(path, 'Q') for path in count),
             *(n.pin(path, 'Q') for path in sync), root_q]
    require(len(named) == len(set(named)) == 35, 'root distinct state-bit inventory changed')
    bd = RootDiagram(named)
    memo, rows = {}, []

    def next_q(path):
        cell = n.cells[path]
        actual = bd.choose(bd.net(g, n.pin(path, 'CE'), memo),
                           bd.net(g, n.pin(path, 'D'), memo), bd.inputs[n.pin(path, 'Q')])
        pin = 'CLEAR' if cell['kind'] == 'DFFCE' else 'RESET'
        return bd.choose(bd.net(g, n.pin(path, pin), memo), 0, actual)

    def prove(path, expected, label):
        require(next_q(path) == expected, 'root reset-inclusive next-Q changed: ' + label)
        rows.append(dict(register=path, primitive=n.cells[path]['kind'],
                         clock=n.pin(path, 'CLK'), effective_init=0,
                         contract=label, reset_inclusive_next_q_exact=True))

    prove(sync[0], 1, 'sync_ff0 fills with one')
    prove(sync[1], bd.inputs[n.pin(sync[0], 'Q')], 'sync_ff1 captures exact sync_ff0')
    count_bits = [bd.inputs[n.pin(path, 'Q')] for path in count]
    equal_1023 = bd.all([value if bit < 10 else bd.invert(value)
                         for bit, value in enumerate(count_bits)])
    enabled = bd.inputs[n.pin(sync[1], 'Q')]
    hold = bd.either(bd.inputs[root_q], equal_1023)
    prove(started, bd.both(enabled, hold), 'started: !sync1 -> 0; started or count==1023 -> 1')
    carry = 1
    for bit, path in enumerate(count):
        incremented = bd.different(count_bits[bit], carry)
        expected = bd.both(enabled, bd.choose(hold, count_bits[bit], incremented))
        prove(path, expected, 'startup_count bit %d exact increment/hold/reset' % bit)
        carry = bd.both(carry, count_bits[bit])
    require(len(rows) == 35, 'root proof incomplete')
    return dict(policy=POLICY, **binding,
                actual_state_bits=35, named_inputs=named, root_state_next_q=rows,
                all_state_assignments_proven=True, state_assignment_count=1 << 35,
                bdd_nodes=len(bd.nodes), hold_compare_exact_value=1023,
                first_root_rise_clock_edge_from_zero_init=1026,
                root_stays_high_until_external_reset=True,
                runtime_or_warm_reset_supported=False,
                source_only_external_reset_fixed_high=True,
                primitive_reference='Gowin GW5A prim_sim.v ALU ADD=0 and DFFCE/DFFRE reset-before-CE',
                physical_recovery_removal_verified=False,
                routed_timing_verified=False, hardware_tested=False)
