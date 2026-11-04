#!/usr/bin/env python3
"""Strict new W batch provider selection against actual preprocessed source.

An explicitly supplied immutable W stage provides unrelated vendor inputs.
Fixtures are copied and receive the maintained batch sources only; this does
not refresh old profile seals or claim production prepare/physical acceptance.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_task3_w_paired_profile as paired


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class WPhoneBatchSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = dict(configurations=[], negative_controls=[], provider_mutations=[])
        cls.tracked = [Path(__file__), ROOT / 'tools/workstation_task3_w_paired_profile.py',
            ROOT / 'tools/workstation_task3_paired_board.py', ROOT / paired.BOARD,
            ROOT / paired.PROVIDER, ROOT / paired.PHONE_PROVIDER, ROOT / paired.BATCH_PROVIDER,
            ROOT / 'rtl/workstation/workstation_task3_w_bus_endpoint.sv',
            ROOT / 'rtl/workstation/workstation_task3_phone_window_tx.sv',
            ROOT / 'rtl/workstation/workstation_task3_phone_batch_w.sv',
            ROOT / 'rtl/workstation/task3_paired_channels.vh']
        cls.evidence['input_sha256'] = {str(path): sha(path) for path in cls.tracked}

    def setUp(self):
        type(self).test_result = self._outcome.result

    @classmethod
    def tearDownClass(cls):
        target = os.environ.get('GW138K_TASK3_W_BATCH_SELECTION_EVIDENCE')
        if target:
            cls.evidence['inputs_unchanged'] = cls.evidence['input_sha256'] == {
                str(path): sha(path) for path in cls.tracked}
            complete = (cls.test_result.wasSuccessful() and len(cls.evidence['configurations']) == 3
                        and cls.evidence.get('policy_combinations_checked') is True
                        and cls.evidence['inputs_unchanged'])
            Path(target).write_text(json.dumps(dict(cls.evidence, passed=complete,
                actual_source_preprocessing=True, production_preparation=False,
                synthesis_verified=False, physical_timing_verified=False,
                hardware_tested=False), indent=2) + '\n')

    def batch_configuration(self):
        return dict(phone_batch_policy=paired.PHONE_BATCH_POLICY,
                    phone_window_policy='posted_window5_single_inflight_applied_barrier_v1',
                    interboard_media_policy=paired.BATCH_MEDIA_POLICY,
                    ae350_firmware_policy=paired.BATCH_FIRMWARE_POLICY,
                    cnn_memory_policy='task3_w_signal_cqt_bsram_v1')

    def test_01_exact_policy_combinations(self):
        batch = self.batch_configuration()
        self.assertEqual(paired.cnn_memory_configuration(batch), paired.cnn_memory_provider(paired.BATCH_PROVIDER))
        self.assertEqual(paired.cnn_memory_configuration({})['provider'], paired.PROVIDER)
        legacy = dict(phone_window_policy='posted_window5_single_inflight_applied_barrier_v1')
        self.assertEqual(paired.cnn_memory_configuration(legacy)['provider'], paired.PHONE_PROVIDER)
        for key in batch:
            for value in (None, False, 0, 'unregistered'):
                changed = dict(batch, **{key: value})
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    paired.cnn_memory_configuration(changed)
            changed = dict(batch)
            changed.pop(key)
            if key != 'cnn_memory_policy':
                with self.subTest(missing=key), self.assertRaises(ValueError):
                    paired.cnn_memory_configuration(changed)
        for key, value in (('interboard_media_policy', paired.BATCH_MEDIA_POLICY),
                           ('ae350_firmware_policy', paired.BATCH_FIRMWARE_POLICY)):
            with self.assertRaises(ValueError):
                paired.cnn_memory_configuration(dict(legacy, **{key: value}))
        for provider in ('unregistered.sv', None, False, paired.BATCH_PROVIDER + '.bak'):
            with self.assertRaises(ValueError):
                paired.cnn_memory_provider(provider)
        self.evidence['policy_combinations_checked'] = True

    def test_02_actual_wrapper_scope(self):
        with tempfile.TemporaryDirectory(prefix='task3-w-batch-wrapper-') as temp:
            stage = Path(temp)
            for relative in (paired.PROVIDER, paired.BATCH_PROVIDER):
                target = stage / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            wrapper = stage / paired.BATCH_PROVIDER
            original = wrapper.read_text()
            proof = paired.verify_batch_provider(stage, paired.BATCH_PROVIDER)
            self.assertTrue(proof['phone_batch'])
            self.assertEqual(proof['included_provider_sha256'], sha(ROOT / paired.PROVIDER))
            for name, old, new in (
                ('missing-batch-flag', '`define WORKSTATION_TASK3_PHONE_BATCH\n', ''),
                ('missing-window-flag', '`define WORKSTATION_TASK3_PHONE_WINDOW_BLOCK\n', ''),
                ('missing-batch-undef', '`undef WORKSTATION_TASK3_PHONE_BATCH\n', ''),
                ('wrong-role-include', paired.PROVIDER, paired.PHONE_PROVIDER),
                ('scope-closes-before-include', '`include "' + paired.PROVIDER + '"\n',
                 '`undef WORKSTATION_TASK3_PHONE_BATCH\n`include "' + paired.PROVIDER + '"\n'),
            ):
                self.assertEqual(original.count(old), 1)
                wrapper.write_text(original.replace(old, new, 1))
                with self.subTest(mutation=name), self.assertRaises(ValueError):
                    paired.verify_batch_provider(stage, paired.BATCH_PROVIDER)
                self.evidence['provider_mutations'].append(dict(name=name, rejected=True))
            wrapper.write_text(original)
            (stage / paired.PROVIDER).unlink()
            with self.assertRaises(ValueError):
                paired.verify_batch_provider(stage, paired.BATCH_PROVIDER)

    def fixture(self, parent, stage, provider):
        shutil.copytree(parent, stage, ignore=shutil.ignore_patterns('impl'))
        selected = (paired.PROVIDER, paired.PHONE_PROVIDER, paired.BATCH_PROVIDER, paired.BOARD,
            'rtl/workstation/workstation_task3_w_bus_endpoint.sv',
            'rtl/workstation/workstation_task3_phone_batch_w.sv',
            'rtl/workstation/workstation_task3_phone_window_tx.sv',
            'rtl/workstation/task3_paired_channels.vh')
        for relative in selected:
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        tree = ET.parse(stage / 'Prj1.gprj')
        rows = tree.find('FileList')
        providers = [row for row in rows if row.get('enable') == '1' and
                     row.get('path', '').startswith('rtl/workstation/workstation_profile_')]
        self.assertEqual(len(providers), 1)
        providers[0].set('path', provider)
        source = 'rtl/workstation/workstation_task3_phone_batch_w.sv'
        self.assertEqual(sum(row.get('path') == source for row in rows), 0)
        ET.SubElement(rows, 'File', path=source, type='file.verilog', enable='1')
        tree.write(stage / 'Prj1.gprj')
        hdl = [row.get('path') for row in rows if row.get('enable') == '1' and
               Path(row.get('path', '')).suffix in ('.v', '.sv')]
        command = ['iverilog', '-g2012', '-grelative-include', '-E', '-I.', '-o', '-', *hdl]
        result = subprocess.run(command, cwd=stage, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout, command

    def test_03_actual_all_three_provider_closures(self):
        selected = os.environ.get('GW138K_TASK3_W_BATCH_PARENT_STAGE')
        if not selected:
            self.skipTest('explicit immutable W parent stage required; no cache fallback')
        parent = Path(selected).resolve()
        self.assertTrue((parent / 'Prj1.gprj').is_file())
        parent_hash = sha(parent / 'Prj1.gprj')
        for provider, window, batch in ((paired.PROVIDER, False, False),
                                       (paired.PHONE_PROVIDER, True, False),
                                       (paired.BATCH_PROVIDER, True, True)):
            with self.subTest(provider=provider), tempfile.TemporaryDirectory(prefix='task3-w-batch-source-') as temp:
                stage = Path(temp) / 'stage'
                text, command = self.fixture(parent, stage, provider)
                proof = paired.selected_source_evidence(stage, text)
                self.assertEqual(proof['actual_phone_provider']['phone_batch'], batch)
                self.assertEqual(proof['selected_CNN_memory'], paired.cnn_memory_provider(provider))
                negatives = paired.source_negative_controls(stage, text)
                self.assertEqual(len(negatives), 17 if batch else 8)
                self.evidence['negative_controls'].extend(dict(provider=provider, **row) for row in negatives)
                self.evidence['configurations'].append(dict(provider=provider, phone_window=window,
                    phone_batch=batch, actual_preprocessed_sha256=hashlib.sha256(text.encode()).hexdigest(),
                    normalized_source_proof=proof, command=command,
                    fixture_current_sources_sha256={relative: sha(stage / relative) for relative in
                        (paired.BATCH_PROVIDER, paired.BOARD,
                         'rtl/workstation/workstation_task3_w_bus_endpoint.sv',
                         'rtl/workstation/workstation_task3_phone_batch_w.sv')}))
                tree = ET.parse(stage / 'Prj1.gprj')
                rows = tree.find('FileList')
                if batch:
                    owner = [row for row in rows if row.get('path') == 'rtl/workstation/workstation_task3_phone_batch_w.sv'][0]
                    owner.set('enable', '0')
                    tree.write(stage / 'Prj1.gprj')
                    with self.assertRaises(ValueError):
                        paired.selected_source_evidence(stage, text)
                    owner.set('enable', '1')
                ET.SubElement(rows, 'File', path=paired.PHONE_PROVIDER if batch else paired.BATCH_PROVIDER,
                              type='file.verilog', enable='1')
                tree.write(stage / 'Prj1.gprj')
                with self.assertRaises(ValueError):
                    paired.selected_source_evidence(stage, text)
        self.assertEqual(sha(parent / 'Prj1.gprj'), parent_hash)
        self.evidence['parent_project_unchanged'] = True
        self.evidence['parent_project_sha256'] = parent_hash


if __name__ == '__main__':
    unittest.main()
