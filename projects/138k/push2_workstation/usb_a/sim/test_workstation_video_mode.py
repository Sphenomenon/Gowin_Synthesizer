#!/usr/bin/env python3
"""Native-only video selection, source drift guards and standard 720p30 timing."""

from pathlib import Path
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ElementTree


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_baselines import load_baseline
from tools.workstation_custom_clocks import clock_bundle
from tools.workstation_resource_timing import dashboard
from tools.workstation_video_mode import apply, LOCKED_INPUTS, TIMING, ADAPTED_PLL, IDENTITY_720, PROFILES_720
from tools.stage_usb_firmware import sha


class VideoMode(unittest.TestCase):
    def fixture(self, stage):
        baseline = load_baseline(ROOT, 'resource_rework_route0')
        for relative in LOCKED_INPUTS:
            destination = stage / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            data = baseline.read_bytes(relative)
            if relative == 'src/video/feedback_dashboard.v':
                data = dashboard(data.decode()).encode()
            destination.write_bytes(data)
            self.assertEqual(sha(destination), LOCKED_INPUTS[relative])
        files = ElementTree.Element('FileList')
        ElementTree.SubElement(files, 'File', path='vendor/sipeed_dvi/video_pll_1080p_gw5a.v', enable='1')
        return files

    def test_default_does_not_change_any_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            files = self.fixture(stage)
            before = {path: path.read_bytes() for path in stage.rglob('*') if path.is_file()}
            result = apply(ROOT, stage, files, '1080p60')
            self.assertEqual(result['adapted'], {})
            self.assertEqual(before, {path: path.read_bytes() for path in stage.rglob('*') if path.is_file()})

    def test_720p_changes_scanout_renderer_and_real_pll_only_when_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            files = self.fixture(stage)
            result = apply(ROOT, stage, files, '720p30')
            self.assertEqual(result['width'] * result['height'] * 2 * result['refresh_hz'], 55296000)
            self.assertEqual(result['pixel_hz'], result['h_total'] * result['v_total'] * result['refresh_hz'])
            self.assertEqual(result['serial_hz'], result['pixel_hz'] * 5)
            self.assertEqual(sha(stage / 'vendor/sipeed_dvi/video_pll_1080p_gw5a.v'),
                             LOCKED_INPUTS['vendor/sipeed_dvi/video_pll_1080p_gw5a.v'])
            self.assertIn('.OUTPUT_DIV0(2)', (stage / ADAPTED_PLL).read_text())
            self.assertIn('1280 X 720 / 30 HZ', (stage / 'src/video/feedback_dashboard.v').read_text())
            selected = [entry.get('path') for entry in files if entry.get('enable') == '1']
            self.assertEqual(set(selected), {ADAPTED_PLL, TIMING})

    def test_rejects_locked_input_drift_before_writing(self):
        for relative in LOCKED_INPUTS:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory:
                stage = Path(directory)
                files = self.fixture(stage)
                with (stage / relative).open('a') as stream:
                    stream.write('\n')
                with self.assertRaisesRegex(ValueError, 'locked input drift'):
                    apply(ROOT, stage, files, '720p30')
                self.assertFalse((stage / ADAPTED_PLL).exists())

    def test_clock_modes_keep_every_non_video_clock_unchanged(self):
        original, reduced = clock_bundle(ROOT), clock_bundle(ROOT, '720p30')
        self.assertEqual(original['plan']['primary'], reduced['plan']['primary'])
        original_clocks = {entry['name']: entry for entry in original['plan']['generated']}
        reduced_clocks = {entry['name']: entry for entry in reduced['plan']['generated']}
        for name in original_clocks.keys() - {'video_serial742', 'video_pixel148'}:
            self.assertEqual(original_clocks[name], reduced_clocks[name])
        self.assertEqual(reduced_clocks['video_serial371']['frequency_hz'], 371250000)
        self.assertEqual(reduced_clocks['video_pixel74']['frequency_hz'], 74250000)
        self.assertEqual(reduced_clocks['video_pixel74']['edges'], [1, 7, 11])
        self.assertNotIn('set_false_path', reduced['sdc'])
        self.assertNotIn('set_clock_groups', reduced['sdc'])

    def test_rejects_unknown_modes_and_non_native_entry(self):
        with self.assertRaises(ValueError):
            clock_bundle(ROOT, '720p24')
        with self.assertRaises(ValueError):
            apply(ROOT, ROOT, ElementTree.Element('FileList'), '720p24')
        result = subprocess.run([sys.executable, str(ROOT / 'build.py'), '--current-workstation',
                                 '--prepare-only', '--hdmi-mode', '720p30'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--hdmi-mode requires --prepare-custom-board', result.stderr)

    def test_720p60_keeps_720p30_clocks_and_complete_canvas(self):
        self.assertEqual(clock_bundle(ROOT, '720p30'), clock_bundle(ROOT, '720p60'))
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            files = self.fixture(stage)
            result = apply(ROOT, stage, files, '720p60')
            profile = PROFILES_720['720p60']
            self.assertNotEqual(profile['identity'], IDENTITY_720)
            self.assertEqual(result['pixel_hz'], result['h_total'] * result['v_total'] * 60)
            self.assertEqual(result['h_total'], 1650)
            self.assertEqual(result['width'] * result['height'] * 2 * result['refresh_hz'], 110592000)
            self.assertEqual(result['canvas_mapping'], 'floor(output_coordinate*3/2)')
            self.assertIn('1280 X 720 / 60 HZ', (stage / 'src/video/feedback_dashboard.v').read_text())
            self.assertIn('workstation_video_timing_720p60 u_timing',
                          (stage / 'src/video/hdmi_display.v').read_text())
            self.assertEqual({entry.get('path') for entry in files if entry.get('enable') == '1'},
                             {profile['pll'], profile['timing']})
            self.assertEqual(sha(stage / 'vendor/sipeed_dvi/video_pll_1080p_gw5a.v'),
                             LOCKED_INPUTS['vendor/sipeed_dvi/video_pll_1080p_gw5a.v'])

    def test_actual_720p60_raster(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            executable = stage / '720p60.vvp'
            compiled = subprocess.run(['iverilog', '-g2012', '-s', 'tb_video_720p30',
                                       '-Ptb_video_720p30.REFRESH_HZ=60', '-o', str(executable),
                                       str(ROOT / PROFILES_720['720p60']['timing']),
                                       str(ROOT / 'sim/display/tb_video_720p30.sv')],
                                      capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run(['vvp', str(executable)], capture_output=True, text=True, timeout=180)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS 720p60: 1650x750', result.stdout)
            print(result.stdout.strip(), flush=True)

    def test_native_720p_physical_adapter_keeps_original_checks(self):
        from tools import workstation_video_physical as checker
        for mode in PROFILES_720:
            for kind, (filename, expected) in checker.ORIGINALS.items():
                with self.subTest(mode=mode, kind=kind):
                    original = ROOT / 'reports/workstation_physical_20261025' / filename
                    self.assertEqual(sha(original), expected)
                    text = checker.adapt(kind, original.read_text(), mode)
                    compile(text, filename + ':' + mode, 'exec')
                    if kind == 'cdc':
                        self.assertEqual(text, original.read_text())
                    else:
                        with self.assertRaisesRegex(ValueError, 'anchor drift'):
                            checker.adapt(kind, 'wrong original checker', mode)
                    self.assertEqual(sha(original), expected)
        with self.assertRaises(ValueError):
            checker.adapt('timing', '', '1080p60')

    def test_actual_720p30_raster_and_scaled_renderer(self):
        baseline = load_baseline(ROOT, 'resource_rework_route0')
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            files = self.fixture(stage)
            apply(ROOT, stage, files, '720p30')
            names = ('feedback_capture.v', 'feedback_wave_align.v', 'video_font_5x7.v')
            sources = [stage / 'src/video/feedback_renderer.v', stage / 'src/video/feedback_dashboard.v']
            for name in names:
                source = stage / 'src/video' / name
                source.write_bytes(baseline.read_bytes('src/video/' + name))
                sources.append(source)
            testbench = ROOT / 'sim/display/tb_video_720p30.sv'
            for top, inputs in (
                    ('tb_video_720p30', [stage / TIMING]),
                    ('tb_video_720p_renderer', sources)):
                with self.subTest(top=top):
                    executable = stage / (top + '.vvp')
                    compiled = subprocess.run(['iverilog', '-g2012', '-s', top, '-o', str(executable),
                                               *map(str, inputs), str(testbench)], capture_output=True, text=True)
                    self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
                    command = ['vvp', str(executable)]
                    if top == 'tb_video_720p_renderer' and os.environ.get('GW138K_VIDEO_FRAME_DUMP'):
                        command.append('+FRAME_DUMP=' + os.environ['GW138K_VIDEO_FRAME_DUMP'])
                    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('PASS ', result.stdout)
                    print(result.stdout.strip(), flush=True)

    def test_physical_adapters_keep_original_checkers_and_reject_drift(self):
        source = ROOT / 'reports/hdmi_720p30_20261026/check_physical.py'
        specification = importlib.util.spec_from_file_location('video_physical_checker', source)
        checker = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(checker)
        for kind, (filename, expected) in checker.ORIGINALS.items():
            with self.subTest(kind=kind):
                original = ROOT / 'reports/workstation_physical_20261025' / filename
                self.assertEqual(sha(original), expected)
                text = checker.adapt(kind, original.read_text())
                compile(text, filename + ':720p30', 'exec')
                if kind == 'cdc':
                    self.assertEqual(text, original.read_text())
                else:
                    self.assertNotEqual(text, original.read_text())
                    with self.assertRaisesRegex(ValueError, 'anchor drift'):
                        checker.adapt(kind, 'wrong original checker')
                self.assertEqual(sha(original), expected)
                if kind == 'timing':
                    namespace = dict(__file__=str(original), __name__='video_timing_test')
                    exec(compile(text, filename + ':720p30', 'exec'), namespace)
                    self.assertEqual(namespace['EXPECTED_HZ']['video_pixel74'], 74250000)
                    self.assertEqual(namespace['EXPECTED_HZ']['ddr_mem400'], 400000000)

    def test_physical_checker_rejects_wrong_candidate_or_mode(self):
        checker = ROOT / 'reports/hdmi_720p30_20261026/check_physical.py'
        for identity, mode in (('wrong-candidate', '720p30'), (IDENTITY_720, '1080p60')):
            with self.subTest(identity=identity, mode=mode), tempfile.TemporaryDirectory() as directory:
                physical = Path(directory)
                (physical / 'parent_integration_inputs.json').write_text(json.dumps(
                    dict(identity=identity, hdmi=dict(mode=mode))))
                result = subprocess.run([sys.executable, str(checker), 'timing', str(physical)],
                                        capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('requires the explicit native mode identity', result.stderr)
                self.assertEqual(len(list(physical.iterdir())), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
