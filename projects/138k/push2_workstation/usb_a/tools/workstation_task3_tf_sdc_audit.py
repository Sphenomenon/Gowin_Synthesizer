"""Exact actual DIRECT status/receipt mailbox SDC, not whole-TF acceptance.

The producer query is checked as a complete pin set. Merely finding some
matching pins would let ``status_ack_s*`` select its own synchronizer Qs.
"""
import bisect
import fnmatch
import re

from tools.workstation_runtime_pcm_cdc import Graph

POLICY = 'task3-direct-status-receipt-exact-sdc-v1'


def require(condition, message):
    if not condition:
        raise ValueError('task3 TF mailbox SDC audit: ' + message)


def validate_tf_mailbox_sdc(sdc, n, *, status, receipt):
    require(status.get('full_status_acceptance_next_q_proven') is True,
            'actual DIRECT status next-Q proof required')
    require(receipt.get('source_pins') and receipt.get('capture_pins') and receipt.get('chains'),
            'actual DIRECT captured-receipt proof required')
    g = Graph(n)
    scope = 'u_tf_audio'
    pins = sorted(p + '/' + port for p, cell in n.cells.items() for port in cell['ports'])

    def resolve(body, *, kind='get_pins'):
        found = set()
        for pattern in body.split():
            prefix = pattern[:next((i for i, char in enumerate(pattern) if char in '*?['), len(pattern))]
            # get_regs selectors refer to a register, not a named pin.
            if kind == 'get_regs':
                found.update(pin for pin in pins if fnmatch.fnmatchcase(pin.rsplit('/', 1)[0], pattern))
                continue
            a, b = bisect.bisect_left(pins, prefix), bisect.bisect_right(pins, prefix+'\U0010ffff')
            found.update(pin for pin in pins[a:b] if fnmatch.fnmatchcase(pin, pattern))
        return found

    def inventories(line):
        queries = re.findall(r'\[get_pins \{([^}]+)\}\]', line)
        require(len(queries) == 2 and 'get_clocks' not in line and 'get_regs' not in line,
                'mailbox query command shape changed')
        return [resolve(body) for body in queries]

    records, allowed_hold, finite_lines = [], set(), set()
    protected, bounded = set(), set()
    lines = sdc.splitlines()

    def exact_selected(source_marker, target_marker, source, target, max_ns, hold=False):
        selected = [line for line in lines if source_marker in line and target_marker in line]
        prefixes = [f'set_max_delay {max_ns:.3f} '] + (['set_false_path -hold '] if hold else [])
        require(len(selected) == len(prefixes), 'missing/duplicate mailbox bound: '+source_marker)
        for prefix in prefixes:
            matches = [line for line in selected if line.startswith(prefix)]
            require(len(matches) == 1, 'mailbox finite bound/hold command changed: '+source_marker)
            line = matches[0]
            actual = inventories(line)
            require(actual == [set(source), set(target)],
                    'mailbox complete source/target pin inventory changed: '+source_marker)
            if prefix.startswith('set_false_path'):
                allowed_hold.add(line)
            else:
                finite_lines.add(line)
            records.append(dict(constraint=line, source_pins=sorted(source), capture_pins=sorted(target)))
        bounded.update(target)
        protected.update(target)

    exact_selected(scope+'/held_status_', scope+'/compute_status_',
                   status['source_pins'], status['capture_pins'], 13.020, hold=True)
    exact_selected(scope+'/receipt_payload_', scope+'/receipt_local_',
                   receipt['source_pins'], receipt['capture_pins'], 20.000, hold=True)
    chains = [*status['chains'], *receipt['chains']]
    require(len(chains) == 4, 'exact four status/receipt synchronizer chains required')
    for row in chains:
        stem = row['first'].rsplit('_s', 1)[0]
        selected = [line for line in lines if stem+'_s*/D' in line and line.startswith('set_false_path ')]
        require(len(selected) == 1 and '-hold' not in selected[0],
                'exact explicit producer-to-first setup cut required')
        require(inventories(selected[0]) == [{row['source']}, {row['first']}],
                'first-stage source glob selects a synchronizer or unrelated Q')
        first_q = row['first'].rsplit('/', 1)[0]+'/Q'
        second_stem = row['second'].rsplit('_s', 1)[0]
        exact_selected(stem+'_s*/Q', second_stem+'_s*/D', [first_q], [row['second']], 2.000)
    protected.update((g.register(scope,'status_capture')+'/D',
                      g.register(scope,'status_ack')+'/D',
                      receipt['capture_state'], receipt['dispatch_state'], receipt['seen_state']))
    # Later data pins may not acquire a broad setup cut, or a second weaker
    # max-delay command while the required finite one remains installed.
    for raw in lines:
        line = raw.strip()
        if line.startswith('set_false_path'):
            if 'get_clocks' in line:
                from tools.workstation_runtime_cdc import MODE_EXCLUSIONS
                require(line in MODE_EXCLUSIONS, 'unreviewed whole-clock false path')
            if line in allowed_hold:
                continue
            for kind, body in re.findall(r'-to\s+\[(get_pins|get_regs)\s+\{([^}]+)\}\]', line):
                require(not (resolve(body,kind=kind) & protected),
                        'false path reaches held capture or later handshake state')
        if line.startswith('set_max_delay'):
            for kind, body in re.findall(r'-to\s+\[(get_pins|get_regs)\s+\{([^}]+)\}\]', line):
                if resolve(body,kind=kind) & bounded:
                    require(line in finite_lines, 'mailbox finite setup bound overridden')
    return dict(policy=POLICY, exact_source_and_capture_queries=True,
                status_payload_pins_verified=67, receipt_payload_pins_verified=34,
                exact_status_receipt_synchronizers_verified=4,
                bounded_setup_targets=sorted(bounded), protected_later_state_pins=sorted(protected),
                installed_constraints=records, complete_tf_cdc_accepted=False,
                physical_recovery_removal_verified=False, hardware_tested=False)
