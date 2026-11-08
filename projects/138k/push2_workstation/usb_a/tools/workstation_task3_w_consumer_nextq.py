"""Read-only W consumer transition comparison; never changes CDC admission.

Compare reset-inclusive next-Q functions under an explicit correspondence of
named state bits in byte-identical owners. This is a conditional one-step
proof, not induction over the complete state relation or whole-design CDC.
Shared expression cuts are exact identical expression DAGs, not net-name
assumptions. Unknown primitives, missing state, or different INIT remain open.
The original parser, source locks and historical consumer seals stay intact.
"""
from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path
import re

from tools.workstation_runtime_pcm_cdc import BooleanDiagram, Graph, PcmNetlist
from tools.workstation_recording_phase1_cdc import complete_closure

TOP = 'workstation_custom_138k_top'
SOURCE = 'u_usb_pll/u_pll_init/enable_r_1_s0'
OWNERS = {
    'u_bluetooth/u_core/application/command_endpoint/cpu_mailbox':
        'rtl/services/workstation_business_mailbox.sv',
    'u_bluetooth/u_core/application/command_endpoint/recording':
        'rtl/bluetooth/cpu_owner/workstation_ble_record_data_engine.sv',
    'u_bluetooth/u_core/application/command_endpoint':
        'rtl/bluetooth/cpu_owner/ble_protocol_command.v',
    'u_bluetooth/u_core/owner/bootstrap':
        'rtl/bluetooth/hci_owner/workstation_hci_host_bootstrap.sv',
    'u_bluetooth/u_core/owner/flow':
        'rtl/bluetooth/hci_owner/workstation_hci_flow_owner.sv',
    'u_bluetooth/u_core/owner/host_rx':
        'rtl/bluetooth/hci_owner/workstation_hci_host_rx_owner.sv',
    'u_bluetooth/u_core/transport':
        'native_bluetooth/bt_h5_transport.v',
    'u_task3_media/raw_store': 'rtl/memory/workstation_ble_raw_ddr_store.sv',
}


def require(value, message):
    if not value:
        raise ValueError('W consumer next-Q: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def logical(path):
    return re.sub(r'_s\d+$', '', path)


class VectorNetlist(PcmNetlist):
    """Compatibility name for diagnostics; strict vector parsing is shared."""


class Expressions:
    def __init__(self):
        self.nodes = [('constant', 0), ('constant', 1)]
        self.unique = {node: i for i, node in enumerate(self.nodes)}

    def node(self, *key):
        if key not in self.unique:
            require(len(self.nodes) < 300000, 'expression bound exceeded')
            self.unique[key] = len(self.nodes)
            self.nodes.append(key)
        return self.unique[key]

    def choose(self, condition, yes, no):
        if condition < 2:
            return yes if condition else no
        if yes == no:
            return yes
        if yes == 1 and no == 0:
            return condition
        return self.node('choose', condition, yes, no)

    def invert(self, value):
        return self.choose(value, 0, 1)

    def xor(self, a, b):
        return self.choose(a, self.invert(b), b)

    def lut(self, inputs, truth):
        if not inputs:
            return truth & 1
        half = 1 << (len(inputs)-1)
        return self.choose(inputs[-1], self.lut(inputs[:-1], truth >> half),
                           self.lut(inputs[:-1], truth & ((1 << half)-1)))

    def closure(self, root):
        result, todo = set(), [root]
        while todo:
            node = todo.pop()
            if node in result:
                continue
            result.add(node)
            if self.nodes[node][0] == 'choose':
                todo.extend(self.nodes[node][1:])
        return result


class Circuit:
    def __init__(self, n, expressions):
        self.n, self.g, self.e, self.memo = n, Graph(n), expressions, {}
        names = {}
        for p in self.g.regs:
            names.setdefault(logical(p), []).append(p)
        self.ambiguous = {name for name, paths in names.items() if len(paths) != 1}
        self.state = {name:paths[0] for name,paths in names.items() if len(paths) == 1}

    def net(self, net, active=()):
        if net in self.g.high | self.g.low:
            return int(net in self.g.high)
        if net in self.memo:
            return self.memo[net]
        require(net not in active, 'combinational cycle: ' + net)
        ds = self.g.drivers[net]
        require(len(ds) == 1, 'unknown/ambiguous driver: ' + net)
        p, port = ds[0]
        cell, kind = self.n.cells[p], self.n.cells[p]['kind']
        if p in self.g.regs:
            require(logical(p) not in self.ambiguous, 'ambiguous named state leaf: ' + p)
            value = self.e.node('state', logical(p))
        else:
            pin = lambda name: self.net(self.n.pin(p, name), (*active, net))
            if kind == 'INV' and port == 'O':
                value = self.e.invert(pin('I'))
            elif re.fullmatch(r'LUT[1-6]', kind) and port == 'F':
                width = int(kind[3:])
                truth = re.fullmatch(r"(\d+)'h([0-9a-fA-F]+)", cell['parameters'].get('INIT', ''))
                require(truth is not None and int(truth[1]) == 1 << width and
                        int(truth[2], 16) < 1 << (1 << width), 'invalid LUT truth: ' + p)
                value = self.e.lut([pin('I'+str(i)) for i in range(width)], int(truth[2], 16))
            elif kind in ('MUX2_LUT5', 'MUX2_LUT6', 'MUX2_LUT7', 'MUX2_LUT8'):
                require(port == 'O' and not cell['parameters'] and
                        set(cell['ports']) == {'O', 'I0', 'I1', 'S0'},
                        'MUX port/parameter inventory: ' + p)
                # GW5A wrappers instantiate the vendor MUX2/mux2 UDP.
                # This diagnostic evaluates its two-valued truth table only.
                value = self.e.choose(pin('S0'), pin('I1'), pin('I0'))
            elif kind == 'ALU':
                mode = cell['parameters'].get('ALU_MODE')
                require(mode in ('0','1','3','4','5') and port in ('SUM','COUT'),
                        'unreviewed ALU: ' + p + '/' + port)
                a, b, carry = pin('I0'), pin('I1'), pin('CIN')
                # Exact GW5A ADD/SUB/NE/GE/LE S,C equations. I3 is
                # unreferenced by these modes in the vendor primitive.
                select = self.e.xor(a,b) if mode == '0' else self.e.invert(self.e.xor(a,b))
                carry_else = 1 if mode == '3' else b if mode == '5' else a
                value = (self.e.xor(select,carry) if port == 'SUM' else
                         self.e.choose(select,carry,carry_else))
            else:
                raise ValueError('W consumer next-Q: unsupported primitive: ' + p + '/' + port)
        self.memo[net] = value
        return value

    def next_q(self, path):
        cell = self.n.cells[path]
        kinds = {'DFFCE': ('CLEAR', 0), 'DFFRE': ('RESET', 0), 'DFFPE': ('PRESET', 1)}
        require(cell['kind'] in kinds, 'unreviewed FF: ' + path)
        reset, default = kinds[cell['kind']]
        require(set(cell['ports']) == {'Q', 'D', 'CLK', 'CE', reset} and
                set(cell['parameters']) <= {'INIT'}, 'FF port/parameter inventory: ' + path)
        init = cell['parameters'].get('INIT', "1'b" + str(default))
        require(init in ("1'b0", "1'b1"), 'unsupported FF INIT')
        e = self.e
        d, ce, assertion, q = [self.net(self.n.pin(path, p)) for p in ('D', 'CE', reset, 'Q')]
        return e.choose(assertion, default, e.choose(ce, d, q)), init, self.n.pin(path, 'CLK')


class ConsumerDiagram(BooleanDiagram):
    """Same exact BDD operations, with a larger explicit input-count bound.

    The shared production class retains its120-input and200000-node limits.
    This isolated diagnostic admits up to2048 independent expression cuts;
    the200000-node limit is unchanged and exhaustion stays inconclusive.
    """
    def __init__(self, inputs):
        require(len(inputs) == len(set(inputs)) <= 2048, 'expression-cut input bound')
        self.nodes, self.unique, self.cache = [None, None], {}, {}
        self.inputs = {net:self.node(i,0,1) for i,net in enumerate(inputs)}


def sat_compare(e, a, b, *, timeout_ms=10000, evidence_dir=None, label='miter'):
    """Exact Boolean miter over unconstrained named leaves; opt-in diagnostic.

    No correlations between distinct named leaves or composite cuts are
    asserted. A result other than unsat never establishes equivalence.
    The expression/input bounds remain the same as the BDD diagnostic.
    """
    import z3
    require(1 <= timeout_ms <= 10000, 'SAT timeout outside diagnostic bound')
    closure = e.closure(a) | e.closure(b)
    leaves = sorted(node for node in closure if e.nodes[node][0] == 'state')
    require(len(leaves) <= 2048, 'SAT named-state input bound')
    values = {0:z3.BoolVal(False), 1:z3.BoolVal(True)}
    # Node IDs are topological: every expression is interned after its children.
    for node in sorted(closure - {0,1}):
        kind, *args = e.nodes[node]
        if kind == 'state':
            values[node] = z3.Bool(args[0])
        else:
            require(kind == 'choose', 'unreviewed SAT expression')
            values[node] = z3.If(*(values[child] for child in args))
    solver = z3.Solver()
    solver.set(timeout=timeout_ms)
    solver.add(z3.Xor(values[a],values[b]))
    smt2 = '(set-option :timeout '+str(timeout_ms)+')\n'+solver.to_smt2()
    artifact = None
    if evidence_dir is not None:
        artifact = Path(evidence_dir)/('miter-'+hashlib.sha256(label.encode()).hexdigest()[:16]+'.smt2')
        require(not artifact.exists(), 'SAT miter evidence exists')
        artifact.write_text(smt2)
    result = solver.check()
    detail = dict(proof_engine='Z3_Boolean_miter', solver_version=z3.get_version_string(),
                  solver_timeout_ms=timeout_ms, solver_result=str(result),
                  solver_reason_unknown=solver.reason_unknown() if result == z3.unknown else None,
                  named_state_inputs=len(leaves), expression_nodes=len(closure),
                  smt2_sha256=hashlib.sha256(smt2.encode()).hexdigest(),
                  smt2_path=str(artifact) if artifact else None)
    if artifact:
        artifact.with_suffix('.result.json').write_text(json.dumps(detail,indent=2)+'\n')
    require(result == z3.unsat,
            'SAT miter ' + str(result) + (': '+solver.reason_unknown() if result == z3.unknown else ''))
    return detail


def compare(old, new, name, *, sat_fallback=False, evidence_dir=None):
    require(name in old.state and name in new.state, 'missing corresponding named state: ' + name)
    a, ai, ac = old.next_q(old.state[name])
    b, bi, bc = new.next_q(new.state[name])
    require(ai == bi and ac == bc, 'INIT or clock differs: ' + name)
    e = old.e
    common = e.closure(a) & e.closure(b)
    # A shared subexpression is exactly identical over the same named state
    # leaves. Treating different shared expressions as independent is stronger
    # than assuming their reachable-state correlations.
    cuts = set()
    def frontier(node):
        if node < 2:
            return
        if node in common:
            cuts.add(node)
        elif e.nodes[node][0] == 'choose':
            for child in e.nodes[node][1:]:
                frontier(child)
        else:
            cuts.add(node)
    frontier(a); frontier(b)
    def attempt(selected):
        bd, memo = ConsumerDiagram(sorted(selected)), {}
        def value(node):
            if node < 2:
                return node
            if node in bd.inputs:
                return bd.inputs[node]
            if node not in memo:
                require(e.nodes[node][0] == 'choose', 'uncut named state')
                memo[node] = bd.choose(*(value(c) for c in e.nodes[node][1:]))
            return memo[node]
        return value(a) == value(b), bd
    try:
        equal, bd = attempt(cuts)
        if not equal:
            # Independent composite cuts may lose relationships with their own
            # descendants. Fall back to exact named state leaves, never assume a
            # relation between composite cuts to manufacture equivalence.
            cuts = {node for node in e.closure(a) | e.closure(b) if e.nodes[node][0] == 'state'}
            equal, bd = attempt(cuts)
        require(equal, 'conditional reset-inclusive next-Q not established: ' + name)
        proof = dict(proof_engine='BDD', independent_expression_cuts=len(cuts),
                     bdd_nodes=len(bd.nodes))
    except ValueError as error:
        # Only BDD node exhaustion admits the optional solver. Missing state,
        # unsupported primitives, input limits and counterexamples still reject.
        if not sat_fallback or str(error) != 'runtime PCM CDC audit: next-Q BDD exceeds reviewed node bound':
            raise
        proof = sat_compare(e,a,b,evidence_dir=evidence_dir,label=name)
        proof['BDD_node_bound_exhausted'] = True
    return dict(register=name, old_cell=old.state[name], new_cell=new.state[name],
                INIT=ai, clock=ac, conditional_next_Q_equal=True,
                **proof,
                named_leaf_correspondence_is_assumption=True,
                asynchronous_event_equivalence_proven=False)


def run(old_output, new_output, output, *, sat_fallback=False):
    if sat_fallback:
        try:
            import z3
        except ImportError as error:
            raise ValueError('W consumer next-Q: --sat-fallback requires Z3 in the selected Python interpreter') from error
    output = Path(output).resolve()
    require(not output.exists(), 'evidence directory exists')
    repository = Path(__file__).resolve().parents[5]
    require(not output.is_relative_to(repository) and
            all(not output.is_relative_to(Path(p).resolve()) for p in (old_output,new_output)),
            'evidence must be outside repository and candidates')
    output.mkdir(parents=True)
    e, circuits, before, sources = Expressions(), {}, {}, {}
    for label, folder in [('old', old_output), ('new', new_output)]:
        stage = Path(folder).resolve()/'workstation/Prj1'
        metadata_path = Path(folder).resolve()/'integration_inputs.json'
        from tools.workstation_task3_paired_audit import verify_prepared
        role, profile, _, _ = verify_prepared(Path(folder),json.loads(metadata_path.read_text()))
        require(role == 'W', 'explicit immutable paired W candidate required')
        vg = stage/'impl/gwsynthesis/custom_138k_integration.vg'
        text = vg.read_text()
        n = VectorNetlist(text, TOP)
        circuits[label] = Circuit(n, e)
        before[str(vg)] = sha(vg)
        before[str(metadata_path)] = sha(metadata_path)
        before[str(Path(folder).resolve()/'workstation_profile.json')] = sha(Path(folder).resolve()/'workstation_profile.json')
        sources[label] = dict(stage=stage, vg=vg,candidate_identity=profile['candidate_identity'])
    old, new = circuits['old'], circuits['new']
    closures = [complete_closure(c.n, c.g, [SOURCE]) for c in (old, new)]
    pins = []
    for c in closures:
        pins.append(Counter((logical(pin.rsplit('/',1)[0]), pin.rsplit('/',1)[1], clock)
                            for pin, clock in c['ff_endpoints'].items()))
    changed = sorted({item[0] for item in (pins[0]-pins[1]) | (pins[1]-pins[0])})
    report = dict(schema='task3-W-conditional-consumer-nextQ-v1',
        candidates={label: str(Path(folder).resolve()) for label, folder in
                    [('old', old_output), ('new', new_output)]},
        source_register=SOURCE, changed_registers=changed, proved=[], pending=[],
        owner_source_sha256={}, original_VG_rewritten=False, historical_seals_modified=False,
        production_auditor_modified=False, whole_source_CDC_accepted=False,
        physical_CDC_accepted=False, routed_timing_verified=False, hardware_tested=False,
        full_state_relation_inductively_proven=False, deployment_allowed=False,
        SAT_fallback_explicitly_enabled=sat_fallback,
        scope='Conditional one-step equality under named state correspondence, not source semantics, initialization/reachability induction, asynchronous reset-event equivalence, or full CDC admission.')
    report['candidate_identities'] = {label:row['candidate_identity'] for label,row in sources.items()}
    report['immutable_prepared_closures_verified'] = True
    report['tools_sha256'] = {str(p):sha(p) for p in (
        Path(__file__).resolve(),Path(__file__).with_name('workstation_runtime_pcm_cdc.py'),
        Path(__file__).with_name('workstation_recording_phase1_cdc.py'))}
    for name in changed:
        try:
            scope = name.rsplit('/',1)[0]
            require(scope in OWNERS, 'owner not explicitly selected: ' + scope)
            relative = OWNERS[scope]
            paths = [sources[label]['stage']/relative for label in ('old','new')]
            require(paths[0].is_file() and paths[1].is_file() and sha(paths[0]) == sha(paths[1]),
                    'owner source absent or differs: ' + relative)
            require(old.n.frames[scope]['kind'] == new.n.frames[scope]['kind'], 'owner module differs')
            for path in paths:
                before[str(path)] = sha(path)
            report['owner_source_sha256'][relative] = sha(paths[0])
            report['proved'].append(compare(old,new,name,sat_fallback=sat_fallback,
                                           evidence_dir=output if sat_fallback else None))
        except ValueError as error:
            report['pending'].append(dict(register=name,reason=str(error)))
    require(before == {p:sha(p) for p in before}, 'immutable input drift during comparison')
    require(report['tools_sha256'] == {p:sha(p) for p in report['tools_sha256']}, 'diagnostic tool drift')
    report.update(inputs_sha256=before, actual_inputs_unchanged=True,
                  diagnostic_completed=True, changed_register_count=len(changed),
                  conditional_equal_count=len(report['proved']), pending_count=len(report['pending']))
    (output/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old',type=Path,required=True)
    parser.add_argument('--new',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--sat-fallback',action='store_true',
                        help='Explicitly permit a 10-second Z3 Boolean miter after BDD node exhaustion')
    args = parser.parse_args()
    result = run(args.old,args.new,args.output,sat_fallback=args.sat_fallback)
    print(json.dumps({key:result[key] for key in
        ('diagnostic_completed','changed_register_count','conditional_equal_count','pending_count')},indent=2))
