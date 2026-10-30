#!/usr/bin/env python3
"""R00 identity, actual source selection and checked address-map adaptation."""
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_profile as profiles
from tools import workstation_recording_policy as policy

REFERENCE = '3156993f7659709d6efe73ae0b8385a369d00997'


class RecordingProfile(unittest.TestCase):
    def test_named_profile_has_distinct_source_policy_and_honest_scope(self):
        selected = profiles.load(ROOT, policy.NAME)
        self.assertEqual(selected['revision'], 1)
        self.assertEqual(selected['configuration']['recording_policy'], policy.POLICY)
        self.assertFalse(profiles.recognition_metadata(selected)['music_analysis_enabled'])
        for name in (profiles.NAME, profiles.NO_CNN_NAME):
            self.assertFalse(profiles.specification(name).get('recording_enabled', False))
            self.assertNotEqual(profiles.specification(name)['provider'], policy.PROVIDER)
            self.assertNotIn('recording_policy', profiles.specification(name)['configuration'])
        self.assertTrue(profiles.specification(policy.NAME)['recording_enabled'])
        metadata = policy.metadata()
        self.assertTrue(metadata['production_owner8_selected'])
        for field in ('hardware_tested', 'r00_complete', 'physical_cdc_accepted',
                      'physical_resource_saving_proven', 'default_ble_backend_replaced', 'deployment_allowed'):
            self.assertIs(metadata[field], False)
        for source in (*policy.SOURCES, *policy.DEPENDENCIES, policy.PROVIDER):
            self.assertIn('projects/138k/push2_workstation/usb_a/' + source, selected['source_sha256'])

    def test_alias_revision_and_recording_policy_drift_fail_before_prepare(self):
        config = ROOT / policy.CONFIG
        original = Path.read_text
        base = json.loads(config.read_text())
        changes = [dict(base, name=profiles.NO_CNN_NAME), dict(base, revision=2)]
        changed = copy.deepcopy(base)
        del changed['configuration']['recording_policy']
        changes.append(changed)
        for changed in changes:
            with self.subTest(changed=changed['name']), patch.object(Path, 'read_text',
                    lambda path, *a, **k: json.dumps(changed) if path == config else original(path, *a, **k)), \
                    self.assertRaisesRegex(ValueError, 'identity changed|configuration mismatch'):
                profiles.load(ROOT, policy.NAME)

    def test_recording_map_preserves_existing_allocation_and_checks_parent_bytes(self):
        original, selected = policy.address_map_inputs(ROOT)
        self.assertTrue(all(policy.macros(selected)[key] == value for key, value in policy.macros(original).items()))
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            target = stage / policy.MAP_DESTINATION
            target.parent.mkdir(parents=True)
            target.write_bytes(original)
            evidence = policy.install_address_map(ROOT, stage)
            self.assertEqual(target.read_bytes(), selected)
            policy.verify_address_map(ROOT, stage, evidence)
            changed = dict(evidence, parent_sha256='0' * 64)
            with self.assertRaisesRegex(ValueError, 'provenance changed'):
                policy.verify_address_map(ROOT, stage, changed)
            target.write_bytes(original + b'\n')
            with self.assertRaisesRegex(ValueError, 'parent address-map identity changed'):
                policy.install_address_map(ROOT, stage)

    def test_changed_existing_map_allocation_is_rejected(self):
        original = Path.read_bytes
        source = ROOT / policy.MAP_SOURCE
        selected = source.read_bytes()
        key, value = next(iter(policy.macros(policy.address_map_inputs(ROOT)[0]).items()))
        changed = selected.replace(b'`define ' + key + b' ' + value,
                                   b'`define ' + key + b' 0', 1)
        if changed == selected:
            changed = re.sub(rb'(?m)^(`define\s+' + key + rb'\s+)[^\r\n]+', rb'\g<1>0', selected, count=1)
        self.assertNotEqual(changed, selected)
        with patch.object(Path, 'read_bytes', lambda path: changed if path == source else original(path)), \
                self.assertRaisesRegex(ValueError, 'existing allocation'):
            policy.address_map_inputs(ROOT)

    def test_macro_selects_real_owner8_and_does_not_leak_or_change_default_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            def preprocess(path, name, macros=()):
                output = temp / (name + '.v')
                command = ['iverilog', '-g2012', '-E', '-I', str(ROOT), '-o', str(output),
                           *['-D' + macro for macro in macros], str(path)]
                subprocess.run(command, check=True, capture_output=True, timeout=30)
                return output.read_text()
            selected = preprocess(ROOT / policy.PROVIDER, 'r00')
            legacy = preprocess(ROOT / profiles.NO_CNN_PROVIDER, 'no_cnn')
            for text in ('workstation_recording_runtime u_recording',
                         'workstation_recording_ddr_client_queues #(.RECORDING_ENABLE(1)) u_arbiter',
                         '.recording_native_accept_i(recording_native_accept)',
                         '.frame_pcm_i(physical_frame_pcm)', "20'hf8040"):
                self.assertIn(text, selected)
                self.assertNotIn(text, legacy)
            self.assertIn('workstation_bluetooth #(.EXTERNAL_SEAL_PROTOCOL(1)) u_bluetooth', selected)
            self.assertIn('workstation_bluetooth #(.EXTERNAL_SEAL_PROTOCOL(1)) u_bluetooth', legacy)
            wrapper = temp / 'leak.sv'
            wrapper.write_text('`include "' + policy.PROVIDER + '"\n`ifdef WORKSTATION_RECORDING_DDR\nLEAKED_RECORDING_MACRO\n`endif\n')
            self.assertNotIn('LEAKED_RECORDING_MACRO', preprocess(wrapper, 'leak'))
            def tokens(text):
                return re.sub(r'\s+', '', re.sub(r'//[^\n]*|/\*.*?\*/', '', text, flags=re.S))
            for index, relative in enumerate(('rtl/workstation/gw138k_push_workstation_top.v',
                                              'rtl/workstation/workstation_hdmi_display.sv')):
                previous = temp / ('previous' + str(index) + '.sv')
                reference = subprocess.check_output(['git', 'show', REFERENCE +
                    ':projects/138k/push2_workstation/usb_a/' + relative], cwd=ROOT.parents[3])
                # Keep the frozen pre-R00 reference. 66bb45d independently added
                # synchronous audio-owner reset release to the runtime USB path.
                # Apply only that checked follow-up to the expected temp copy;
                # all unrelated tokens and all four macro paths still compare.
                if relative == 'rtl/workstation/gw138k_push_workstation_top.v':
                    old = b',.CNN_FOLLOW_ENABLE(RECOGNITION_ENABLED),.STOP_CLOCK_QUEUE_FENCE(1)'
                    new = old + b',.AUDIO_OWNER_RESET_SYNC(1)'
                    self.assertEqual(reference.count(old), 1)
                    self.assertNotIn(new, reference)
                    reference = reference.replace(old, new, 1)
                previous.write_bytes(reference)
                for mode, macros in enumerate(((), ('WORKSTATION_CUSTOM_138K',),
                        ('WORKSTATION_CUSTOM_138K', 'WORKSTATION_RUNTIME_NATIVE'),
                        ('WORKSTATION_CUSTOM_138K', 'WORKSTATION_RUNTIME_NATIVE', 'WORKSTATION_NO_CNN'))):
                    self.assertEqual(tokens(preprocess(previous, f'old{index}_{mode}', macros)),
                                     tokens(preprocess(ROOT / relative, f'new{index}_{mode}', macros)))

    @unittest.skipUnless(os.environ.get('GW138K_R00_PREPARED'), 'Set GW138K_R00_PREPARED to verify a real prepare')
    def test_real_prepare_selects_one_provider_sources_map_and_opt_in_firmware(self):
        output = Path(os.environ['GW138K_R00_PREPARED'])
        artifact = profiles.verify(ROOT, output)
        self.assertEqual(artifact['profile'], policy.NAME)
        self.assertEqual(artifact['validation_stage'], 'prepare_only')
        self.assertFalse(artifact['hardware_tested'])
        self.assertFalse(artifact['deployment_allowed'])
        self.assertIn(policy.PROVIDER, artifact['enabled_inputs'])
        for name in (profiles.RUNTIME_PROVIDER, profiles.NO_CNN_PROVIDER):
            self.assertNotIn(name, artifact['enabled_inputs'])
        for source in policy.SOURCES:
            self.assertIn(source, artifact['enabled_inputs'])
        ae350 = artifact['ae350_firmware']['build']
        self.assertTrue(ae350['recording_api_enabled'])
        self.assertIn('recording_service.c', ae350['compiled_sources'])
        self.assertEqual(artifact['recording']['owner'], 8)
        self.assertFalse(artifact['recording']['r00_complete'])
        policy.verify_address_map(ROOT, output / 'workstation/Prj1', artifact['recording']['address_map'])

    @unittest.skipUnless(os.environ.get('GW138K_R00_PREPARED'), 'Set GW138K_R00_PREPARED to verify prepared tampering')
    def test_prepared_policy_map_provider_and_api_aliases_are_rejected(self):
        output = Path(os.environ['GW138K_R00_PREPARED'])
        metadata = json.loads((output / 'integration_inputs.json').read_text())
        selected = profiles.load(ROOT, policy.NAME)
        mutations = []
        changed = copy.deepcopy(metadata); changed['recording']['owner_bits'] = 3
        mutations.append((changed, 'recording selection changed'))
        changed = copy.deepcopy(metadata); changed['recording']['address_map']['selected_sha256'] = '0' * 64
        mutations.append((changed, 'address-map provenance changed'))
        changed = copy.deepcopy(metadata); changed['enabled_inputs'].append(profiles.NO_CNN_PROVIDER)
        mutations.append((changed, 'selected compilation provider changed'))
        changed = copy.deepcopy(metadata); changed['ae350_firmware']['build']['recording_api_enabled'] = False
        mutations.append((changed, 'recording API selection changed'))
        for changed, error in mutations:
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                profiles._artifact(ROOT, output, changed, selected)


if __name__ == '__main__':
    unittest.main()
