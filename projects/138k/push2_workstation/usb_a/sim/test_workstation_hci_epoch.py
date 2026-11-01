#!/usr/bin/env python3
"""Explicit W epoch selection and exact preservation of legacy CDC budgets."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.workstation_classic_runtime import cdc_bundle
from tools.workstation_cpu_business import selection
from tools.workstation_hci_epoch import (POLICY, CDC_POLICY, PROVIDER, RAW_SOURCE,
                                         REGISTERED_SOURCE, cdc_selection)


class RegisteredEpochPolicy(unittest.TestCase):
    def test_default_bundle_is_unchanged_and_not_mutated(self):
        old = cdc_bundle()
        self.assertIs(cdc_selection(old), old)
        self.assertEqual(old, cdc_bundle(registered_controller_epoch=False))
        self.assertNotIn('controller_epoch_source', old)

    def test_new_policy_only_rebinds_two_existing_lines(self):
        old = cdc_bundle()
        actual = cdc_bundle(registered_controller_epoch=True)
        expected = dict(old, policy=CDC_POLICY, controller_epoch_source=POLICY,
                        sdc=old['sdc'].replace(RAW_SOURCE, REGISTERED_SOURCE))
        self.assertEqual(actual, expected)
        self.assertEqual(actual['held_payload_max_delay_ns'], 10)
        self.assertEqual(actual['sdc'].count(REGISTERED_SOURCE), 2)
        self.assertEqual(cdc_bundle(), old)

    def test_selector_or_budget_drift_is_rejected(self):
        old = cdc_bundle()
        for label, changed in (
            ('budget', old['sdc'].replace('set_max_delay 10.000', 'set_max_delay 20.000')),
            ('destination', old['sdc'].replace('session/epoch_o*', 'session/live_o*')),
            ('expanded_source', old['sdc'].replace(RAW_SOURCE, RAW_SOURCE+' other_source*')),
            ('missing', '\n'.join(x for x in old['sdc'].splitlines() if RAW_SOURCE not in x)),
            ('duplicate', old['sdc']+next(x for x in old['sdc'].splitlines() if RAW_SOURCE in x)+'\n'),
            ('already_selected', old['sdc']+REGISTERED_SOURCE+'\n'),
        ):
            with self.subTest(label=label), self.assertRaises(ValueError):
                cdc_selection(dict(old, sdc=changed), True)
        for changed in (dict(old, policy=CDC_POLICY), dict(old, held_payload_max_delay_ns=20)):
            with self.assertRaises(ValueError):
                cdc_selection(changed, True)

    def test_selection_requires_actual_boolean(self):
        for value in (None, 0, 1, 'true', [], {}, 1.0):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    cdc_bundle(registered_controller_epoch=value)
                with self.assertRaises(ValueError):
                    selection(True, audio_only=True, registered_controller_epoch=value)

    def test_provider_is_opt_in_to_shared_audio_worker(self):
        for shared, audio in ((False, False), (True, False), (False, True)):
            with self.subTest(shared=shared, audio=audio), self.assertRaises(ValueError):
                selection(shared, audio_only=audio, registered_controller_epoch=True)
        default = selection(True, audio_only=True)
        self.assertEqual(default, selection(True, audio_only=True, registered_controller_epoch=False))
        self.assertNotEqual(default[0]['rtl/bluetooth/workstation_bluetooth.sv'], PROVIDER)
        copies, sources, dependencies = selection(True, audio_only=True, registered_controller_epoch=True)
        self.assertEqual(copies, {'rtl/bluetooth/workstation_bluetooth.sv': PROVIDER})
        self.assertEqual(sources, default[1])
        self.assertIn('rtl/bluetooth/hci_owner/workstation_hci_audio_provider.sv', dependencies)
        self.assertIn(PROVIDER, dependencies)
        self.assertIn('tools/workstation_hci_epoch.py', dependencies)

    def test_selected_epoch_auditor_is_hashed_before_prepared_boundary(self):
        from tools import workstation_demo_audit as audit
        class PreparedBoundaryReached(Exception):
            pass
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in audit.AUDIT_SOURCES:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('frozen auditor fixture\n')
            with patch.object(audit, 'verify_prepared', side_effect=PreparedBoundaryReached):
                with self.assertRaises(PreparedBoundaryReached):
                    audit.audit(root, root / 'candidate', {})
                metadata = {'classic_runtime': {'hci_epoch_policy': POLICY}}
                with self.assertRaisesRegex(FileNotFoundError, 'workstation_hci_epoch.py'):
                    audit.audit(root, root / 'candidate', metadata)
                (root / 'tools/workstation_hci_epoch.py').write_text('selected auditor\n')
                with patch.object(audit, 'sha', wraps=audit.sha) as hashes:
                    with self.assertRaises(PreparedBoundaryReached):
                        audit.audit(root, root / 'candidate', metadata)
                    self.assertIn('workstation_hci_epoch.py', {c.args[0].name for c in hashes.call_args_list})


if __name__ == '__main__':
    unittest.main()
