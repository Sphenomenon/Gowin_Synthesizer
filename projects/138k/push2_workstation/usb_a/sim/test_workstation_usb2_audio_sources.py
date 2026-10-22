#!/usr/bin/env python3
"""Explicit audio closure, canonical resource dependencies and fail-closed staging."""

from pathlib import Path
import copy
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_usb2_audio as audio_sources
from tools import workstation_usb2_soc as preparation
from tools.workstation_baselines import Baseline
from tools.workstation_composition import SOURCES as COMPOSITION_SOURCES
from tools.stage_usb_firmware import sha


class AudioSources(unittest.TestCase):
    def test_audio_lint_has_no_missing_dependencies_or_hidden_new_warnings(self):
        self.assertIsNotNone(shutil.which('verilator'), 'Verilator is required for native audio lint')
        with tempfile.TemporaryDirectory(prefix='workstation-usb2-audio-lint-') as directory:
            stage, metadata = preparation.prepare(ROOT, Path(directory) / 'stage', firmware_profile='workstation',
                                                  component='workstation-audio')
            command = ['verilator', '--lint-only', '--timing', '-Wall', '-Wno-fatal',
                       '--top-module', metadata['top_module'], '-I' + str(stage),
                       *(str(stage / relative) for relative in metadata['source_paths'])]
            result = subprocess.run(command, cwd=stage, text=True, capture_output=True, timeout=180)
            self.assertEqual(result.returncode, 0, result.stdout[-3000:] + result.stderr[-3000:])
            warnings = re.findall(r'%Warning-(\w+): ([^\n]+)', result.stdout + result.stderr)
            wrapper = [(kind, detail) for kind, detail in warnings
                       if '/rtl/workstation/workstation_usb2_audio.sv:' in detail]
            self.assertEqual([kind for kind, _ in wrapper], ['SYNCASYNCNET'])
            self.assertIn('memory_reset_n', wrapper[0][1])
            for relative in ('workstation_usb2_input.sv', 'workstation_usb2_service_adapter.sv'):
                self.assertFalse(any('/' + relative + ':' in detail for _, detail in warnings), relative)

    def test_explicit_audio_profile_preserves_firmware_and_clocks(self):
        with tempfile.TemporaryDirectory(prefix='workstation-usb2-audio-closure-') as directory:
            stage, metadata = preparation.prepare(ROOT, Path(directory) / 'audio', firmware_profile='workstation',
                                                  component='workstation-audio')
            _, default = preparation.prepare(ROOT, Path(directory) / 'soc', firmware_profile='workstation')
            self.assertEqual(metadata['firmware']['rom_sha256'], default['firmware']['rom_sha256'])
            self.assertEqual(metadata['identity'], 'custom138k-usb2-audio-component-v1')
            self.assertEqual(metadata['top_module'], 'workstation_usb2_audio')
            self.assertEqual(metadata['source_policy'], 'explicit_native_audio_and_locked_resource_dependencies')
            self.assertEqual(len(metadata['source_paths']), 66)
            self.assertEqual(len(set(metadata['source_paths'])), 66)
            self.assertTrue(metadata['source_paths'][0].endswith('/audio_math_pkg.sv'))
            self.assertEqual(metadata['clocks_hz'], dict(cpu=48000000, reference=50000000, ulpi=60000000,
                                                        audio=76800000, memory=100000000))
            self.assertEqual((stage / 'usb2_soc.sdc').read_text().count('create_clock'), 5)
            self.assertTrue(metadata['audio_path_integrated'])
            self.assertTrue(metadata['input_owner_integrated'])
            for flag in ('workstation_integrated', 'place_route_allowed', 'hardware_tested',
                         'deployment_allowed', 'release_ready'):
                self.assertFalse(metadata[flag], flag)
            provenance = metadata['input_owner_provenance']
            self.assertEqual(len(provenance['audio_sources']), 28)
            self.assertEqual(provenance['baseline']['name'], 'resource_rework_route0')
            for relative, digest in metadata['staged_input_sha256'].items():
                self.assertEqual(sha(stage / relative), digest, relative)
            for relative in audio_sources.NATIVE_AUDIO_DATA:
                self.assertNotIn(relative, metadata['source_paths'])
                self.assertEqual(sha(stage / relative), sha(ROOT / relative))
            self.assertEqual(json.loads((stage / 'component_inputs.json').read_text()), metadata)
            self.assertEqual(default['clocks_hz'], dict(cpu=48000000, reference=50000000, ulpi=60000000))
            self.assertEqual(len(default['source_paths']), 14)

    def test_selected_dsp_inputs_match_actual_resource_prepare(self):
        result = subprocess.run([sys.executable, str(ROOT / 'build.py'), '--resource-rework', '--resource-timing',
                                 '--prepare-only'], cwd=ROOT, text=True, capture_output=True, timeout=180)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        outputs = [Path(line) for line in result.stdout.splitlines() if line.startswith(str(ROOT / 'results'))]
        self.assertEqual(len(outputs), 1, result.stdout)
        reference = outputs[0] / 'Prj1'
        bundle = audio_sources.audio_bundle(ROOT)
        for destination, record in bundle['provenance']['audio_sources'].items():
            self.assertEqual(bundle['payloads'][destination], (reference / record['target']).read_bytes(), destination)
        overlays = {
            'rtl/audio/audio_capture_fifo.sv': 'legacy/rtl/audio/audio_capture_fifo.sv',
            'rtl/input/score_led_player.sv': 'legacy/rtl/input/score_led_player.sv',
            'rtl/audio/stereo_effects.sv': 'legacy/rtl/audio/stereo_effects.sv',
            'rtl/resource_timing/delay_ddr_dma.sv': 'rtl/audio/delay_ddr/delay_ddr_dma.sv',
        }
        for relative in audio_sources.NATIVE_AUDIO_SOURCES[1:]:
            destination = COMPOSITION_SOURCES.get(relative, overlays.get(relative, relative))
            self.assertEqual((ROOT / relative).read_bytes(), (reference / destination).read_bytes(), relative)
        for relative in audio_sources.NATIVE_AUDIO_DATA:
            destination = 'src/memory/ddr_address_map.vh' if relative == 'rtl/ddr_address_map.vh' else relative
            self.assertEqual((ROOT / relative).read_bytes(), (reference / destination).read_bytes(), relative)
        print('PASS canonical resource audio dependencies: ' + str(reference), flush=True)

    def test_missing_locked_dsp_or_rom_never_falls_back(self):
        original = Baseline.read_bytes
        for missing in ('legacy/rtl/audio/unified_oscillator_engine.sv', 'sim/data/audio_chain/pitch_bend_q20.mem'):
            def checked_read(baseline, relative):
                if relative == missing:
                    raise FileNotFoundError('missing selected audio dependency: ' + relative)
                return original(baseline, relative)

            with self.subTest(missing=missing), tempfile.TemporaryDirectory(prefix='workstation-usb2-audio-missing-') as directory:
                output = Path(directory) / 'stage'
                with patch.object(Baseline, 'read_bytes', checked_read):
                    with self.assertRaisesRegex(FileNotFoundError, 'missing selected audio dependency'):
                        preparation.prepare(ROOT, output, firmware_profile='workstation', component='workstation-audio')
                self.assertFalse(output.exists())

    def test_audio_bundle_drift_never_publishes_manifest(self):
        first = audio_sources.audio_bundle(ROOT)
        changed = copy.deepcopy(first)
        changed['payloads']['sim/data/audio_chain/pitch_bend_q20.mem'] += b'\n'
        with tempfile.TemporaryDirectory(prefix='workstation-usb2-audio-bundle-drift-') as directory:
            output = Path(directory) / 'stage'
            with patch.object(audio_sources, 'audio_bundle', side_effect=(first, changed)):
                with self.assertRaisesRegex(ValueError, 'sources changed during preparation'):
                    preparation.prepare(ROOT, output, firmware_profile='workstation', component='workstation-audio')
            self.assertFalse((output / 'component_inputs.json').exists())

    def test_staged_dsp_header_and_rom_drift_are_rejected(self):
        for relative in ('rtl/workstation/workstation_usb2_audio.sv', 'rtl/ddr_address_map.vh',
                         'support/audio/legacy/rtl/audio/unified_oscillator_engine.sv',
                         'sim/data/audio_chain/pitch_bend_q20.mem'):
            with self.subTest(source=relative), tempfile.TemporaryDirectory(prefix='workstation-usb2-audio-staged-drift-') as directory:
                output = Path(directory) / 'stage'
                compile_firmware = preparation.stage_usb2_cpu_firmware

                def compile_and_change(*arguments, **keywords):
                    result = compile_firmware(*arguments, **keywords)
                    source = output / relative
                    source.write_bytes(source.read_bytes() + b'\n')
                    return result

                with patch.object(preparation, 'stage_usb2_cpu_firmware', side_effect=compile_and_change):
                    with self.assertRaisesRegex(ValueError, 'staged source identity changed'):
                        preparation.prepare(ROOT, output, firmware_profile='workstation', component='workstation-audio')
                self.assertFalse((output / 'component_inputs.json').exists())

    def test_audio_requires_explicit_workstation_firmware_and_rejects_profile_mix(self):
        with tempfile.TemporaryDirectory(prefix='workstation-usb2-audio-policy-') as directory:
            output = Path(directory) / 'stage'
            with self.assertRaisesRegex(ValueError, 'requires explicit workstation firmware'):
                preparation.prepare(ROOT, output, component='workstation-audio')
            self.assertFalse(output.exists())
            result = subprocess.run([sys.executable, str(ROOT / 'build.py'), '--prepare-usb2-soc',
                                     '--usb2-component', 'workstation-audio', '--usb2-soc-output', str(output),
                                     '--usb2-firmware-profile', 'workstation', '--current-workstation'],
                                    text=True, capture_output=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
