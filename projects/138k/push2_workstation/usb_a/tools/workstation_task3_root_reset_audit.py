"""Strict task3 DIRECT/paired root startup proof over actual mapped cells.

No profile selection, RTL, SDC or historical acceptance is changed here.
The consumed source binding and every root state bit are checked separately
from the runtime reset-release and held-boundary proofs owned by the caller.
"""
from pathlib import Path
import hashlib
import json
import re
import xml.etree.ElementTree as ET

from tools.workstation_runtime_pcm_cdc import BooleanDiagram, Graph
from tools.workstation_task3_tf_direct import selected_direct_top
from tools import workstation_task3_m_phone_lease_source as lease_source

POLICY = 'task3-direct-real-root-startup-v1'
PROVIDER = 'rtl/workstation/workstation_profile_task3_m_direct_tf.sv'
ROOT_SOURCE = 'src/platform/reset_release.v'
TOP_SOURCE = 'rtl/workstation/gw138k_push_workstation_top.v'
UNPROFILED_PROVIDER = 'rtl/workstation/workstation_custom_138k_top.sv'
ROOT_SOURCE_SHA256 = 'b5d153b9b0660e3ea9db722d41662a4a7f6f151bc40275b81bfedb15c4e9eac1'
PROVIDER_SHA256 = '1a857e684cde13a83e598cf5d183858ba57e224d46048623974fa6b3716be071'
PAIRED_PROVIDER = 'rtl/workstation/workstation_profile_task3_m_paired.sv'
PAIRED_PROVIDER_SHA256 = 'e5e2764eafdcc59fc9904eae93f4f457cb2bd59595336ac88e878d0bb1e65169'
W_PAIRED_PROVIDER = 'rtl/workstation/workstation_profile_task3_w_paired.sv'
W_PAIRED_PROVIDER_SHA256 = 'a13cd5e6285e7d288a7e1eafe2179831dd339be7f8f8d98b243559124d322dac'
M_PHONE_PROVIDER = 'rtl/workstation/workstation_profile_task3_m_paired_phone_blocks.sv'
M_PHONE_PROVIDER_SHA256 = '799306fde1aa3e0e8fa026e6b23a194e445578208bb0c91bab4d5327255e3f05'
W_PHONE_PROVIDER = 'rtl/workstation/workstation_profile_task3_w_paired_phone_blocks.sv'
W_PHONE_PROVIDER_SHA256 = '9fe33e9ca0551b714882c5fee4018a791945cc80bfc131d8a16fd630111a3503'
M_PHONE_BATCH_PROVIDER = 'rtl/workstation/workstation_profile_task3_m_paired_phone_batch.sv'
M_PHONE_BATCH_PROVIDER_SHA256 = 'a8b49bc23afa8eb0ee1424ec08ae88201143d7455d46c59043ddd6bc296fa56d'
M_SYNC_PROVIDER = 'rtl/workstation/workstation_profile_task3_m_paired_sync_storage.sv'
M_SYNC_PROVIDER_SHA256 = 'aaab25be165322ba25c1c08f22cefcad061c7ab0ba71bee704cf79deddafcc85'
# The one-slot terminal no longer exposes reset directly as terminal_ready.
# Actual v5 synthesis preserves reset_n as the positive started/Q alias.
# This admission is separate from the historical sync-provider mapping.
TERMINAL_ROOT_VARIANT = 'task3-m-terminal-pipeline-root-v1'
TERMINAL_ROOT_PROFILES = (
    'custom138k-workstation-task3-m-paired-checkpoint-v5',
    'custom138k-workstation-task3-m-paired-checkpoint-v6',
)
TERMINAL_ROOT_POLICY = 'task3_m_one_slot_terminal_validation_v1'
TERMINAL_ROOT_SOURCES = {
    'rtl/workstation/workstation_task3_m_bus_endpoint.sv': '5d625039d428ab18d554a70ae9ef9ee9b241eba8421fdd301013baf8ad769908',
    'rtl/music/workstation_task3_score_commit_m.sv': '4486d85295c4da778e1631d39cbf6eccdac416e511eb45899a7fa1f21a1d2722',
}
GROUPED_ROOT_PROFILE='custom138k-workstation-task3-m-paired-checkpoint-v7'
GROUPED_ROOT_VARIANT='task3-m-group8-identity-root-v1'
GROUPED_ROOT_SOURCES=dict(TERMINAL_ROOT_SOURCES,**{
    'rtl/workstation/workstation_task3_m_bus_endpoint.sv': '474b6d2288d968f791a2111e17e8cd4d88844f5f006789719f83e504c1b92acf',
    'rtl/workstation/workstation_task3_m_paired_board.svh': '8948765c295b5c26663f9e958b781678bb7930fecdc7d4d5611f2b99955e51ab',
})
# The full96 phone guard has an exact source inverse to the sealed v7
# endpoint/board. Its source admission is separate; the actual root state and
# batch/mailbox equations below still have to pass on the new mapped design.
PHONE_GROUPED_ROOT_PROFILES=(
    'custom138k-workstation-task3-m-paired-checkpoint-v15',
    'custom138k-workstation-task3-m-paired-checkpoint-v16',
)
PHONE_GROUPED_ROOT_VARIANT='task3-m-phone-group8-identity-root-v1'
PHONE_GROUPED_ROOT_SOURCES=dict(GROUPED_ROOT_SOURCES,**{
    'rtl/workstation/workstation_task3_m_bus_endpoint.sv': 'cd60fb213960963cfd15343660796006ae5f70782ddc681e2f3cc30a4f2ab77d',
    'rtl/workstation/workstation_task3_m_paired_board.svh': '541d91d67db0944c0ac4ad0979d4e1845cc297dbcbc88a2a2868b525346c4c0a',
})
LEASE_SOURCE_ROOT_SOURCES=dict(PHONE_GROUPED_ROOT_SOURCES,**{lease_source.BOARD:lease_source.SELECTED_SHA256})
W_PHONE_BATCH_PROVIDER = 'rtl/workstation/workstation_profile_task3_w_paired_phone_batch.sv'
W_PHONE_BATCH_PROVIDER_SHA256 = '74fa5e601734d495e73119fa98d22c4e3143ee34df9486f8426940e0a8212da4'
W_BANKED96_PROVIDER = 'rtl/workstation/workstation_profile_task3_w_paired_banked96.sv'
W_BANKED96_PROVIDER_SHA256 = '1fba7a44d51bac8b831644d9b04f23d0b688d7615a67bdc136d72bc3e37312f0'
RUNTIME_PROVIDER = 'rtl/workstation/workstation_profile_runtime.sv'
RUNTIME_PROVIDER_SHA256 = '31b1483485ccf454c1c8eeabe8c37198e0975da750a36f850fb91244927a0b3f'
HDMI_PROVIDER = 'rtl/workstation/workstation_profile_hdmi.sv'
HDMI_PROVIDER_SHA256 = '540bf918de8211f84e1394eafa60b653cf817c84b6c28a9e17e234562f36aa82'
W_MEDIA_PROVIDER = 'rtl/workstation/workstation_profile_task3_w_media.sv'
W_MEDIA_PROVIDER_SHA256 = '2b18d6349c509ce8227e389618b96dffb58739b3efe9c2b04388a80f585e1920'
# These aliases were resolved from the actual started FF in each reviewed VG.
# A new provider cannot infer its role or root alias from a convenient net name.
PROVIDER_POLICIES = {
    PROVIDER: (PROVIDER_SHA256, None, 'reset_n', {}),
    PAIRED_PROVIDER: (PAIRED_PROVIDER_SHA256, 'M', 'terminal_ready', {}),
    W_PAIRED_PROVIDER: (W_PAIRED_PROVIDER_SHA256, 'W', 'reset_n', {}),
    M_PHONE_PROVIDER: (M_PHONE_PROVIDER_SHA256, 'M', 'terminal_ready', {}),
    # This wrapper actually includes the old W provider; checking only the
    # wrapper bytes would leave its consumed role/macro selection unbound.
    W_PHONE_PROVIDER: (W_PHONE_PROVIDER_SHA256, 'W', 'reset_n',
                       {W_PAIRED_PROVIDER: W_PAIRED_PROVIDER_SHA256}),
    # Actual batch VGs established these aliases. Root auditing additionally
    # checks the selected role's mapped batch boundary before using them;
    # relabeling an older VG with these exact source wrappers must still fail.
    M_PHONE_BATCH_PROVIDER: (M_PHONE_BATCH_PROVIDER_SHA256, 'M', 'terminal_ready',
        {M_PHONE_PROVIDER: M_PHONE_PROVIDER_SHA256,
         RUNTIME_PROVIDER: RUNTIME_PROVIDER_SHA256, HDMI_PROVIDER: HDMI_PROVIDER_SHA256}),
    # Fresh sync-storage VG 3379e610fc580383... resolves the same positive
    # started Q. Bind the complete wrapper/include chain and invoke the mapped
    # batch proof; a familiar root alias alone never admits a new provider.
    M_SYNC_PROVIDER: (M_SYNC_PROVIDER_SHA256, 'M', 'terminal_ready',
        {M_PHONE_BATCH_PROVIDER: M_PHONE_BATCH_PROVIDER_SHA256,
         M_PHONE_PROVIDER: M_PHONE_PROVIDER_SHA256,
         RUNTIME_PROVIDER: RUNTIME_PROVIDER_SHA256, HDMI_PROVIDER: HDMI_PROVIDER_SHA256}),
    W_BANKED96_PROVIDER: (W_BANKED96_PROVIDER_SHA256, 'W', 'reset_n',
        {W_PHONE_BATCH_PROVIDER: W_PHONE_BATCH_PROVIDER_SHA256,
         W_PAIRED_PROVIDER: W_PAIRED_PROVIDER_SHA256, W_MEDIA_PROVIDER: W_MEDIA_PROVIDER_SHA256}),
    W_PHONE_BATCH_PROVIDER: (W_PHONE_BATCH_PROVIDER_SHA256, 'W', 'reset_n',
        {W_PAIRED_PROVIDER: W_PAIRED_PROVIDER_SHA256, W_MEDIA_PROVIDER: W_MEDIA_PROVIDER_SHA256}),
}


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
    providers = [path for path in selected
                 if path and (path.startswith('rtl/workstation/workstation_profile_')
                              or path == UNPROFILED_PROVIDER)]
    require(len(providers) == 1 and providers[0] in PROVIDER_POLICIES,
            'root requires one uniquely selected reviewed provider')
    provider = providers[0]
    provider_sha, expected_role, _, includes = PROVIDER_POLICIES[provider]
    includes = dict(includes)
    mapping = {}
    if provider == M_SYNC_PROVIDER:
        artifact = json.loads((stage.parent.parent / 'workstation_profile.json').read_text())
        lease_profile=artifact.get('profile') in lease_source.PROFILES
        phone_grouped_profile=artifact.get('profile') in PHONE_GROUPED_ROOT_PROFILES or lease_profile
        grouped_profile=artifact.get('profile')==GROUPED_ROOT_PROFILE or phone_grouped_profile
        terminal_profile = artifact.get('profile') in TERMINAL_ROOT_PROFILES or grouped_profile
        configuration = artifact.get('configuration', {})
        from tools import workstation_task3_demand_identity_compare as demand
        demand_profile=artifact.get('profile') in demand.PROFILES
        require(demand.configured(configuration)==demand_profile,'demand identity root profile/policy mismatch')
        require(lease_source.configured(configuration)==lease_profile,'source-clock lease profile/policy mismatch')
        from tools.workstation_task3_identity_compare import POLICY as IDENTITY_POLICY
        require(configuration.get('m_identity_compare_policy')==
                (IDENTITY_POLICY if grouped_profile else None),'identity root profile/policy mismatch')
        from tools import workstation_task3_phone_identity_compare as phone_identity
        require(configuration.get('m_phone_identity_compare_policy')==
                (phone_identity.POLICY if phone_grouped_profile else None),
                'phone identity root profile/policy mismatch')
        require(configuration.get('m_score_terminal_policy') ==
                (TERMINAL_ROOT_POLICY if terminal_profile else None),
                'terminal root profile/policy mismatch')
        if terminal_profile:
            require(configuration.get('demo_role') == 'M' and
                    configuration.get('m_endpoint_storage_policy') == 'sync_score_and_final_tap_prefetch_v1',
                    'terminal root role/storage policy mismatch')
            reviewed=dict(LEASE_SOURCE_ROOT_SOURCES if lease_profile else PHONE_GROUPED_ROOT_SOURCES if phone_grouped_profile else
                          GROUPED_ROOT_SOURCES if grouped_profile else TERMINAL_ROOT_SOURCES)
            if demand_profile:
                demand.evidence(stage,configuration)
                require(demand.digest(demand.restore_endpoint((stage/demand.ENDPOINT).read_text()))==reviewed[demand.ENDPOINT],
                        'demand identity source does not invert to the reviewed endpoint')
                reviewed[demand.ENDPOINT]=sha(stage/demand.ENDPOINT)
            from tools import workstation_task3_capture_compare as capture
            capture_profile=artifact.get('profile')==capture.PROFILE
            require(capture.configured(configuration)==capture_profile,'capture ordering root profile/policy mismatch')
            if capture_profile:
                capture.evidence(stage,configuration)
                require(capture.digest(capture.restore((stage/capture.SOURCE).read_text()))==capture.PARENT_SHA256,
                        'capture ordering source does not invert to the reviewed batch')
                reviewed[capture.SOURCE]=sha(stage/capture.SOURCE)
            for relative in reviewed:
                require(relative.endswith('.svh') or selected.count(relative) == 1,
                        'terminal root source not uniquely selected: ' + relative)
            includes.update(reviewed)
            if phone_grouped_profile:
                phone_identity.restore_endpoint((stage/phone_identity.ENDPOINT).read_text())
                board=(stage/phone_identity.BOARD).read_text()
                phone_identity.restore_board(lease_source.restore(board) if lease_profile else board)
            mapping = dict(root_mapping_variant=lease_source.ROOT_VARIANT if lease_profile else PHONE_GROUPED_ROOT_VARIANT if phone_grouped_profile else
                           GROUPED_ROOT_VARIANT if grouped_profile else TERMINAL_ROOT_VARIANT,
                           root_profile=artifact['profile'])
    worker = expected_role == 'W'
    require(selected.count(ROOT_SOURCE) == 1,
            'exact root source not uniquely selected')
    # All reviewed providers include this composition transitively. Compiling
    # it again as a standalone unit would bypass that macro/provider scope.
    require(TOP_SOURCE not in selected,
            'included root composition also selected as a standalone unit')
    require((stage / ROOT_SOURCE).is_file() and sha(stage / ROOT_SOURCE) == ROOT_SOURCE_SHA256,
            'reviewed reset_release source/HOLD_CYCLES changed')
    for relative, expected in {provider: provider_sha, **includes}.items():
        require((stage / relative).is_file() and sha(stage / relative) == expected,
                'reviewed root provider/include bytes changed: ' + relative)
    if expected_role is not None:
        from tools.workstation_task3_tf_storage_selection import unwrap_paired_top
        parent, role = unwrap_paired_top(stage, (stage / TOP_SOURCE).read_text())
        if worker:
            from tools.workstation_task3_w_paired_profile import PARENT_TOP_SHA256, digest
        else:
            from tools.workstation_task3_m_paired_profile import PARENT_TOP_SHA256, digest
        require(role == expected_role and digest(parent) == PARENT_TOP_SHA256,
                'paired root exact common/role source inverse changed')
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
    files = (project, stage / provider, stage / ROOT_SOURCE, stage / TOP_SOURCE,
             *(stage / relative for relative in includes))
    return dict(source_sha256={str(path.relative_to(stage)): sha(path) for path in files},
                selected_provider=provider, default_hold_cycles=1024,
                custom_external_reset_constant=1,
                selected_top_root_binding_verified=True, **mapping)


def publisher_policy(root):
    """Select one source-bound reviewed alias; never search for a matching net."""
    provider = root.get('selected_provider')
    require(provider in PROVIDER_POLICIES, 'root publisher provider is not reviewed')
    provider_sha, _, alias, includes = PROVIDER_POLICIES[provider]
    includes = dict(includes)
    variant = root.get('root_mapping_variant')
    if variant is not None:
        grouped=variant==GROUPED_ROOT_VARIANT
        phone_grouped=variant==PHONE_GROUPED_ROOT_VARIANT
        registered=variant==lease_source.ROOT_VARIANT
        require(provider == M_SYNC_PROVIDER and
                ((registered and root.get('root_profile') in lease_source.PROFILES) or
                 (phone_grouped and root.get('root_profile') in PHONE_GROUPED_ROOT_PROFILES) or
                 (grouped and root.get('root_profile')==GROUPED_ROOT_PROFILE) or
                 (variant==TERMINAL_ROOT_VARIANT and root.get('root_profile') in TERMINAL_ROOT_PROFILES)),
                'unreviewed terminal root mapping/profile')
        alias = 'reset_n'
        includes.update(LEASE_SOURCE_ROOT_SOURCES if registered else PHONE_GROUPED_ROOT_SOURCES if phone_grouped else
                        GROUPED_ROOT_SOURCES if grouped else TERMINAL_ROOT_SOURCES)
        from tools import workstation_task3_demand_identity_compare as demand
        if root.get('root_profile') in demand.PROFILES:
            require(registered,'demand root requires the reviewed source-clock lease policy')
            includes[demand.ENDPOINT]=demand.SELECTED_SHA256
        from tools import workstation_task3_capture_compare as capture
        if root.get('root_profile')==capture.PROFILE:
            require(registered,'capture root requires the reviewed source-clock lease policy')
            includes[capture.SOURCE]=capture.SELECTED_SHA256
    else:
        require('root_profile' not in root, 'root profile without mapping policy')
    return provider_sha, alias, includes


def validate_root_publisher(n, g, root):
    """Bind the reviewed source policy to the actual positive root FF output.

    Historical paired mappings use terminal_ready; the source-bound terminal
    pipeline uses reset_n. Both must be the unique, positive actual started Q.
    """
    provider = root.get('selected_provider')
    provider_sha, alias, includes = publisher_policy(root)
    require(isinstance(alias, str) and bool(alias),
            'mapped root alias requires actual synthesis review: ' + provider)
    source_identity = root.get('source_sha256', {})
    require(isinstance(source_identity, dict) and
            set(source_identity) == {'Prj1.gprj', TOP_SOURCE, ROOT_SOURCE, provider, *includes} and
            all(source_identity.get(path) == expected
            for path, expected in {ROOT_SOURCE: ROOT_SOURCE_SHA256,
                                   provider: provider_sha, **includes}.items()),
            'root publisher reviewed provider/source identity changed')
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


def audit_selected_batch_structure(n, *, stage, source=None):
    """Dispatch only exact batch providers; old root policies stay unchanged."""
    source = source_binding(stage) if source is None else source
    provider = source['selected_provider']
    if provider in (M_PHONE_BATCH_PROVIDER, M_SYNC_PROVIDER):
        from tools.workstation_task3_phone_batch_mapped_m import audit
    elif provider in (W_PHONE_BATCH_PROVIDER,W_BANKED96_PROVIDER):
        from tools.workstation_task3_phone_batch_mapped_w import audit
    else:
        return None
    return audit(n, stage=stage)


def audit_root_startup(n, *, stage):
    source = source_binding(stage)
    batch = audit_selected_batch_structure(n, stage=stage, source=source)
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
                   mapped_common_root_name=publisher_policy(source)[1],
                   common_root_output_polarity=1)
    if batch is not None:
        binding['batch_mapped_structure'] = batch
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
