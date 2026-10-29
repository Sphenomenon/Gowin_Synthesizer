#!/usr/bin/env python3
"""Explicit profile isolation and source/compiled-closure tamper rejection."""

from pathlib import Path
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_profile as profile
from tools import workstation_custom_board as integration
from tools.workstation_baselines import load_baseline


class ProfileSources(unittest.TestCase):
    def test_real_lock_and_honest_feature_matrix(self):
        selected = profile.load(ROOT, profile.NAME)
        features = {item['name']: item for item in selected['features']}
        self.assertEqual(selected['target_sample_rates_hz'], [48000, 44100])
        self.assertEqual(selected['configuration']['implemented_sample_rates_hz'], [48000])
        self.assertEqual(features['audio_44k1_switch']['source_state'], 'not_implemented')
        self.assertIn('D5 write-window adapter remains isolated', features['hdmi_ddr']['selected_behavior'])
        self.assertTrue(all(item['hardware_acceptance'] == 'unverified_for_this_profile'
                            for item in selected['features']))
        self.assertEqual(set(selected['references']), {'A2', 'D5', 'C1'})

    def test_configuration_is_explicit_and_other_profiles_are_isolated(self):
        for options in (dict(name='accepted_full83'), dict(name=profile.NAME, allow_high_speed=False),
                        dict(name=profile.NAME, hdmi_mode='720p60')):
            with self.subTest(options=options), self.assertRaises(ValueError):
                profile.load(ROOT, **options)
        for option in ('--current-workstation', '--cnn-timing85', '--resource-rework',
                       '--prepare-pinout', '--prepare-usb2-soc'):
            command = [sys.executable, str(ROOT / 'build.py'), '--workstation-profile', profile.NAME, option]
            if option == '--prepare-pinout':
                command.append('custom-138k')
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('--workstation-profile requires --prepare-custom-board', result.stderr)

    def test_changed_selected_source_is_rejected_before_preparation(self):
        selected = next(iter(profile.load(ROOT, profile.NAME)['source_sha256']))
        repository = ROOT.parents[3]
        original = profile.sha
        with patch.object(profile, 'sha', side_effect=lambda path: '0' * 64
                          if Path(path) == repository / selected else original(path)):
            with self.assertRaisesRegex(ValueError, 'profile source drift'):
                profile.load(ROOT, profile.NAME)

    def test_added_source_in_a_globbed_directory_is_rejected(self):
        config = json.loads((ROOT / profile.CONFIG).read_text())
        config['source_sets'][next(iter(config['source_sets']))] = []
        original = Path.read_text
        with patch.object(Path, 'read_text', lambda source, *args, **kwargs:
                          json.dumps(config) if source == ROOT / profile.CONFIG else original(source, *args, **kwargs)):
            with self.assertRaisesRegex(ValueError, 'source inventory drift'):
                profile.load(ROOT, profile.NAME)

    def test_missing_maintained_ae350_source_cannot_fall_back_to_locked_rom(self):
        original = Path.is_file
        missing = ROOT / 'firmware/ae350/ui_main.c'
        with tempfile.TemporaryDirectory(prefix='profile-missing-ae350-') as directory, \
             patch.object(Path, 'is_file', lambda source: False if source == missing else original(source)), \
             patch.object(integration, 'prepare_pinout') as prepare_pinout:
            output = Path(directory) / 'candidate'
            with self.assertRaisesRegex(ValueError, 'missing.*ui_main.c'):
                integration.prepare(ROOT, Path(directory) / 'netlists', output, workstation_profile=profile.NAME)
            prepare_pinout.assert_not_called()
            self.assertFalse(output.exists())


@unittest.skipUnless(os.environ.get('GW138K_PROFILE_PREPARED'),
                     'Set GW138K_PROFILE_PREPARED to test an actual prepared native candidate')
class PreparedClosure(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='workstation-profile-check-')
        self.addCleanup(temporary.cleanup)
        self.output = Path(temporary.name).resolve() / 'candidate'
        shutil.copytree(Path(os.environ['GW138K_PROFILE_PREPARED']), self.output)
        self.stage = self.output / 'workstation/Prj1'

    def test_actual_prepare_records_every_input_and_reference_scope(self):
        artifact = profile.verify(ROOT, self.output)
        self.assertEqual(artifact['validation_stage'], 'prepare_only')
        self.assertFalse(artifact['hardware_tested'])
        self.assertFalse(artifact['deployment_allowed'])
        self.assertGreater(len(artifact['enabled_inputs']), 200)
        self.assertTrue(all(row['sha256'] for row in artifact['enabled_inputs'].values()))
        a2 = artifact['reference_reuse']['A2']['files']
        firmware = a2['projects/138k/push2_workstation/usb_a/firmware.c']
        self.assertEqual(firmware['selection'], 'usb_firmware_build_input')
        self.assertTrue(firmware['same_bytes_as_reference'])
        self.assertEqual(artifact['revision'], 2)
        self.assertEqual(artifact['configuration']['ae350_firmware_policy'], profile.AE350_POLICY)
        ae350 = artifact['ae350_firmware']
        self.assertTrue(ae350['project_rom_installed'])
        self.assertEqual(profile.sha(self.stage / 'firmware/boot.mem'), ae350['build']['rom_sha256'])
        self.assertGreaterEqual(ae350['build']['capacity']['stack_capacity_bytes'], 4096)
        self.assertTrue(ae350['build']['tool_versions'])
        self.assertEqual(artifact['generated_data_inputs']['firmware/boot.mem']['origin'],
                         'maintained_ae350_firmware')

    def test_changed_compiled_input_and_uncompiled_dependency_are_rejected(self):
        metadata = json.loads((self.output / 'integration_inputs.json').read_text())
        for relative in (metadata['enabled_inputs'][0], 'usb2_cpu.hex'):
            source = self.stage / relative
            original = source.read_bytes()
            source.write_bytes(original + b'\n')
            with self.subTest(relative=relative), self.assertRaisesRegex(ValueError, 'drift|closure changed'):
                profile.verify(ROOT, self.output)
            source.write_bytes(original)

    def test_new_compilation_entry_and_unlisted_files_are_rejected(self):
        project = self.stage / 'Prj1.gprj'
        original = project.read_bytes()
        tree = ElementTree.parse(project)
        ElementTree.SubElement(tree.find('FileList'), 'File', path='unexpected.sv', type='file.verilog', enable='1')
        tree.write(project, encoding='UTF-8', xml_declaration=True)
        with self.assertRaisesRegex(ValueError, 'compilation selection changed'):
            profile.verify(ROOT, self.output)
        project.write_bytes(original)
        (self.stage / 'unexpected.mem').write_text('0000\n')
        with self.assertRaisesRegex(ValueError, 'staged file inventory changed'):
            profile.verify(ROOT, self.output)

    def test_metadata_and_feature_claim_changes_are_rejected(self):
        manifest = self.output / 'integration_inputs.json'
        original = manifest.read_text()
        for key, value in (('hardware_tested', True), ('deployment_allowed', True), ('release_ready', True)):
            metadata = json.loads(original)
            metadata[key] = value
            manifest.write_text(json.dumps(metadata))
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'manifest changed'):
                profile.verify(ROOT, self.output)
        manifest.write_text(original)
        artifact = self.output / profile.ARTIFACT
        data = json.loads(artifact.read_text())
        data['features'][0]['hardware_acceptance'] = 'accepted'
        artifact.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'artifact changed'):
            profile.verify(ROOT, self.output)

    def test_toolchain_and_generated_rom_change_candidate_identity(self):
        metadata = json.loads((self.output / 'integration_inputs.json').read_text())
        config = profile.load(ROOT, profile.NAME)
        initial = profile._artifact(ROOT, self.output, metadata, config)
        for key in ('compiler_version', 'rom_sha256'):
            changed = copy.deepcopy(metadata)
            changed['firmware'][key] = 'different compiler or generated ROM'
            other = profile._artifact(ROOT, self.output, changed, config)
            with self.subTest(key=key):
                self.assertNotEqual(initial['candidate_identity'], other['candidate_identity'])

    def test_ae350_evidence_and_installed_rom_are_bound_to_the_candidate(self):
        for source in (self.output / profile.AE350_DIRECTORY / 'firmware.elf',
                       self.stage / 'firmware/boot.mem'):
            original = source.read_bytes()
            source.write_bytes(original + b'\n')
            with self.subTest(path=source), self.assertRaisesRegex(ValueError, 'AE350.*changed'):
                profile.verify(ROOT, self.output)
            source.write_bytes(original)


@unittest.skipUnless(os.environ.get('GW138K_PROFILE_LEGACY_PREPARED'),
                     'Set GW138K_PROFILE_LEGACY_PREPARED to verify unprofiled native preparation')
class LegacyPolicy(unittest.TestCase):
    def test_default_native_profile_keeps_locked_ae350_rom(self):
        output = Path(os.environ['GW138K_PROFILE_LEGACY_PREPARED']).resolve()
        metadata = json.loads((output / 'integration_inputs.json').read_text())
        self.assertNotIn('workstation_profile', metadata)
        self.assertNotIn('ae350_firmware', metadata)
        self.assertFalse((output / profile.AE350_DIRECTORY).exists())
        baseline = load_baseline(ROOT, 'resource_rework_route0')
        self.assertEqual((output / 'workstation/Prj1/firmware/boot.mem').read_bytes(),
                         baseline.read_bytes('firmware/boot.mem'))


if __name__ == '__main__':
    unittest.main()
