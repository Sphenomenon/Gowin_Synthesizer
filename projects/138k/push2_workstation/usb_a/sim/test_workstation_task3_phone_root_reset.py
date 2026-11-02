#!/usr/bin/env python3
"""Actual phone-block M/W roots, source selection and fail-closed controls.

Stages and optional independent VGs are explicit inputs. This permits a newly
sealed tools/source stage to review an unchanged earlier hardware netlist
without changing either candidate. No EDA or device operations are launched.
"""
from contextlib import contextmanager
from pathlib import Path
import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_runtime_pcm_cdc import Graph
from tools.workstation_task3_root_reset_audit import (
    audit_root_startup, source_binding, validate_root_publisher,
    ROOT_SOURCE, TOP_SOURCE, PROVIDER, PAIRED_PROVIDER, W_PAIRED_PROVIDER,
    M_PHONE_PROVIDER, W_PHONE_PROVIDER, PROVIDER_POLICIES, UNPROFILED_PROVIDER)
from tools.workstation_task3_peripheral_releases_audit import (
    trace_release, PAIRED_CPU_DESTINATION_CLOSURE)
from tools.workstation_task3_w_paired_cdc_audit import _root_release
from tools.workstation_task3_m_paired_releases_audit import audit_paired_release_sdc

REFERENCES = tuple('rtl/workstation/workstation_task3_' + name + '_top_reference.json'
                   for name in ('m_paired', 'w_paired', 'tf_storage', 'w_media'))
AUDITORS = tuple('tools/' + name + '.py' for name in (
    'workstation_task3_root_reset_audit', 'workstation_task3_tf_direct',
    'workstation_task3_tf_storage_selection', 'workstation_task3_w_media_profile',
    'workstation_task3_m_paired_profile', 'workstation_task3_w_paired_profile',
    'workstation_task3_paired_board', 'workstation_profile',
    'workstation_native_protocol_audit', 'workstation_runtime_pcm_cdc',
    'workstation_recording_phase1_cdc', 'workstation_task3_peripheral_releases_audit',
    'workstation_task3_w_paired_cdc_audit', 'workstation_task3_m_paired_releases_audit',
    'workstation_task3_native_held', 'workstation_task3_receipt_audit'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ActualPhoneRoots(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.actual, cls.before, cls.mutations, cls.failed = {}, {}, [], False
        cls.consumer_gates_rejected = False
        for role, provider in (('M', M_PHONE_PROVIDER), ('W', W_PHONE_PROVIDER)):
            selected = os.environ.get('GW138K_TASK3_PHONE_ROOT_' + role + '_STAGE')
            if not selected:
                raise unittest.SkipTest('explicit M/W source stages required; no cache fallback')
            stage = Path(selected)
            vg = Path(os.environ.get('GW138K_TASK3_PHONE_ROOT_' + role + '_VG',
                      stage / 'impl/gwsynthesis/custom_138k_integration.vg'))
            n = protocol_netlist(vg.read_text(), mapping='synthesis')
            root = audit_root_startup(n, stage=stage)
            if root['selected_provider'] != provider:
                raise AssertionError('actual role must select the new phone-block provider')
            cls.actual[role] = dict(n=n, stage=stage, vg=vg, root=root)
            paths = [vg, *(stage/p for p in root['source_sha256']),
                     *(stage/p for p in REFERENCES if (stage/p).is_file())]
            cls.before.update({str(p): sha(p) for p in paths})

    def tearDown(self):
        result = self._outcome.result
        self.__class__.failed |= bool(result.failures or result.errors)

    @classmethod
    def tearDownClass(cls):
        assert cls.before == {p: sha(p) for p in cls.before}, 'actual candidate inputs changed'
        selected = os.environ.get('GW138K_TASK3_PHONE_ROOT_EVIDENCE')
        if selected:
            Path(selected).write_text(json.dumps(dict(
                status='FAIL' if cls.failed else 'PASS', mapping='synthesis',
                actual_input_sha256=cls.before,
                actual_auditor_source_sha256={p: sha(ROOT/p) for p in AUDITORS},
                regression_source_sha256=sha(__file__),
                actual_root_proofs={role: row['root'] for role, row in cls.actual.items()},
                mutations=cls.mutations, mutation_count=len(cls.mutations),
                historical_complete_consumer_gates_still_reject=cls.consumer_gates_rejected,
                actual_candidates_mutated=False, physical_CDC_accepted=False,
                routed_timing_verified=False, hardware_tested=False), indent=2)+'\n')

    @contextmanager
    def changed(self, n, path, part, key, value):
        target = n.cells[path][part]
        absent = object()
        old = target.get(key, absent)
        target[key] = value
        try:
            yield
        finally:
            if old is absent:
                del target[key]
            else:
                target[key] = old

    def rejected(self, label, function, message=None):
        with self.assertRaises(ValueError) as error:
            function()
        if message is not None:
            self.assertIn(message, str(error.exception))
        self.mutations.append(dict(case=label, rejected=True, error=str(error.exception)))

    def test_actual_roots_keep_exact_all_state_proof(self):
        for role, row in self.actual.items():
            with self.subTest(role=role):
                root = row['root']
                self.assertEqual(root['actual_state_bits'], 35)
                self.assertEqual(root['state_assignment_count'], 1 << 35)
                self.assertEqual(root['hold_compare_exact_value'], 1023)
                self.assertEqual(root['first_root_rise_clock_edge_from_zero_init'], 1026)
                self.assertEqual(root['mapped_common_root_name'],
                                 'terminal_ready' if role == 'M' else 'reset_n')
                self.assertEqual(root['common_root_output_polarity'], 1)
                self.assertTrue(root['all_state_assignments_proven'])
                for field in ('physical_recovery_removal_verified',
                              'routed_timing_verified', 'hardware_tested'):
                    self.assertFalse(root[field])
                for included, expected in PROVIDER_POLICIES[root['selected_provider']][3].items():
                    self.assertEqual(root['source_sha256'][included], expected)

    def test_actual_state_arithmetic_and_publisher_mutants(self):
        for role, row in self.actual.items():
            n, stage, root = row['n'], row['stage'], row['root']
            g = Graph(n)
            started = g.register('u_reset', 'started')
            sync = g.group('u_reset', 'sync_ff', 2)
            count = g.group('u_reset', 'startup_count', 32)
            alu = next(p for p,c in n.cells.items()
                       if p.startswith('u_reset/') and c['kind'] == 'ALU')
            comparator = next(p for p,c in n.cells.items()
                              if p.startswith('u_reset/') and c['kind'] == 'LUT4'
                              and c['parameters'].get('INIT') == "16'h1000")
            cases = (
                ('root INIT', started, 'parameters', 'INIT', "1'b1"),
                ('root clock', started, 'ports', 'CLK', "1'b0"),
                ('root Q disconnected', started, 'ports', 'Q', 'audit_disconnected_root'),
                ('root premature CE', started, 'ports', 'CE', "1'b1"),
                ('root reset removed', started, 'ports', 'RESET', "1'b0"),
                ('sync1 bypass', sync[1], 'ports', 'D', "1'b1"),
                ('sync0 held in clear', sync[0], 'ports', 'CLEAR', "1'b1"),
                ('counter high INIT', count[31], 'parameters', 'INIT', "1'b1"),
                ('counter LSB D', count[0], 'ports', 'D', "1'b0"),
                ('counter high CE', count[31], 'ports', 'CE', "1'b0"),
                ('counter reset removed', count[23], 'ports', 'RESET', "1'b0"),
                ('compare threshold', comparator, 'parameters', 'INIT', "16'h2000"),
                ('unreviewed ALU mode', alu, 'parameters', 'ALU_MODE', '1'),
                ('ALU I3 ungrounded', alu, 'ports', 'I3', "1'b1"),
                ('ALU carry seed', alu, 'ports', 'CIN', "1'b1"),
            )
            for label,p,part,key,value in cases:
                with self.subTest(role=role, case=label), self.changed(n,p,part,key,value):
                    self.rejected(role+' '+label, lambda: audit_root_startup(n, stage=stage))
            p = 'u_reset/audit_extra_state_s0'
            n.cells[p] = copy.deepcopy(n.cells[started])
            n.cells[p]['ports']['Q'] = 'audit_extra_state_q'
            n.scopes[p] = 'u_reset'
            try:
                self.rejected(role+' extra root state', lambda: audit_root_startup(n, stage=stage))
            finally:
                del n.cells[p]; del n.scopes[p]
            other = W_PHONE_PROVIDER if role == 'M' else M_PHONE_PROVIDER
            for label, patch in (
                ('unreviewed provider', dict(selected_provider='unreviewed')),
                ('forged opposite role', dict(selected_provider=other)),
                ('legacy identity substituted', dict(selected_provider=
                    PAIRED_PROVIDER if role == 'M' else W_PAIRED_PROVIDER)),
                ('forged source identity', dict(source_sha256={})),
                ('wrong mapped alias', dict(mapped_common_root_name='preset_n')),
                ('wrong polarity', dict(common_root_output_polarity=0)),
                ('counter as root', dict(root_register=count[0])),
            ):
                self.rejected(role+' '+label, lambda patch=patch:
                    validate_root_publisher(n, Graph(n), dict(root, **patch)))

    def test_compilation_selection_and_source_drift(self):
        for role, row in self.actual.items():
            provider = row['root']['selected_provider']
            old = PAIRED_PROVIDER if role == 'M' else W_PAIRED_PROVIDER
            other = W_PHONE_PROVIDER if role == 'M' else M_PHONE_PROVIDER
            with tempfile.TemporaryDirectory(prefix='task3-phone-root-source-') as directory:
                stage = Path(directory)
                for relative in ('Prj1.gprj', ROOT_SOURCE, TOP_SOURCE,
                                 *PROVIDER_POLICIES, *REFERENCES):
                    source = row['stage']/relative
                    # A sealed role stage need not carry the opposite role's
                    # new wrapper/reference. Use only the other explicitly supplied
                    # actual stage, so wrong-role controls reach the inverse
                    # proof with exact provider bytes rather than fail early
                    # merely because the file is absent.
                    if not source.is_file() and (relative in PROVIDER_POLICIES or relative in REFERENCES):
                        source = self.actual['W' if role == 'M' else 'M']['stage']/relative
                    if source.is_file():
                        path = stage/relative
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(source.read_bytes())
                source_binding(stage)
                self.assertTrue((stage/other).is_file(), 'opposite-role exact provider fixture required')
                project = stage/'Prj1.gprj'
                original = project.read_bytes()
                for label, path, operation in (
                    ('provider disabled', provider, 'disable'),
                    ('provider missing', provider, 'remove'),
                    ('provider duplicate', provider, 'duplicate'),
                    ('mixed old/new', old, 'add'),
                    ('mixed M/W', other, 'add'),
                    ('mixed DIRECT', PROVIDER, 'add'),
                    ('mixed generic top provider', UNPROFILED_PROVIDER, 'add'),
                    ('unknown provider', 'rtl/workstation/workstation_profile_unreviewed.sv', 'replace'),
                    ('opposite role selected', other, 'replace'),
                    ('top compiled outside provider scope', TOP_SOURCE, 'add'),
                    ('root unselected', ROOT_SOURCE, 'disable'),
                    ('root duplicate', ROOT_SOURCE, 'duplicate'),
                ):
                    tree = ET.fromstring(original)
                    files = tree.find('FileList')
                    chosen = next(r for r in files if r.get('path') ==
                                  (provider if operation == 'replace' else path)
                                  and r.get('enable') == '1') if operation != 'add' else None
                    if operation == 'disable': chosen.set('enable', '0')
                    elif operation == 'remove': files.remove(chosen)
                    elif operation == 'duplicate': files.append(copy.deepcopy(chosen))
                    elif operation == 'replace': chosen.set('path', path)
                    else: ET.SubElement(files, 'File', path=path, type='file.verilog', enable='1')
                    project.write_bytes(ET.tostring(tree))
                    try:
                        with self.subTest(role=role, case=label):
                            self.rejected(role+' '+label, lambda: source_binding(stage),
                                          'paired' if operation == 'replace' and path == other else None)
                    finally:
                        project.write_bytes(original)
                common_before, common_after = (
                    ('wire runtime_common_reset_n=reset_n;', "wire runtime_common_reset_n=1'b1;")
                    if role == 'M' else
                    ('.common_reset_ni(reset_n)', ".common_reset_ni(1'b1)"))
                for label, relative, before, after in (
                    ('root HOLD drift', ROOT_SOURCE, 'HOLD_CYCLES = 1024', 'HOLD_CYCLES = 1023'),
                    ('provider macro drift', provider, '`define WORKSTATION_TASK3_PHONE_WINDOW_BLOCK',
                     '// removed WORKSTATION_TASK3_PHONE_WINDOW_BLOCK'),
                    ('top root clock drift', TOP_SOURCE, 'reset_release u_reset(.clk(clk_50m)',
                     'reset_release u_reset(.clk(audio_clk)'),
                    ('top common root drift', TOP_SOURCE, common_before, common_after),
                ):
                    target = stage/relative
                    content = target.read_text()
                    self.assertEqual(content.count(before), 1, label)
                    target.write_text(content.replace(before, after))
                    try:
                        with self.subTest(role=role, case=label):
                            self.rejected(role+' '+label, lambda: source_binding(stage))
                    finally:
                        target.write_text(content)
                reference = stage/('rtl/workstation/workstation_task3_'+role.lower()+'_paired_top_reference.json')
                for label, target in [('paired inverse reference drift', reference)] + (
                        [('included legacy W bytes drift', stage/W_PAIRED_PROVIDER)] if role == 'W' else []):
                    content = target.read_bytes()
                    target.write_bytes(content+b'\n// audit drift\n')
                    try:
                        self.rejected(role+' '+label, lambda: source_binding(stage))
                    finally:
                        target.write_bytes(content)
                source_binding(stage)

    def test_historical_complete_consumer_closures_still_reject(self):
        row = self.actual['M']; n, root = row['n'], row['root']; g = Graph(n)
        self.rejected('M historical complete destination inventory', lambda: trace_release(
            n, g, g.register('u_runtime/u_cpu_cdc', 'destination_data', 0),
            alias_scope='u_task3_pair_link/config_cdc', alias_stem='a_release', clock='clk_50m',
            root_q=root['root_q'], other_reset=n.canonical('', 'preset_n'),
            opaque_cpu_reset=True, expected_final_count=5638,
            paired_final_closure=PAIRED_CPU_DESTINATION_CLOSURE),
            'paired final release complete endpoint inventory changed')
        row = self.actual['W']; n, root = row['n'], row['root']; g = Graph(n)
        self.rejected('W historical complete shared-control inventory', lambda: _root_release(
            n, g, n.pin(g.register('u_managed/pc_bytes', 'held_data', 0), 'CLEAR'),
            root['root_q'], 'clk_50m'), 'W shared PLL/control release complete inventory changed')
        self.__class__.consumer_gates_rejected = True

    def test_phone_m_release_reaches_complete_consumer_gate_and_rejects_w(self):
        row = self.actual['M']
        sdc = (row['stage']/'constraints/custom_138k.sdc').read_text()
        self.rejected('phone M exact release reaches historical complete consumer gate',
            lambda: audit_paired_release_sdc(row['n'], sdc, root=row['root']),
            'paired final release complete consumer inventory changed')
        worker = self.actual['W']
        self.rejected('phone W cannot use M release policy',
            lambda: audit_paired_release_sdc(worker['n'], sdc, root=worker['root']),
            'verified explicit paired M root required')


if __name__ == '__main__':
    unittest.main()
