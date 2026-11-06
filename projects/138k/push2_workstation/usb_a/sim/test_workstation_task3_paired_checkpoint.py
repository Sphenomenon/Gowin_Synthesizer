#!/usr/bin/env python3
"""Rebuild both current roles while preserving immutable rollback candidates."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import workstation_profile as profiles
from tools import workstation_task3_paired_audit as paired

NAMES = {'M':profiles.TASK3_M_CHECKPOINT_NAME,'W':profiles.TASK3_W_CHECKPOINT_NAME}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class CurrentSources(unittest.TestCase):
    def test_current_source_locks_and_parent_runtime_contracts(self):
        for role,name in NAMES.items():
            with self.subTest(role=role):
                selected = profiles.load(ROOT,name)
                reference = selected['checkpoint_parent']
                parent_path = ROOT.parents[3]/reference['configuration']
                parent = json.loads(parent_path.read_text())
                self.assertEqual(sha(parent_path),reference['configuration_sha256'])
                self.assertEqual(parent['name'],reference['profile'])
                expected=deepcopy(parent['configuration'])
                if role=='M' and name.endswith('-v5'):
                    from tools.workstation_task3_m_paired_profile import TERMINAL_POLICY
                    expected['m_score_terminal_policy']=TERMINAL_POLICY
                if role=='M' and name.endswith('-v7'):
                    from tools.workstation_task3_identity_compare import POLICY
                    expected['m_identity_compare_policy']=POLICY
                if role=='W' and name.endswith('-v8'):
                    expected['usb2_cpu_ram_bytes']=49152
                if role=='W' and name.endswith('-v12'):
                    from tools.workstation_task3_cnn_reset import POLICY
                    expected['cnn_reset_policy']=POLICY
                if role=='W' and name.endswith('-v14'):
                    from tools.workstation_task3_cnn_ready_sdc import POLICY
                    expected['cnn_ready_sdc_policy']=POLICY
                if role=='M' and name.endswith('-v15'):
                    from tools.workstation_task3_phone_identity_compare import POLICY
                    expected['m_phone_identity_compare_policy']=POLICY
                if role=='M' and name.endswith('-v17'):
                    from tools.workstation_task3_m_phone_lease_source import KEY,POLICY
                    expected[KEY]=POLICY
                if role=='M' and name.endswith('-v19'):
                    from tools.workstation_task3_tf_tail_reset import KEY,POLICY
                    expected[KEY]=POLICY
                self.assertEqual(selected['configuration'],expected)
                self.assertFalse(selected['configuration']['interboard_business_default_enabled'])
                self.assertTrue(selected['configuration']['interboard_physical_acceptance_required'])
                self.assertEqual(profiles.specification(name)['provider'],
                                 profiles.specification(parent['name'])['provider'])
                prefix = ROOT.relative_to(ROOT.parents[3]).as_posix()+'/'
                for source in paired.AUDIT_SOURCES:
                    self.assertEqual(selected['source_sha256'][prefix+source],sha(ROOT/source))


class PreparedPair(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.outputs = {}
        cls.parents = {}
        for role in NAMES:
            current = os.environ.get('GW138K_TASK3_CHECKPOINT_'+role)
            parent = os.environ.get('GW138K_TASK3_CHECKPOINT_PARENT_'+role)
            if not current or not parent:
                raise unittest.SkipTest('explicit current and immutable parent candidates required')
            cls.outputs[role] = Path(current)
            cls.parents[role] = Path(parent)
        cls.before = {}
        for output in (*cls.outputs.values(),*cls.parents.values()):
            for name in ('integration_inputs.json','workstation_profile.json'):
                path = output/name
                cls.before[str(path)] = sha(path)

    @classmethod
    def tearDownClass(cls):
        assert cls.before == {p:sha(p) for p in cls.before}

    def test_both_complete_current_preparations_and_frozen_parents_verify(self):
        for role,output in self.outputs.items():
            with self.subTest(role=role):
                artifact = profiles.verify(ROOT,output)
                metadata = json.loads((output/'integration_inputs.json').read_text())
                actual,_,_,_ = paired.verify_prepared(output,metadata)
                self.assertEqual(actual,role)
                self.assertEqual(artifact['profile'],NAMES[role])
                parent = self.parents[role]
                old_metadata = json.loads((parent/'integration_inputs.json').read_text())
                old_role,old_artifact,_,_ = paired.verify_prepared(parent,old_metadata)
                self.assertEqual(old_role,role)
                self.assertNotEqual(artifact['candidate_identity'],old_artifact['candidate_identity'])

    def test_prepared_configuration_and_gate_status_do_not_inherit_acceptance(self):
        for role,output in self.outputs.items():
            with self.subTest(role=role):
                metadata = json.loads((output/'integration_inputs.json').read_text())
                artifact = json.loads((output/'workstation_profile.json').read_text())
                for flag in ('hardware_tested','deployment_allowed','release_ready'):
                    self.assertIs(metadata[flag],False)
                self.assertIsNone(metadata['bitstream_sha256'])
                self.assertEqual(metadata['validation_stage'],'integration_prepare_only')
                self.assertFalse((output/'workstation/Prj1/impl/gwsynthesis/custom_138k_integration.vg').exists())
                config = artifact['configuration']
                self.assertEqual(config['interboard_media_policy'],
                    'task3_pcm_block6_credit8_phone_window5_atomic_snapshot_batch_v3')
                if role == 'M':
                    self.assertEqual(config['m_endpoint_storage_policy'],'sync_score_and_final_tap_prefetch_v1')
                    storage = metadata['task3_phone_batch']['local_storage']
                    self.assertEqual(storage['score_capacity_notes'],2048)
                    self.assertEqual(storage['tap_capacity_frames'],256)
                    self.assertFalse(storage['physical_BSRAM_mapping_verified'])
                    if 'm_score_terminal_policy' in config:
                        self.assertEqual(storage['terminal_commit']['queue_slots'],1)
                        self.assertEqual(storage['terminal_commit']['extra_validation_cycles'],1)
                else:
                    self.assertEqual(metadata['firmware']['ram_bytes'],config.get('usb2_cpu_ram_bytes',65536))
                    self.assertGreater(metadata['firmware']['stack_margin_bytes'],8192)
                    self.assertTrue(metadata['classic_runtime']['phone_batch'])
                    self.assertTrue(metadata['classic_runtime']['worker_media'])
                    firmware = json.loads((output/'ae350_firmware/verification.json').read_text())
                    self.assertTrue(firmware['passed'])
                    for command in firmware['commands']:
                        if command['name'].startswith('compile-'):
                            self.assertFalse(any(arg.startswith('-DA138_BLE_RECORD_DUAL_RATE')
                                                 for arg in command['argv']))
                    gatt = (output/'workstation/Prj1/rtl/bluetooth/cpu_owner/bt_gatt.v').read_text()
                    self.assertNotIn('.DUAL_RATE_RECORDING',gatt)

    def test_metadata_tampering_cannot_borrow_another_role_or_old_identity(self):
        for role,output in self.outputs.items():
            metadata = json.loads((output/'integration_inputs.json').read_text())
            mutations = [lambda m:m.update(identity='unreviewed-identity'),
                         lambda m:m['workstation_profile'].update(candidate_identity='borrowed-old-candidate'),
                         lambda m:m['workstation_profile'].update(name=NAMES['W' if role=='M' else 'M']),
                         lambda m:m.update(hardware_tested=True)]
            for mutate in mutations:
                changed = deepcopy(metadata);mutate(changed)
                with self.subTest(role=role,changed=changed['identity']),self.assertRaises(ValueError):
                    paired.verify_prepared(output,changed)


if __name__ == '__main__':
    unittest.main()
