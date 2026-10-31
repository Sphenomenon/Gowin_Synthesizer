#!/usr/bin/env python3
"""Independent PCM/context source policy and explicit sealed actual-VG negatives."""
from contextlib import contextmanager
from pathlib import Path
import copy
import json
import os
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_runtime_pcm_cdc import (
    B, R, T, Z, TOP, POLICY, PAYLOADS, RESETS, SYNCS, REPLY_FLEX, CONSTRAINT_REVISIONS,
    Graph, PcmNetlist, BooleanDiagram,
    audit_netlist, audit_runtime_clocks, file_sha, prepared_reset_policy, run_audit,
    runtime_pcm_cdc_bundle, validate_constraints, VG_RELATIVE,
)


class RuntimePcmPolicy(unittest.TestCase):
    def test_partial_scope_and_fast_destination_budget(self):
        b = runtime_pcm_cdc_bundle(ROOT)
        self.assertEqual(b['policy'], POLICY)
        self.assertEqual([x['width'] for x in b['payload_groups']], [65, 98, 33, 33])
        self.assertEqual([x['capture_pin_count'] for x in b['payload_groups']], [65, 295, 33, 33])
        old = runtime_pcm_cdc_bundle(ROOT, constraint_revision='legacy-v1')
        self.assertEqual(old['payload_groups'][1]['capture_pin_count'], 263)
        self.assertEqual([i for i, (x, y) in enumerate(zip(b['sdc'].splitlines(), old['sdc'].splitlines())) if x != y], [2, 3])
        with self.assertRaisesRegex(ValueError, 'unknown constraint revision'):
            runtime_pcm_cdc_bundle(ROOT, constraint_revision='auto')
        self.assertEqual(len(b['sdc'].splitlines()), 50)
        self.assertEqual((len(SYNCS), len(RESETS)), (16, 5))
        request = b['payload_groups'][0]
        self.assertEqual(request['minimum_destination_wait_edges'], 2)
        self.assertEqual(request['max_delay_ns'], 13.020)
        self.assertLess(request['max_delay_ns'], 1e9 / 76800000)
        self.assertNotIn('get_clocks', b['sdc'])
        self.assertNotIn('/CLEAR', b['sdc'])
        self.assertNotIn('/PRESET', b['sdc'])
        for key in ('constraints_complete', 'reset_inventory_complete', 'physical_cdc_accepted', 'release_ready', 'deployment_allowed'):
            self.assertFalse(b[key])

    def test_boolean_diagram_truth_tables_and_canonical_equivalence(self):
        # Exhaust every 3-input truth table and its complement, evaluated via
        # independently selected constant assignments. Also check reduction and
        # distributivity, rather than merely comparing the same constructor.
        b = BooleanDiagram(['a', 'b', 'c'])
        inputs = list(b.inputs.values())
        for truth in range(256):
            node = b.lut(inputs, truth)
            self.assertEqual(b.invert(node), b.lut(inputs, truth ^ 255))
            for assignment in range(8):
                current = node
                while current > 1:
                    variable, low, high = b.nodes[current]
                    current = high if (assignment >> variable) & 1 else low
                self.assertEqual(current, (truth >> assignment) & 1)
        a, c, d = inputs
        self.assertEqual(b.both(a, b.either(c, d)), b.either(b.both(a, c), b.both(a, d)))
        self.assertEqual(b.choose(a, c, c), c)

    def test_escaped_named_port_lexical_adapter_preserves_connection(self):
        text = r'''
module child ( x );
output \x ;
DFFCE q_s0 (
 .Q(\x ), .D(1'b0), .CLK(1'b0), .CLEAR(1'b0), .CE(1'b1)
);
endmodule
module top ( y );
wire y;
child c (
 .\x (y)
);
endmodule
'''
        n = PcmNetlist(text, 'top')
        self.assertEqual(n.pin('c/q_s0', 'Q'), 'y')
        self.assertIn('\\x (y)', text)

    def test_duplicate_plain_or_escaped_named_formal_is_rejected(self):
        for binding in (' .x(y), .x(y)', r' .\x (y), .x(y)'):
            text = 'module child ( x );\noutput x;\nendmodule\nmodule top ( y );\nwire y;\nchild c (\n' + binding + '\n);\nendmodule\n'
            with self.subTest(binding=binding), self.assertRaisesRegex(ValueError, 'duplicate/ambiguous named port'):
                PcmNetlist(text, 'top')

    def test_escaped_vector_terminal_is_not_silently_dropped(self):
        text = r'''
module top ( a );
wire [1:0] \a[3] ;
MYSTERY ram (
 .DI({1'b0,\a[3] [1:0]})
);
endmodule
'''
        g = Graph(PcmNetlist(text, 'top'))
        self.assertIn(('ram', 'DI', 'unsupported'), g.fan['\\a[3] [0]'])
        self.assertIn(('ram', 'DI', 'unsupported'), g.fan['\\a[3] [1]'])


class ActualRuntimePcm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stage = os.environ.get('GW138K_RUNTIME_PCM_CDC_STAGE')
        process = os.environ.get('GW138K_RUNTIME_PCM_CDC_PROCESS')
        if not stage or not process:
            raise unittest.SkipTest('set explicit GW138K_RUNTIME_PCM_CDC_STAGE/PROCESS; no EDA or historical fallback')
        cls.stage, cls.process = Path(stage), Path(process)
        cls.installed = os.environ.get('GW138K_RUNTIME_PCM_CDC_INSTALLED') == '1'
        cls.constraint_revision = os.environ.get('GW138K_RUNTIME_PCM_CDC_CONSTRAINT_REVISION', CONSTRAINT_REVISIONS[0])
        cls.text = (cls.stage / VG_RELATIVE).read_text()
        cls.n = PcmNetlist(cls.text, TOP)
        cls.g = Graph(cls.n)
        cls.clocks = audit_runtime_clocks(ROOT, cls.stage, cls.text)
        cls.reset_policy = prepared_reset_policy(cls.stage)
        cls.result = audit_netlist(ROOT, cls.n, cls.clocks, reset_policy=cls.reset_policy)
        cls.sdc = (cls.stage / 'constraints/custom_138k.sdc').read_text()
        cls.bundle = runtime_pcm_cdc_bundle(ROOT, constraint_revision=cls.constraint_revision)
        cls.negative_cases = []

    @classmethod
    def tearDownClass(cls):
        target = os.environ.get('GW138K_RUNTIME_PCM_CDC_TEST_EVIDENCE')
        if target:
            path = Path(target)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(dict(schema=1, policy=POLICY,
                vg_sha256=file_sha(cls.stage / VG_RELATIVE), tests_source_sha256=file_sha(Path(__file__)),
                stage=str(cls.stage), synthesis_process=str(cls.process),
                constraint_revision=cls.constraint_revision,
                complete_closure_counts=[len(x['closure']['endpoints']) for x in cls.result['payload_groups']],
                resolved_selector_count=len(cls.result['resolved_pin_selectors']),
                reply_next_q_proof=cls.result['reply_next_q_proof'],
                negative_control_count=len(cls.negative_cases), negative_controls=cls.negative_cases,
                eda_invoked=False, hardware_operated=False, constraints_complete=False,
                reset_inventory_complete=False, physical_cdc_accepted=False), indent=2, sort_keys=True) + '\n')

    def reg(self, scope, stem, bit=None):
        return self.g.register(scope, stem, bit)

    @contextmanager
    def changed(self, path, *, port=None, parameter=None, value=None):
        cell = self.n.cells[path]
        old = copy.deepcopy(cell)
        try:
            cell['ports' if port else 'parameters'][port or parameter] = value
            yield
        finally:
            cell.clear()
            cell.update(old)

    @contextmanager
    def added(self, path, scope, kind, ports, parameters=None):
        self.assertNotIn(path, self.n.cells)
        self.n.cells[path] = dict(kind=kind, ports=ports, parameters=parameters or {})
        self.n.scopes[path] = scope
        try:
            yield
        finally:
            del self.n.cells[path]
            del self.n.scopes[path]

    def reject(self, name):
        with self.assertRaisesRegex(ValueError, 'runtime PCM CDC audit:') as caught:
            audit_netlist(ROOT, self.n, self.clocks, reset_policy=self.reset_policy)
        self.negative_cases.append(dict(case=name, rejected=True, error=str(caught.exception)))

    def reject_sdc(self, name, text, installed=True):
        with self.assertRaisesRegex(ValueError, 'runtime PCM CDC audit:') as caught:
            validate_constraints(ROOT, text, self.result, installed=installed, constraint_revision=self.constraint_revision)
        self.negative_cases.append(dict(case=name, rejected=True, error=str(caught.exception)))

    def test_01_sealed_source_partial_acceptance(self):
        r = run_audit(ROOT, self.stage, self.process, installed=self.installed, constraint_revision=self.constraint_revision)
        self.assertEqual(r['payload_source_bits'], 229)
        self.assertEqual([len(x['closure']['endpoints']) for x in r['payload_groups']], [65, 263, 141, 207])
        self.assertEqual(len(r['resolved_pin_selectors']), 896)
        self.assertEqual((len(r['synchronization_groups']), len(r['reset_release_groups'])), (16, 5))
        self.assertEqual(len(r['boolean_contracts']), 19)
        self.assertGreater(r['lexical_connection_audit']['escaped_named_port_count'], 0)
        self.assertFalse(r['lexical_connection_audit']['original_vg_rewritten'])
        levels = {x['id']: x for x in r['level_source_boundaries']}
        self.assertEqual(len(levels['ready']['source_registers']), 70)
        self.assertEqual(len(levels['prefill']['source_registers']), 14)
        self.assertTrue(any(x.endswith('/runtime_configuration.failed_s0') for x in levels['fault']['source_registers']))
        self.assertTrue(r['source_seal_before_and_after'])
        self.assertEqual(r['proposal_only'], not self.installed)
        self.assertEqual(r['candidate_constraints_installed'], self.installed and self.constraint_revision == 'paired-nextq-v2')
        self.assertEqual(r['constraint_installation']['selected_constraint_bundle_installed'], self.installed)
        self.assertEqual(r['constraint_installation']['legacy_constraints_installed'], self.installed and self.constraint_revision == 'legacy-v1')
        self.assertEqual(len(levels['quiesce']['source_registers']), 1)
        self.assertEqual(len(levels['resume']['source_registers']), 1)
        self.assertTrue(r['context_comparison_semantics_verified'])
        self.assertTrue(r['reply_capture_header_gate_verified'])
        self.assertTrue(r['reply_effective_next_q_verified'])
        self.assertEqual(r['reply_next_q_proof']['proved_register_count'], 33)
        self.assertEqual(r['reply_next_q_proof']['flexible_consumer_register_count'], 32)
        self.assertFalse(r['reply_next_q_proof']['sampling_used'])
        current = runtime_pcm_cdc_bundle(ROOT)
        coverage = validate_constraints(ROOT, self.sdc.replace(self.bundle['sdc'], '') + current['sdc'],
                                        r, installed=True)
        self.assertTrue(coverage['selected_constraint_capture_coverage_verified'])
        self.assertFalse(any(coverage['uncovered_payload_pins'].values()))
        for key in ('constraints_complete', 'held_payload_complete', 'fifo_payload_complete',
                    'reset_inventory_complete', 'physical_cdc_accepted', 'routed_propagation_verified',
                    'tool_query_resolution_verified', 'hardware_tested', 'release_ready', 'deployment_allowed'):
            self.assertFalse(r[key])

    def test_02_installed_text_is_distinct_from_sealed_installation(self):
        original = self.sdc.replace(self.bundle['sdc'], '') if self.installed else self.sdc
        text = original + self.bundle['sdc']
        result = validate_constraints(ROOT, text, self.result, installed=True, constraint_revision=self.constraint_revision)
        self.assertTrue(result['selected_constraint_bundle_installed'])
        self.assertEqual(result['candidate_constraints_installed'], self.constraint_revision == 'paired-nextq-v2')
        self.assertFalse(result['tool_query_resolution_verified'])
        self.reject_sdc('proposal refuses an already-installed text', text, installed=False)
        self.reject_sdc('missing sealed installation cannot claim installed', original)
        if self.installed:
            with self.assertRaisesRegex(ValueError, 'proposal audit must not silently accept'):
                run_audit(ROOT, self.stage, self.process, constraint_revision=self.constraint_revision)
        else:
            with self.assertRaisesRegex(ValueError, 'installed PCM lines'):
                run_audit(ROOT, self.stage, self.process, installed=True, constraint_revision=self.constraint_revision)

    def test_03_original_twenty_eight_structural_negatives(self):
        for scope, stem, width, toggle in [(B, 'held_request', 65, 'request_toggle'),
                                          (B, 'held_reply', 98, 'reply_toggle'),
                                          (R, 'context_payload', 33, 'context_toggle')]:
            p = self.reg(scope, stem, 0)
            for port in ('CE', 'CLK', 'CLEAR'):
                with self.subTest(stem=stem, port=port), self.changed(p, port=port, value="1'b0"):
                    self.reject(stem + ' source ' + port)
            t = self.reg(scope, toggle)
            with self.changed(t, port='D', value=self.n.cells[t]['ports']['Q']):
                self.reject(stem + ' toggle no transition')
        for scope, stem in [(B, 'request_sync'), (B, 'reply_sync'), (B, 'request_ack_sync'),
                            (B, 'reply_ack_sync'), (R, 'context_sync'), (R, 'ack_sync')]:
            for port in ('D', 'CE'):
                with self.subTest(stem=stem, port=port), self.changed(self.reg(scope, stem, 1), port=port, value="1'b0"):
                    self.reject(stem + ' second ' + port)
        for port in ('D', 'CE'):
            with self.changed(self.reg(B, 'render_epoch_o', 0), port=port, value="1'b0"):
                self.reject('request consumer ' + port)
        for stem in ('serial_reset_n', 'compute_reset_n'):
            with self.changed(self.reg(B, stem), port='D', value="1'b1"):
                self.reject(stem + ' reset release skips two stages')

    def test_04_every_first_stage_source_is_explicit(self):
        for scope, stem, *_ in SYNCS:
            with self.subTest(stem=stem), self.changed(self.reg(scope, stem, 0), port='D', value="1'b0"):
                self.reject(stem + ' first source replaced')

    def test_05_all_global_release_seeds_and_composition_are_verified(self):
        for scope, stem, *_ in RESETS:
            with self.subTest(stem=stem), self.changed(self.reg(scope, stem, 0), port='D', value="1'b0"):
                self.reject(scope + '/' + stem + ' first constant removed')
        if self.reset_policy['mode'] == 'separate-raw-button':
            with self.assertRaisesRegex(ValueError, 'global runtime assertion composition changed'):
                audit_netlist(ROOT, self.n, self.clocks)
            for path, port, value in (
                    (self.reg(R, 'control_release', 0), 'CLEAR', "1'b1"),
                    (self.reg(R, 'startup_compute', 1), 'D', "1'b1"),
                    (self.reg(R, 'compute_release', 1), 'RESET', "1'b0")):
                with self.changed(path, port=port, value=value):
                    self.reject('separate common/startup/local release wrong connection: ' + path + '/' + port)
        else:
            reset = self.n.pin(self.reg(R, 'control_release', 0), 'CLEAR')
            driver = self.g.drivers[reset][0][0]
            with self.changed(driver, parameter='INIT', value="4'h8"):
                self.reject('all reset chains share wrong global assertion')

    def test_06_closure_rejects_extra_ff_memory_and_first_stage_fanout(self):
        q = self.n.cells[self.reg(B, 'held_request', 0)]['ports']['Q']
        ports = dict(Q='rogue', D=q, CLK='audio_clk', CLEAR="1'b0", CE="1'b1")
        with self.added(B + '/rogue_s0', B, 'DFFCE', ports):
            self.reject('payload extra FF consumer')
        with self.added(B + '/rogue_ram', B, 'MYSTERY_RAM', dict(DI='{held_request[1],held_request[0]}')):
            self.reject('payload unknown vector RAM consumer')
        sync = self.n.cells[self.reg(B, 'request_sync', 0)]['ports']['Q']
        with self.added(B + '/rogue_meta_consumer', B, 'MYSTERY_RAM', dict(DI=sync)):
            self.reject('first sync Q unclassified fanout')
        reply = self.n.cells[self.reg(B, 'held_reply', 0)]['ports']['Q']
        with self.added(B + '/rogue_reply_s0', B, 'DFFCE', dict(Q='rogue_reply', D=reply, CLK='serial_clk', CLEAR="1'b0", CE="1'b1")):
            self.reject('reply extra FF cannot enter flexible FF projection')
        reply1 = self.n.cells[self.reg(B, 'held_reply', 1)]['ports']['Q']
        with self.added(B + '/rogue_reply_ram', B, 'MYSTERY_RAM', dict(DI='{' + reply1 + ',' + reply + '}')):
            self.reject('reply unknown memory cannot be filtered away')
            self.assertIn('unsupported primitive', self.negative_cases[-1]['error'])
        p = self.reg(Z, 'wanted_sequence', 1)
        source = self.n.cells[self.reg(Z, 'next_error')]['ports']['D']
        self.assertEqual(self.n.canonical(Z, source), self.n.pin(self.reg(B, 'held_reply', 0), 'Q'))
        with self.changed(p, port='CLEAR', value=source):
            self.reject('reply flexible FF third CLEAR endpoint')
            self.assertIn('exactly one D/CE consumer', self.negative_cases[-1]['error'])
        missing = 'CE' if p + '/D' in self.result['payload_groups'][1]['closure']['endpoints'] else 'D'
        with self.changed(p, port=missing, value=source):
            self.reject('reply flexible FF both D and CE reached')
            self.assertIn('exactly one D/CE consumer', self.negative_cases[-1]['error'])

    def test_07_data_mapping_comparisons_and_capture_truth_tables(self):
        for scope, stem in [(B, 'held_request'), (B, 'held_reply'), (R, 'context_payload')]:
            with self.changed(self.reg(scope, stem, 0), port='D', value="1'b0"):
                self.reject(stem + ' producer tuple wrong')
        for scope, stem in [(R, 'pending_rate'), (R, 'serial_rate'), (Z, 'next_pcm')]:
            p = self.reg(scope, stem, 0 if stem == 'next_pcm' else None)
            driver = self.g.drivers[self.n.pin(p, 'CE')][0][0]
            width = 1 << int(self.n.cells[driver]['kind'][3:])
            with self.changed(driver, parameter='INIT', value=str(width) + "'h0"):
                self.reject(stem + ' capture gate changed')
        ce = self.n.pin(self.reg(R, 'context_payload', 0), 'CE')
        gate = self.g.drivers[ce][0][0]
        comparison = self.n.pin(gate, 'I0')
        p = self.g.drivers[comparison][0][0]
        with self.changed(p, port='I1', value="1'b0"):
            self.reject('context comparator source bit replaced')
        next_ce = self.n.pin(self.reg(Z, 'next_pcm', 0), 'CE')
        carry = next(iter(self.g.carry_frontier(next_ce)))
        p = self.g.drivers[carry][0][0]
        with self.changed(p, parameter='ALU_MODE', value='0'):
            self.reject('reply comparator ALU mode changed')
        p = self.reg(R, 'context_ack')
        driver = self.g.drivers[self.n.pin(p, 'CE')][0][0]
        with self.changed(driver, parameter='INIT', value="16'h0000"):
            self.reject('context ACK before/without applied configuration')

    def test_08_joint_payload_toggle_mutation_cannot_bypass_credit(self):
        source = self.reg(B, 'held_request', 0)
        p = self.reg(B, 'request_toggle')
        old = [copy.deepcopy(self.n.cells[self.reg(B, 'held_request', bit)]) for bit in range(65)]
        try:
            for bit in range(65):
                self.n.cells[self.reg(B, 'held_request', bit)]['ports']['CE'] = 'serial_request'
            with self.added(B + '/joint_s0', B, 'LUT2', dict(F='joint_toggle', I0='request_toggle', I1='serial_request'), dict(INIT="4'h6")):
                with self.changed(p, port='D', value='joint_toggle'):
                    self.reject('joint payload/toggle still publish together but ignore ACK credit')
                    self.assertIn('publication owns free credit', self.negative_cases[-1]['error'])
        finally:
            for bit, cell in enumerate(old):
                target = self.n.cells[self.reg(B, 'held_request', bit)]
                target.clear()
                target.update(cell)

    def test_10_registered_level_publication_and_complete_comparisons(self):
        for stem in ('quiesce_o', 'dac_mute_o'):
            p = self.reg(T, stem)
            for port in ('CLK', 'CE', 'PRESET', 'D'):
                with self.subTest(stem=stem, port=port), self.changed(p, port=port, value="1'b0"):
                    self.reject('registered ' + stem + ' ' + port)
        mute = self.n.pin(self.reg(T, 'dac_mute_o'), 'Q')
        inv = [p for p, c in self.n.cells.items() if self.n.scopes[p] == R and c['kind'] == 'INV'
               and self.n.pin(p, 'I') == mute]
        self.assertEqual(len(inv), 1)
        with self.changed(inv[0], port='I', value="1'b0"):
            self.reject('resume no longer inverts the registered mute source')
        with self.added(R + '/rogue_resume', R, 'INV', dict(I='dac_mute', O='rogue_resume')):
            self.reject('ambiguous resume inverter added')
        ready_net = R + '/rate_context_ready'
        ready = self.g.drivers[ready_net][0][0]
        width = 1 << int(self.n.cells[ready]['kind'][3:])
        with self.changed(ready, parameter='INIT', value=str(width) + "'h0"):
            self.reject('ready return qualifier altered')

        def comparison_cell(output, pair):
            todo, seen, matches = [output], set(), []
            while todo:
                net = todo.pop()
                if net in seen or net in self.g.high | self.g.low:
                    continue
                seen.add(net)
                p, _ = self.g.drivers[net][0]
                if p in self.g.regs:
                    continue
                cell = self.n.cells[p]
                ports = [x for x in cell['ports'] if x not in ('F', 'O', 'COUT', 'SUM')]
                if pair <= {self.n.pin(p, x) for x in ports}:
                    matches.append((p, ports))
                todo.extend(self.n.pin(p, x) for x in ports)
            self.assertEqual(len(matches), 1)
            return matches[0]

        rate_nets = {self.n.pin(self.reg(R, 'context_payload', 32), 'Q'),
                     self.n.pin(self.reg(T, 'pending_44k1'), 'Q')}
        p, ports = comparison_cell(ready_net, rate_nets)
        operands = [x for x in ports if self.n.pin(p, x) in rate_nets]
        self.assertEqual(len(operands), 2)
        with self.changed(p, port=operands[0], value=self.n.cells[p]['ports'][operands[1]]):
            self.reject('ready rate comparison bypassed in carry or scalar gate')
        next_ce = self.n.pin(self.reg(Z, 'next_pcm', 0), 'CE')
        epoch_nets = {self.n.pin(self.reg(Z, 'epoch', 31), 'Q'),
                      self.n.pin(self.reg(B, 'held_reply', 96), 'Q')}
        p, ports = comparison_cell(next_ce, epoch_nets)
        operands = [x for x in ports if self.n.pin(p, x) in epoch_nets]
        self.assertEqual(len(operands), 2)
        with self.changed(p, port=operands[0], value=self.n.cells[p]['ports'][operands[1]]):
            self.reject('reply high epoch bit bypassed in carry or scalar gate')

    def test_11_synthesis_seal_cannot_be_replaced_by_ad_hoc_evidence(self):
        original = json.loads(self.process.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            for label, change in [('VG hash', lambda d: d['output_sha256'].update({VG_RELATIVE: '0' * 64})),
                                  ('input closure', lambda d: d['input_sha256'].update({next(iter(d['input_sha256'])): '0' * 64}))]:
                changed = copy.deepcopy(original)
                change(changed)
                path = Path(tmp) / 'bad_process.json'
                path.write_text(json.dumps(changed))
                with self.assertRaisesRegex(ValueError, 'runtime clock audit:') as caught:
                    run_audit(ROOT, self.stage, path)
                self.negative_cases.append(dict(case='seal ' + label, rejected=True, error=str(caught.exception)))

    def test_12_effective_next_q_d_ce_increment_saturation_and_header_negatives(self):
        # Inversion preserves every source-to-consumer dependency, so closure
        # cannot catch these mutations; the independent next-Q proof must fail.
        for stem, bit in [('wanted_sequence', 1), ('wanted_sequence', 2), ('wanted_sequence', 31), ('underrun_count_o', 0)]:
            p = self.reg(Z, stem, bit)
            for port in ('D', 'CE'):
                original = self.n.cells[p]['ports'][port]
                with self.added(Z + '/negative_nextq_s0', Z, 'INV', dict(I=original, O='negative_nextq')):
                    with self.changed(p, port=port, value='negative_nextq'):
                        self.reject(stem + '[' + str(bit) + '] effective ' + port + ' inverted')
                        self.assertIn('effective next-Q contract changed', self.negative_cases[-1]['error'])

        def cone_cells(nets):
            todo, seen, cells = list(nets), set(), []
            while todo:
                net = todo.pop()
                if net in seen or net in self.g.high | self.g.low or net in self.result['reply_next_q_proof']['header_predicate_cuts']:
                    continue
                seen.add(net)
                p, _ = self.g.drivers[net][0]
                if p in self.g.regs:
                    continue
                cells.append(p)
                todo.extend(self.n.pin(p, pin) for pin in self.n.cells[p]['ports'] if pin not in ('F', 'O', 'COUT', 'SUM'))
            return cells

        # Change lower-bit carry and high-bit saturation inputs inside their
        # actual LUT cones; the reply closure remains unchanged in both forms.
        for target, source, label in [('wanted_sequence', 'wanted_sequence', 'increment propagation'),
                                       ('underrun_count_o', 'underrun_count_o', 'saturation high bit')]:
            bit = 31 if target == 'wanted_sequence' else 0
            target_ff = self.reg(Z, target, bit)
            source_ff = self.reg(Z, source, 0 if target == 'wanted_sequence' else 31)
            source_q = self.n.pin(source_ff, 'Q')
            matches = [(p, pin) for p in cone_cells([self.n.pin(target_ff, 'D'), self.n.pin(target_ff, 'CE')])
                       for pin in self.n.cells[p]['ports'] if pin.startswith('I') and self.n.pin(p, pin) == source_q
                       and self.n.cells[p]['kind'].startswith('LUT')]
            self.assertTrue(matches)
            p, pin = matches[0]
            with self.changed(p, port=pin, value="1'b0"):
                self.reject(label + ' changed')
                self.assertIn('effective next-Q contract changed', self.negative_cases[-1]['error'])

        # The cuts cannot become arbitrary Boolean inputs: their operands and
        # ALU truth model are checked independently before the BDD is built.
        carry = self.result['reply_next_q_proof']['header_predicate_cuts'][0]
        p = self.g.drivers[carry][0][0]
        with self.changed(p, port='I1', value="1'b0"):
            self.reject('next-Q header cut operand changed')
            self.assertIn('reply header', self.negative_cases[-1]['error'])

    def test_13_explicit_legacy_installation_never_promotes_paired_capture(self):
        old = runtime_pcm_cdc_bundle(ROOT, constraint_revision='legacy-v1')
        original = self.sdc.replace(self.bundle['sdc'], '') if self.installed else self.sdc
        old_text = original + old['sdc']
        result = validate_constraints(ROOT, old_text, self.result, installed=True, constraint_revision='legacy-v1')
        self.assertTrue(result['legacy_constraints_installed'])
        self.assertFalse(result['candidate_constraints_installed'])
        actual = set(self.result['payload_groups'][1]['closure']['endpoints'])
        legacy_pins = {pin for selector in old['payload_groups'][1]['selectors']['capture']
                       for pin in self.result['resolved_pin_selectors'][selector]}
        self.assertEqual(result['uncovered_payload_pins']['reply'], sorted(actual - legacy_pins))
        self.assertEqual(result['selected_constraint_capture_coverage_verified'], actual <= legacy_pins)
        with self.assertRaisesRegex(ValueError, 'installed PCM lines'):
            validate_constraints(ROOT, old_text, self.result, installed=True)

    def test_09_constraint_negatives(self):
        original = self.sdc.replace(self.bundle['sdc'], '') if self.installed else self.sdc
        text = original + self.bundle['sdc']
        lines = self.bundle['sdc'].splitlines()
        for index, label in [(0, 'request line missing'), (2, 'reply bypass and CE line missing'),
                             (4, 'context line missing'), (8, 'first D cut missing'), (9, 'resolution line missing')]:
            self.reject_sdc(label, text.replace(lines[index] + '\n', '', 1))
        self.reject_sdc('request relaxed to slow source period', text.replace(lines[0], lines[0].replace('13.020', '59.051'), 1))
        self.reject_sdc('reply hold changed to all false', text.replace(lines[3], lines[3].replace(' -hold', ''), 1))
        self.reject_sdc('duplicate installed constraint', text + lines[0] + '\n')
        self.reject_sdc('unscoped setup cut hides PCM', text + 'set_false_path -to [get_pins {u_managed/runtime/serializer/*/D}]\n')
        self.reject_sdc('broad register false path', text + 'set_false_path -to [get_regs {u_managed/runtime/serializer/*}]\n')
        self.reject_sdc('async reset recovery cut', text + 'set_false_path -to [get_pins {u_managed/runtime/serial_guard_0_s*/CLEAR}]\n')
        self.reject_sdc('whole compute/selected clock cut', text + 'set_false_path -from [get_clocks {audio_76m8}] -to [get_clocks {selected44}]\n')
        self.reject_sdc('second synchronization stage cut', text + 'set_false_path -to [get_pins {u_managed/runtime/bridge/request_sync_1_s*/D}]\n')
        self.reject_sdc('arbitrary max-delay override', text + 'set_max_delay 100.000 -to [get_pins {u_managed/runtime/bridge/render_epoch_o_0_s*/D}]\n')


if __name__ == '__main__':
    unittest.main()
