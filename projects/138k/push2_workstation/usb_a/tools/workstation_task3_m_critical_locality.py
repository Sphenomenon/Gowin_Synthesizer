"""M v40 response round-trip and two actual synchronizer wire failures.

Only the explicit physical policy selects this recipe. The netlist is unchanged;
the response cone, its owner state and earlier held endpoints are exact. Retire
this physical recipe when a routed replacement proves the same boundaries.
"""
from collections import Counter
import hashlib
import re
from tools.workstation_runtime_pcm_cdc import Graph, COMB
from tools.workstation_pinout import parse_locations

KEY = 'm_critical_locality_policy'
POLICY = 'task3_M_v40_response_DQS_PLL_and_held_locality_v1'


def configured(configuration):
    value = configuration.get(KEY)
    if value not in (None, POLICY) or value and configuration.get('demo_role') != 'M':
        raise ValueError('M critical locality requires its explicit M policy')
    return bool(value)


def placement(cst, n):
    g = Graph(n)
    targets = g.group('u_task3_m_pcm_commands', 'response_held', 33)
    comb, sources, seen = set(), set(), set()
    todo = [n.pin(p, 'D') for p in targets]
    while todo:
        net = todo.pop()
        if net in seen:
            continue
        seen.add(net)
        for p, pin in g.drivers[net]:
            if p in g.regs:
                sources.add(p)
            elif n.cells[p]['kind'] in COMB:
                comb.add(p)
                todo.extend(n.pin(p, k) for k in n.cells[p]['ports']
                            if k not in COMB[n.cells[p]['kind']])
    kinds = dict(Counter(n.cells[p]['kind'] for p in comb))
    expected = dict(LUT4=857, MUX2_LUT5=211, ALU=464, LUT3=601,
                    LUT2=75, MUX2_LUT6=34, GND=2, MUX2_LUT7=8)
    if len(comb) != 2252 or kinds != expected:
        raise ValueError('M v40 complete response cone changed')
    native = {p for p in sources if p.startswith((
        'u_managed/runtime/cpu_pcm.owner/',
        'u_task3_m_pcm_commands/request_local_'))}
    if len(native) != 1596 or any(n.pin(p, 'CLK') != 'audio_clk' for p in native | set(targets)):
        raise ValueError('M v40 owner/request response clock or inventory changed')
    text = cst.decode()
    existing = set(re.findall(r'^INS_LOC "([^"]+)" ', text, re.M))
    existing.update(p for line in text.splitlines() if line.startswith('GROUP ')
                    for p in re.findall(r'"([^"]+)"', line))
    # Keep the complete inventory above as a drift check. Place the causal
    # spines of the actual address-response and descriptor-error paths, rather
    # than moving the complete observation/snapshot storage with its mux.
    physical, spine_proofs = set(), []
    owner = 'u_managed/runtime/cpu_pcm.owner'
    mailbox = 'u_task3_m_pcm_commands'
    for source, target, count, expected_kinds in [
        (mailbox+'/request_local_43_s0', mailbox+'/response_held_25_s0',
         38, dict(LUT4=36, LUT3=2)),
        (owner+'/staged_frames_1_s0', mailbox+'/response_held_32_s0',
         179, dict(LUT4=154, LUT3=16, LUT2=9))]:
        forward, seen, todo = set(), set(), [n.pin(source, 'Q')]
        while todo:
            net = todo.pop()
            if net in seen:
                continue
            seen.add(net)
            for p, pin, role in g.fan[net]:
                if role == 'comb':
                    forward.add(p)
                    todo.extend(n.pin(p, k) for k in COMB[n.cells[p]['kind']])
        backward, seen, todo = set(), set(), [n.pin(target, k) for k in ('D', 'CE')]
        while todo:
            net = todo.pop()
            if net in seen:
                continue
            seen.add(net)
            for p, pin in g.drivers[net]:
                kind = n.cells[p]['kind']
                if kind in COMB:
                    backward.add(p)
                    todo.extend(n.pin(p, k) for k in n.cells[p]['ports'] if k not in COMB[kind])
        spine = forward & backward
        if len(spine) != count or dict(Counter(n.cells[p]['kind'] for p in spine)) != expected_kinds:
            raise ValueError('M v40 actual response spine changed: ' + target)
        physical.update(spine)
        spine_proofs.append(dict(source=source, target=target, cells=sorted(spine),
                                 exact_primitive_inventory=expected_kinds))
    if not physical <= comb:
        raise ValueError('M v40 response spine leaves its full cone')
    staged_frames = g.group(owner, 'staged_frames', 32)
    wanted = physical | set(staged_frames)
    selected = wanted - existing
    region = 'R[80:100]C[20:60]'
    lines = [f'INS_LOC "{p}" {region};' for p in sorted(selected)]
    synchronizers = []
    for scope, stem, target in [
        ('u_managed/runtime/', 'fault_sync_', 'R[50:51]C[110:115]'),
        ('', 'task3_m_idle_sync_', 'R[50:51]C[54:59]')]:
        pair = [scope + stem + str(i) + '_s0' for i in range(2)]
        if any(p not in g.regs or n.pin(p, 'CLK') != 'clk_50m' or p in existing for p in pair):
            raise ValueError('M v40 two-stage synchronizer changed: ' + stem)
        lines += [f'INS_LOC "{p}" {target};' for p in pair]
        synchronizers.append(dict(registers=pair, region=target))
    result = cst + ('\n# M v40 actual response and synchronizer wire failures\n' +
                    '\n'.join(lines) + '\n').encode()
    if parse_locations(result.decode()) != parse_locations(text):
        raise ValueError('M v40 IO locations changed')
    sha = lambda data: hashlib.sha256(data).hexdigest()
    return result, dict(policy=POLICY, response_targets=targets,
        exact_response_cone_primitives=kinds, selected=sorted(selected),
        actual_response_spines=spine_proofs,
        selected_count=len(selected), region=region,
        earlier_constraints_preserved=sorted(wanted & existing),
        synchronizers=synchronizers, before_CST_sha256=sha(cst),
        after_CST_sha256=sha(result), logic_changed=False,
        clocks_changed=False, timing_exceptions_changed=False,
        routed_timing_verified=False, hardware_tested=False)
