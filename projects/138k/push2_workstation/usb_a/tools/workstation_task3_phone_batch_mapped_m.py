"""Narrow M batch synthesis proof, independent of historical consumer seals.

This proves actual mapped command/mailbox/snapshot wiring and selected next-Q
equations. It does not prove the whole executor, CDC timing, or board behavior.
Only the explicitly selected batch provider may consume this policy.
"""
from pathlib import Path
import hashlib
import json
import re
import xml.etree.ElementTree as ET

from tools.workstation_runtime_pcm_cdc import BooleanDiagram, COMB, Graph
from tools.workstation_task3_m_paired_profile import (
    BATCH_PROVIDER, SYNC_PROVIDER, SYNC_POLICY, TERMINAL_POLICY, selected_batch_source_evidence,
)

POLICY = 'task3_m_batch_mapped_command_snapshot_v1'
PROFILE = 'custom138k-workstation-task3-m-paired-phone-batch-v1'
BATCH = 'u_task3_m_endpoint/g_phone_batch.batch_m'
MAILBOX = 'u_task3_m_pcm_commands'
RUNTIME = 'u_managed/runtime'
OWNER = RUNTIME + '/cpu_pcm.owner'
# These reviewed implementations are inputs to the proof, not a VG seal.
# Changed implementations require a new review and meaningful mapped negatives.
SOURCE_SHA256 = {
    'rtl/workstation/workstation_task3_phone_batch_m.sv': 'f5d823e777b203655fdd88e0b182df078a887732f343884eaa76b7703740ae2c',
    'rtl/workstation/workstation_task3_m_bus_endpoint.sv': '827ae79416262a64c7fc6d41cdc336e75f4567d431d7b3c7e20c9ffa701e8e70',
    'rtl/workstation/workstation_task3_m_paired_board.svh': '0971e95bc12aad369bae5296ba7ffb0059c548f075a6513dfa7328fc4ca6594d',
    'rtl/workstation/workstation_runtime_controlled.sv': 'bd58103e17b36d9c8d5f9fe1b0346691840417e94beb59a6c12d16c725c7ef8b',
    'rtl/workstation/workstation_runtime_audio.sv': '3170078c72ac8b11d02f0366ee0ffde9b26269237e77430d5b68e9c44aa2bedb',
    'rtl/audio/workstation_ae350_pcm_owner.sv': '7d095570cb94978760b3038b0e31d48a7d070053533d591dc294d36a0b7b319a',
    'src/migration/gw138k_apb_cdc.sv': '99eddbe61b57756f50e97cf108099cdfaf7324b55178808ab4d403bebf9818b7',
}
# This is a separate exact source policy. The older batch inputs above remain
# accepted only under their original providers/profiles and are not re-sealed.
SYNC_SOURCE_SHA256 = dict(SOURCE_SHA256, **{
    SYNC_PROVIDER: 'aaab25be165322ba25c1c08f22cefcad061c7ab0ba71bee704cf79deddafcc85',
    'rtl/workstation/workstation_task3_m_bus_endpoint.sv': 'c42aa3b0158457e50dba9d2ae4eb21af09d4ab0b30aea235272424940181a779',
    'rtl/workstation/workstation_task3_m_paired_board.svh': '3fbed8e7323bed00c36a98e9e71439546dbbb92686fe68ac94683883072c2e33',
    'rtl/music/workstation_task3_score_commit_m.sv': '9bded8544f5e5eef7d7c6427967f99e60ec1a32826bedc510c926dfa97bbbe4c',
    'rtl/workstation/workstation_task3_final_tap_export.sv': 'd7856615e4cfa2446f1a11e28c3348359ca76215bfd9c5e9d1b405f70eb8950c',
})
# The v5 endpoint changes only the collector parameter binding. Keep the old
# source policies immutable; the batch/owner next-Q proof below still runs on
# every actual new VG, independently of the collector behavior regression.
TERMINAL_PROFILE='custom138k-workstation-task3-m-paired-checkpoint-v5'
TERMINAL_PROFILES=(TERMINAL_PROFILE,'custom138k-workstation-task3-m-paired-checkpoint-v6')
TERMINAL_SOURCE_SHA256=dict(SYNC_SOURCE_SHA256,**{
    'rtl/workstation/workstation_task3_m_bus_endpoint.sv': '5d625039d428ab18d554a70ae9ef9ee9b241eba8421fdd301013baf8ad769908',
    'rtl/music/workstation_task3_score_commit_m.sv': '4486d85295c4da778e1631d39cbf6eccdac416e511eb45899a7fa1f21a1d2722',
})
GROUPED_PROFILE='custom138k-workstation-task3-m-paired-checkpoint-v7'
GROUPED_SOURCE_SHA256=dict(TERMINAL_SOURCE_SHA256,**{
    'rtl/workstation/workstation_task3_m_bus_endpoint.sv': '474b6d2288d968f791a2111e17e8cd4d88844f5f006789719f83e504c1b92acf',
    'rtl/workstation/workstation_task3_m_paired_board.svh': '8948765c295b5c26663f9e958b781678bb7930fecdc7d4d5611f2b99955e51ab',
})
SYNC_PROFILES = (
    'custom138k-workstation-task3-m-paired-sync-storage-v1',
    'custom138k-workstation-task3-m-paired-checkpoint-v1',
    'custom138k-workstation-task3-m-paired-checkpoint-v2',
    'custom138k-workstation-task3-m-paired-checkpoint-v3',
    'custom138k-workstation-task3-m-paired-checkpoint-v4',
    *TERMINAL_PROFILES,
    GROUPED_PROFILE,
)


def require(condition, message):
    if not condition:
        raise ValueError('M batch mapped audit: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_evidence(stage):
    """Bind the immutable stage, its real preprocessed selection, and RTL."""
    from tools.workstation_task3_root_reset_audit import source_binding
    stage = Path(stage)
    binding = source_binding(stage)
    provider = binding['selected_provider']
    require(provider in (BATCH_PROVIDER, SYNC_PROVIDER), 'exact M batch provider required')
    artifact = stage.parent.parent / 'workstation_profile.json'
    profile = json.loads(artifact.read_text())
    names = SYNC_PROFILES if provider == SYNC_PROVIDER else (PROFILE,
            'custom138k-workstation-task3-m-paired-phone-batch-tf-v1',
            'custom138k-workstation-task3-m-paired-phone-batch-reset-v1')
    require(profile.get('profile') in names, 'exact M batch profile artifact required')
    require((profile['configuration'].get('m_endpoint_storage_policy') == SYNC_POLICY)
            is (provider == SYNC_PROVIDER), 'M mapped storage policy/provider mismatch')
    grouped_profile=profile.get('profile')==GROUPED_PROFILE
    terminal_profile=profile.get('profile') in TERMINAL_PROFILES or grouped_profile
    terminal_policy=profile['configuration'].get('m_score_terminal_policy')
    require(terminal_policy==(TERMINAL_POLICY if terminal_profile else None),
            'M mapped terminal policy/profile mismatch')
    from tools.workstation_task3_identity_compare import POLICY as IDENTITY_POLICY
    require(profile['configuration'].get('m_identity_compare_policy')==
            (IDENTITY_POLICY if grouped_profile else None),'M mapped identity policy/profile mismatch')
    sources = (GROUPED_SOURCE_SHA256 if grouped_profile else TERMINAL_SOURCE_SHA256 if terminal_profile else
               SYNC_SOURCE_SHA256 if provider == SYNC_PROVIDER else SOURCE_SHA256)
    selected = selected_batch_source_evidence(
        stage, stage, profile['configuration'], provider)
    require(selected is not None, 'snapshot parameter selection absent')
    enabled = [row.get('path') for row in ET.parse(stage / 'Prj1.gprj').find('FileList')
               if row.get('enable') == '1']
    for relative, expected in sources.items():
        require(sha(stage / relative) == expected, 'reviewed source identity changed: ' + relative)
        if not relative.endswith('.svh'):
            require(enabled.count(relative) == 1, 'reviewed source not uniquely selected: ' + relative)
    return dict(root_source=binding, snapshot_selection=selected,
                reviewed_source_sha256=sources.copy(),
                profile_artifact_sha256=sha(artifact),
                full_candidate_manifest_validation=False)


class MappedDiagram(BooleanDiagram):
    """Exact LUT/INV, ADD=0, and NE=3 COUT with I3 grounded only.

    GW5A primitive equations: ADD SUM=I0^I1^CIN and
    COUT=(I0^I1)?CIN:I0. NE COUT=(I0^I1)|CIN. No other
    arithmetic mode or output is admitted by these local Boolean proofs.
    """
    def net(self, graph, net, memo=None, active=()):
        memo = {} if memo is None else memo
        if net in self.inputs or net in graph.high | graph.low or net in memo:
            return super().net(graph, net, memo, active)
        ds = graph.drivers[net]
        if len(ds) == 1 and graph.n.cells[ds[0][0]]['kind'] == 'ALU':
            path, output = ds[0]
            n, cell = graph.n, graph.n.cells[path]
            mode = cell['parameters'].get('ALU_MODE')
            require(n.pin(path, 'I3') in graph.low and
                    ((mode == '0' and output in ('SUM', 'COUT')) or
                     (mode == '3' and output == 'COUT')),
                    'unreviewed arithmetic output: ' + path + '/' + output)
            require(net not in active, 'arithmetic cycle')
            i0, i1, carry = [self.net(graph, n.pin(path, p), memo, (*active, net))
                             for p in ('I0', 'I1', 'CIN')]
            different = self.different(i0, i1)
            value = (self.either(different, carry) if mode == '3' else
                     self.different(different, carry) if output == 'SUM' else
                     self.choose(different, carry, i0))
            memo[net] = value
            return value
        return super().net(graph, net, memo, active)


def support(g, net, active=()):
    if net in g.high | g.low:
        return set()
    require(net not in active, 'combinational support cycle')
    ds = g.drivers[net]
    require(len(ds) == 1, 'driver absent/ambiguous: ' + net)
    path, output = ds[0]
    if path in g.regs:
        return {net}
    cell, n = g.n.cells[path], g.n
    kind = cell['kind']
    if kind == 'INV':
        require(output == 'O', 'inverter output changed')
        ports = ('I',)
    elif re.fullmatch(r'LUT[1-6]', kind):
        require(output == 'F', 'LUT output changed')
        ports = tuple('I' + str(i) for i in range(int(kind[3:])))
    elif kind == 'ALU':
        mode = cell['parameters'].get('ALU_MODE')
        require(n.pin(path, 'I3') in g.low and
                ((mode == '0' and output in ('SUM', 'COUT')) or
                 (mode == '3' and output == 'COUT')), 'unreviewed support arithmetic: ' + path)
        ports = ('I0', 'I1', 'CIN')
    else:
        raise ValueError('M batch mapped audit: unsupported Boolean primitive: ' + path)
    return set().union(*(support(g, n.pin(path, p), (*active, net)) for p in ports))


def prove(g, label, nets, predicate):
    leaves = sorted(set().union(*(support(g, net) for net in nets)))
    bd = MappedDiagram(leaves)
    values = [bd.net(g, net) for net in nets]
    require(predicate(bd, values), 'Boolean contract changed: ' + label)
    return dict(contract=label, leaf_state_bits=len(leaves), state_assignments=1 << len(leaves),
                exact=True, bdd_nodes=len(bd.nodes))


def prove_observer_assertion(g, clear, root, live):
    """Prove root-dependent cones over arbitrary independent cut values.

    The public live level has hundreds of upstream state bits. Only cones
    with a combinational dependency on the actual started Q are expanded;
    every root-independent cone becomes an arbitrary input. This is an
    overapproximation, not an assumption that independent cuts agree.
    """
    dependent, inputs = {}, {}

    def deps(net, active=()):
        if net == root:
            return True
        if net in g.high | g.low:
            return False
        if net in dependent:
            return dependent[net]
        require(net not in active, 'observer assertion combinational cycle')
        ds = g.drivers[net]
        require(len(ds) == 1, 'observer assertion driver absent/ambiguous: ' + net)
        path, output = ds[0]
        if path in g.regs:
            dependent[net] = False
            return False
        cell, n = g.n.cells[path], g.n
        require(cell['kind'] in COMB and output in COMB[cell['kind']],
                'observer assertion unsupported dependency primitive: ' + path)
        pins = [p for p in cell['ports'] if p not in COMB[cell['kind']]]
        inputs[net] = [n.pin(path, p) for p in pins]
        result = any([deps(x, (*active, net)) for x in inputs[net]])
        dependent[net] = result
        return result

    cuts, seen = set(), set()

    def walk(net):
        if net in seen or net == root or net in g.high | g.low:
            return
        seen.add(net)
        if not deps(net):
            cuts.add(net)
        else:
            for value in inputs[net]:
                walk(value)

    walk(clear)
    walk(live)
    bd = MappedDiagram([root, *sorted(cuts)])
    actual, public = bd.net(g, clear), bd.net(g, live)
    require(actual == bd.invert(bd.both(bd.inputs[root], public)) and
            bd.both(public, bd.invert(bd.inputs[root])) == 0,
            'observer assertion/public live root gate changed')
    return dict(contract='mailbox assertion = !(actual root AND public owner live)',
                exact=True, root_Q=root, independent_arbitrary_cut_nets=sorted(cuts),
                proof_input_bits=1 + len(cuts), state_assignments=1 << (1 + len(cuts)),
                cut_overapproximation=True, bdd_nodes=len(bd.nodes))


def audit(n, *, stage):
    source = source_evidence(stage)
    require(n.frames.get('', {}).get('kind') == 'workstation_custom_138k_top', 'wrong mapped top')
    for scope, kind in ((BATCH, 'workstation_task3_phone_batch_m'),
                        (MAILBOX, 'gw138k_apb_cdc_1'),
                        (OWNER, 'workstation_ae350_pcm_owner')):
        require([p for p, frame in n.frames.items() if frame['kind'] == kind] == [scope],
                'actual unique hierarchy missing/changed: ' + scope)
    require(not any('g_no_phone_batch' in p for p in n.frames), 'inactive batch implementation selected')
    g = Graph(n)
    q = lambda path: n.pin(path, 'Q')
    def group(scope, stem, width=None):
        if scope:
            return g.group(scope, stem, width)
        result = []
        for bit in (range(width) if width is not None else (None,)):
            name = stem + ('_' + str(bit) if bit is not None else '')
            found = [p for p in g.regs if re.fullmatch(re.escape(name) + r'_s\d+', p)]
            require(len(found) == 1, 'exact top register missing/duplicate: ' + name)
            result.extend(found)
        require({p for p in g.regs if re.fullmatch(re.escape(stem) +
                (r'_\d+' if width is not None else '') + r'_s\d+', p)} == set(result),
                'top register bit inventory changed: ' + stem)
        return result
    proofs = []

    def ff(paths, clock, clear=None):
        for path in paths:
            cell = n.cells[path]
            require(cell['kind'] == 'DFFCE' and set(cell['ports']) == {'Q', 'D', 'CLK', 'CE', 'CLEAR'} and
                    set(cell['parameters']) <= {'INIT'} and cell['parameters'].get('INIT', "1'b0") == "1'b0",
                    'reviewed zero-init FF changed: ' + path)
            require(n.pin(path, 'CLK') == clock and g.drivers[q(path)] == [(path, 'Q')] and
                    q(path) not in g.high | g.low, 'FF clock/Q changed: ' + path)
            if clear is not None:
                require(n.pin(path, 'CLEAR') == clear, 'FF reset changed: ' + path)
        require(len({q(p) for p in paths}) == len(paths), 'aliased state register group')

    def common(paths, pin):
        values = {n.pin(p, pin) for p in paths}
        require(len(values) == 1, 'non-atomic ' + pin + ' group')
        return next(iter(values))

    root = q(g.register('u_reset', 'started'))
    require(n.frames.get('u_reset') is not None and
            [n.canonical('u_reset', p) for p, d in n.directions[n.frames['u_reset']['kind']].items()
             if d == 'output'] == [root], 'actual positive started Q/output changed')
    batch_reset = n.pin(group(BATCH, 'state', 3)[0], 'CLEAR')
    proofs.append(prove(g, 'M batch/lease reset is actual root only', [batch_reset, root],
                        lambda b, v: v[0] == b.invert(v[1])))
    live = n.canonical('', 'task3_m_phone_live')
    live_sync = group('', 'task3_m_owner_live_sync', 3)
    ff(live_sync, 'audio_clk', batch_reset)
    for bit, path in enumerate(live_sync):
        require(n.pin(path, 'D') == (live if bit == 0 else q(live_sync[bit - 1])) and
                n.pin(path, 'CE') in g.high, 'owner live synchronizer chain changed')

    releases = {stem: group(MAILBOX, stem, 3) for stem in ('p_release', 'a_release')}
    mailbox_clear = n.pin(releases['p_release'][0], 'CLEAR')
    proofs.append(prove_observer_assertion(g, mailbox_clear, root, live))
    for stem, paths in releases.items():
        ff(paths, 'clk_50m' if stem == 'p_release' else 'audio_clk', mailbox_clear)
        for bit, path in enumerate(paths):
            require(n.pin(path, 'CE') in g.high and
                    (n.pin(path, 'D') in g.high if bit == 0 else n.pin(path, 'D') == q(paths[bit - 1])),
                    'mailbox local release chain changed: ' + path)
    p2, a2 = q(releases['p_release'][2]), q(releases['a_release'][2])

    # Owner reset belongs to the original compute release, never the mailbox.
    compute = group(RUNTIME, 'compute_release', 3)
    startup = group(RUNTIME, 'startup_compute', 2)
    ff(compute + startup, 'audio_clk', batch_reset)
    for paths in (compute, startup):
        require(all(n.pin(p, 'CE') in g.high for p in paths), 'owner startup CE changed')
    runtime_reset = n.canonical('', 'runtime_reset_n')
    require(n.pin(startup[0], 'D') == runtime_reset and n.pin(startup[1], 'D') == q(startup[0]),
            'owner startup grant synchronizer changed')
    for bit, path in enumerate(compute):
        expected = [q(startup[1])] + ([q(compute[bit - 1])] if bit else [])
        proofs.append(prove(g, 'owner compute release D bit ' + str(bit),
                            [n.pin(path, 'D'), *expected],
                            lambda b, v: v[0] == b.all(v[1:])))
    owner_clear = n.pin(group(OWNER, 'g_snapshot.capture_id', 32)[0], 'CLEAR')
    compute2 = q(compute[2])
    proofs.append(prove(g, 'original owner reset = !compute release2', [owner_clear, compute2],
                        lambda b, v: v[0] == b.invert(v[1])))
    pipe = group('u_managed', 'reset_compute_pipe', 3)
    ff(pipe, 'audio_clk', batch_reset)
    pipe2 = q(pipe[2])
    cpu_ready = n.canonical('u_managed', 'pcm_owner_reset')
    proofs.append(prove(g, 'observer readiness changes cpu_ready only',
                        [cpu_ready, a2, q(live_sync[2]), pipe2],
                        lambda b, v: v[0] == b.all(v[1:])))

    # All request/response bits cross the same existing held-word mailbox.
    mailbox_groups = {}
    for stem, width, clock, release in (
            ('request_held', 49, 'clk_50m', p2), ('request_local', 49, 'audio_clk', a2),
            ('response_held', 33, 'audio_clk', a2), ('response_local', 33, 'clk_50m', p2)):
        paths = group(MAILBOX, stem, width)
        clear = common(paths, 'CLEAR')
        ff(paths, clock, clear)
        proofs.append(prove(g, stem + ' reset uses mailbox local release', [clear, release],
                            lambda b, v: v[0] == b.invert(v[1])))
        mailbox_groups[stem] = paths
        common(paths, 'CE')
    held, local = mailbox_groups['request_held'], mailbox_groups['request_local']
    response, returned = mailbox_groups['response_held'], mailbox_groups['response_local']
    request_nets = ([n.canonical('', 'task3_m_phone_data[' + str(i) + ']') for i in range(32)] +
                    [n.canonical('', 'task3_m_phone_address[' + str(i) + ']') for i in range(12)] +
                    [n.canonical('', 'task3_m_phone_strobes[' + str(i) + ']') for i in range(4)] +
                    [n.canonical('', 'task3_m_phone_write')])
    local_nets = ([n.canonical('', 'task3_m_pcm_data[' + str(i) + ']') for i in range(32)] +
                  [n.canonical('', 'task3_m_pcm_address[' + str(i) + ']') for i in range(12)] +
                  [n.canonical('', 'task3_m_pcm_strobes[' + str(i) + ']') for i in range(4)] +
                  [n.canonical('', 'task3_m_pcm_write')])
    for bit in range(49):
        require(n.pin(held[bit], 'D') == request_nets[bit] and n.pin(local[bit], 'D') == q(held[bit]) and
                q(local[bit]) == local_nets[bit], 'real command mailbox bit disconnected: ' + str(bit))
    for bit in range(33):
        expected = n.canonical('', 'task3_m_pcm_response[' + str(bit) + ']') if bit < 32 else n.canonical('', 'task3_m_pcm_error')
        require(n.pin(response[bit], 'D') == expected and n.pin(returned[bit], 'D') == q(response[bit]),
                'real response mailbox bit disconnected: ' + str(bit))
        if bit < 32:
            require(q(returned[bit]) == n.canonical('', 'task3_m_pcm_bus_data[' + str(bit) + ']'),
                    'public response data disconnected')
    req_sync = [g.register(MAILBOX, stem) for stem in ('req_meta', 'req_sync', 'req_settled')]
    ack_sync = [g.register(MAILBOX, stem) for stem in ('ack_meta', 'ack_sync', 'ack_settled')]
    for paths, clock, release, launch in (
            (req_sync, 'audio_clk', a2, g.register(MAILBOX, 'request_toggle')),
            (ack_sync, 'clk_50m', p2, g.register(MAILBOX, 'acknowledge_toggle'))):
        clear = common(paths, 'CLEAR')
        ff(paths, clock, clear)
        proofs.append(prove(g, 'mailbox toggle synchronizer local reset ' + clock, [clear, release],
                            lambda b, v: v[0] == b.invert(v[1])))
        for bit, path in enumerate(paths):
            require(n.pin(path, 'D') == q(launch if bit == 0 else paths[bit - 1]) and
                    n.pin(path, 'CE') in g.high, 'mailbox toggle synchronizer changed')
    proofs.append(prove(g, 'request held-word capture at req_sync XOR req_settled',
                        [common(local, 'CE'), q(req_sync[1]), q(req_sync[2])],
                        lambda b, v: v[0] == b.different(v[1], v[2])))
    decoded = q(g.register(MAILBOX, 'request_decoded'))
    req, ack = q(req_sync[2]), q(g.register(MAILBOX, 'acknowledge_toggle'))
    proofs.append(prove(g, 'owner response capture accepts command or revoked observer error',
                        [common(response, 'CE'), a2, decoded, req, ack, q(live_sync[2]), compute2, pipe2],
                        lambda b, v: v[0] == b.both(
                            b.all([v[1], v[2], b.different(v[3], v[4])]),
                            b.either(b.invert(b.both(v[1], v[5])), b.both(v[6], v[7])))))
    mailbox_state = group(MAILBOX, 'state', 2)
    request_toggle = g.register(MAILBOX, 'request_toggle')
    acknowledge = g.register(MAILBOX, 'acknowledge_toggle')
    ff([request_toggle, *mailbox_state], 'clk_50m', common(held, 'CLEAR'))
    ff([acknowledge, g.register(MAILBOX, 'request_decoded')], 'audio_clk', common(local, 'CLEAR'))
    require(n.pin(acknowledge, 'D') == q(req_sync[2]) and
            n.pin(acknowledge, 'CE') == common(response, 'CE'),
            'mailbox request/acknowledge toggle update changed')
    # The actual held-word CE is also the mapped toggle XOR input. Treat that
    # exact shared net as arbitrary: the local identity holds for either CE
    # value and does not require expanding upstream command arbitration.
    if source['root_source']['selected_provider'] == SYNC_PROVIDER:
        # The fresh sync VG maps XOR feedback into D/CE. Check the effective
        # next Q including asynchronous clear, with the real held-word CE as
        # an arbitrary independent input; no upstream arbitration is assumed.
        clear = n.pin(request_toggle, 'CLEAR')
        acceptance = common(held, 'CE')
        bd = MappedDiagram([q(request_toggle), acceptance, clear])
        actual = bd.choose(bd.net(g, n.pin(request_toggle, 'CE')),
                           bd.net(g, n.pin(request_toggle, 'D')), bd.inputs[q(request_toggle)])
        actual = bd.choose(bd.inputs[clear], 0, actual)
        expected = bd.choose(bd.inputs[clear], 0,
                             bd.different(bd.inputs[q(request_toggle)], bd.inputs[acceptance]))
        require(actual == expected, 'request toggle reset-inclusive next-Q changed')
        proofs.append(dict(contract='request toggle changes exactly with held command acceptance',
                           reset_inclusive_next_q_exact=True, independent_inputs=list(bd.inputs),
                           all_input_assignments=8, bdd_nodes=len(bd.nodes),
                           mapped_D=n.pin(request_toggle, 'D'), mapped_CE=n.pin(request_toggle, 'CE'),
                           asynchronous_assertion_bound_by_exact_FF_and_clear=True))
    else:
        require(n.pin(request_toggle, 'CE') in g.high, 'mailbox request toggle enable changed')
        proofs.append(g.equivalent('request toggle changes exactly with held command acceptance',
                            [n.pin(request_toggle, 'D'), q(request_toggle), common(held, 'CE')],
                            lambda v: v[0] == (v[1] ^ v[2]),
                            cuts={q(request_toggle), common(held, 'CE')}))
    proofs.append(prove(g, 'APB response capture waits for matching acknowledge',
                        [common(returned, 'CE'), q(mailbox_state[0]), q(mailbox_state[1]),
                         q(ack_sync[2]), q(g.register(MAILBOX, 'request_toggle'))],
                        lambda b, v: v[0] == b.all([v[1], b.invert(v[2]), b.invert(b.different(v[3], v[4]))])))

    snapshots = [group(BATCH, 'snapshot[' + str(word) + ']', 32) for word in range(20)]
    for word, paths in enumerate(snapshots):
        ff(paths, 'clk_50m', batch_reset)
        common(paths, 'CE')
        for bit, path in enumerate(paths):
            require(n.pin(path, 'D') == n.canonical('', 'task3_m_phone_response[' + str(bit) + ']'),
                    'executor snapshot does not capture real response: ' + str(word) + '/' + str(bit))

    word_bits = {i: tuple(range(32)) for i in (*range(8), 13, 14, 15)}
    word_bits.update({8: (10, 12, 15), 9: tuple(range(8)), 10: tuple(range(4)),
                      11: tuple(range(10)), 12: tuple(range(4))})
    owner_words = [g.register(OWNER, 'g_snapshot.words[' + str(word) + ']', bit)
                   for word, bits in word_bits.items() for bit in bits]
    capture_id = group(OWNER, 'g_snapshot.capture_id', 32)
    valid = group(OWNER, 'g_snapshot.valid')
    all_snapshot = owner_words + capture_id + valid
    actual_snapshot = {p for p in g.regs if p.startswith(OWNER + '/g_snapshot.')}
    require(set(all_snapshot) == actual_snapshot and len(all_snapshot) == 414,
            'owner retained snapshot state inventory changed')
    ff(all_snapshot, 'audio_clk', owner_clear)
    # Escaped vector formals are deliberately not guessed by canonical().
    # Resolve these two exact declared 32-bit sibling port bindings lexically:
    # the session output and owner input share one parent vector, and every
    # source Q / captured D uses the same explicitly numbered local bit.
    session = RUNTIME + '/cpu_pcm.session'
    for word, formal, stem in ((0, 'cpu_pcm.session_epoch', 'epoch_o'),
                               (1, 'cpu_pcm.session_generation', 'generation_o')):
        src = group(session, stem, 32)
        ff(src, 'audio_clk', owner_clear)
        for scope, direction in ((session, 'output'), (OWNER, 'input')):
            frame = n.frames[scope]
            require(n.directions[frame['kind']].get(formal) == direction and
                    n.ranges[frame['kind']].get(formal) == (31, 0) and
                    frame['ports'].get(formal) == '\\' + formal + ' [31:0]',
                    'exact escaped session/owner vector binding changed: ' + formal)
        require(n.scopes[session] == n.scopes[OWNER], 'session/owner parent changed')
        for bit, path in enumerate(src):
            token = '\\' + formal + ' [' + str(bit) + ']'
            dest = g.register(OWNER, 'g_snapshot.words[' + str(word) + ']', bit)
            require(n.cells[path]['ports']['Q'] == token and n.cells[dest]['ports']['D'] == token,
                    'session identity capture bit disconnected: ' + formal + '/' + str(bit))
    # Other full-width words connect directly to the original owner's state.
    # Status/rate/complement words are retained and captured atomically, but
    # their complete data expressions and the read mux are separate scopes.
    data_fields = {2: (OWNER, 'active_controller', 32), 3: (OWNER, 'active_generation', 32),
                   4: (OWNER, 'active_stream', 32), 5: (OWNER, 'active_rate', 32),
                   6: (OWNER, 'active_physical', 32), 7: (RUNTIME, 'compute_epoch', 32),
                   11: (OWNER, 'queued', 10), 12: (OWNER, 'failure', 4),
                   13: (OWNER, 'expected_sequence', 32), 14: (OWNER, 'command_id', 32),
                   15: (OWNER, 'applied_id', 32)}
    for word, (scope, stem, width) in data_fields.items():
        src = group(scope, stem, width)
        ff(src, 'audio_clk', owner_clear)
        for bit, path in enumerate(src):
            dest = g.register(OWNER, 'g_snapshot.words[' + str(word) + ']', bit)
            require(n.pin(dest, 'D') == q(path), 'real owner field snapshot disconnected: ' + str(word) + '/' + str(bit))
    capture_ce = common(owner_words + capture_id, 'CE')
    # Named actual primitive Qs prevent an invented request or source alias
    # from serving as an unconstrained cut at this important boundary.
    named = [*(q(p) for p in capture_id), *(q(p) for p in local[32:44]), q(local[48]),
             a2, q(live_sync[2]), compute2, pipe2, decoded, req, ack]
    bd = MappedDiagram(named)
    bq = lambda path: bd.inputs[q(path)]
    address90 = bd.all([bq(p) if 0x90 >> bit & 1 else bd.invert(bq(p))
                        for bit, p in enumerate(local[32:44])])
    cpu = bd.all([bd.inputs[a2], bq(live_sync[2]), bd.inputs[pipe2]])
    command = bd.all([bd.inputs[decoded], bd.different(bd.inputs[req], bd.inputs[ack]),
                      bd.inputs[a2], bq(live_sync[2])])
    capture = bd.all([address90, bd.invert(bq(local[48])), bd.inputs[compute2], cpu, command])
    saturated = bd.all([bq(p) for p in capture_id])
    expected_capture = bd.both(capture, bd.invert(saturated))
    require(bd.net(g, capture_ce) == expected_capture, 'owner atomic capture/read090 acceptance changed')
    carry = 1
    for path in capture_id:
        require(bd.net(g, n.pin(path, 'D')) == bd.different(bq(path), carry),
                'owner capture ID increment changed: ' + path)
        carry = bd.both(carry, bq(path))
    proofs.append(dict(contract='real command read090 captures all owner words and increments unsaturated ID',
                       exact=True, leaf_state_bits=len(named), state_assignments=1 << len(named),
                       bdd_nodes=len(bd.nodes), common_capture_FFs=413, capture_id_increment_bits=32))
    valid_named = [*named, q(valid[0])]
    vb = MappedDiagram(valid_named)
    actual_valid = vb.choose(vb.net(g, n.pin(valid[0], 'CLEAR')), 0,
                             vb.choose(vb.net(g, n.pin(valid[0], 'CE')),
                                       vb.net(g, n.pin(valid[0], 'D')), vb.inputs[q(valid[0])]))
    # Re-evaluate the proven capture and ready expressions in this ordering.
    ready_v = vb.all([vb.inputs[a2], vb.inputs[q(live_sync[2])], vb.inputs[pipe2]])
    saturated_v = vb.all([vb.inputs[q(p)] for p in capture_id])
    # capture_ce already excludes saturation. A rejected saturated capture
    # must clear valid, so use the independently reconstructed request.
    request_v = vb.all([vb.all([vb.inputs[q(p)] if 0x90 >> bit & 1 else vb.invert(vb.inputs[q(p)])
                               for bit, p in enumerate(local[32:44])]),
                       vb.invert(vb.inputs[q(local[48])]), vb.inputs[compute2], ready_v,
                       vb.inputs[decoded], vb.different(vb.inputs[req], vb.inputs[ack])])
    expected_valid = vb.all([vb.inputs[compute2], ready_v,
                             vb.choose(request_v, vb.invert(saturated_v), vb.inputs[q(valid[0])])])
    require(actual_valid == expected_valid, 'owner snapshot valid reset/revocation/capture next-Q changed')
    proofs.append(dict(contract='owner snapshot valid reset-inclusive exact next-Q', exact=True,
                       leaf_state_bits=len(valid_named), state_assignments=1 << len(valid_named),
                       bdd_nodes=len(vb.nodes)))

    # Gowin merges last_* key state with the identically updated active_* FFs.
    # Check retained primitive state and its root; do not claim a separately
    # named last_* bank or prove the whole new-stream comparator here.
    persistent = [g.register(OWNER, 'retired_key_valid'),
                  *group(OWNER, 'active_controller', 32), *group(OWNER, 'active_generation', 32),
                  *group(OWNER, 'active_stream', 32), *group(OWNER, 'command_id', 32)]
    ff(persistent, 'audio_clk', owner_clear)
    return dict(policy=POLICY, role='M', source_evidence=source,
                mapped_structure_verified=True, actual_root_Q=root,
                batch_scope=BATCH, mailbox_scope=MAILBOX, owner_scope=OWNER,
                executor_snapshot_FFs=640, executor_snapshot_words=20,
                owner_snapshot_FFs=414, owner_snapshot_word_FFs=381,
                owner_capture_id_FFs=32, owner_valid_FFs=1,
                owner_word_retained_bits={str(k): list(v) for k, v in word_bits.items()},
                mailbox_request_bits=49, mailbox_response_bits=33,
                request_and_response_held_word_wiring_verified=True,
                owner_read090_atomic_capture_verified=True,
                owner_snapshot_key_and_counter_field_connections_verified=True,
                owner_snapshot_status_rate_data_semantics_verified=False,
                capture_id_increment_and_observer_retention_verified=True,
                observer_reset_and_owner_root_separation_verified=True,
                proofs=proofs,
                whole_executor_state_machine_verified=False,
                complete_APB_protocol_verified=False,
                owner_snapshot_read_mux_verified=False,
                batch_command_mux_semantics_verified=False,
                response_mux_semantics_verified=False,
                root_35bit_equations_verified=False,
                physical_CDC_accepted=False, routed_timing_verified=False,
                functional_batch_acceptance=False, hardware_tested=False,
                sustained_phone_audio_verified=False, deployment_allowed=False)
