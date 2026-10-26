"""Remote-example provenance, reversed audio cable, and live LCD composition."""

from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_baselines import load_baseline
from tools import workstation_board_peripherals as peripherals, workstation_pinout as pinout
from test_workstation_pinout import fixture


class Peripherals(unittest.TestCase):
    def test_remote_example_drift_is_rejected(self):
        profile = peripherals.reviewed_profile(ROOT)
        self.assertIn('mode_d', profile['excluded'])
        self.assertFalse(profile['hardware_acceptance_inherited'])
        with patch.object(peripherals, 'sha', return_value='0'*64):
            with self.assertRaisesRegex(ValueError, 'reviewed remote peripheral input changed'):
                peripherals.reviewed_profile(ROOT)

    def test_reversed_audio_and_lcd_do_not_change_original_pinout(self):
        profile, payloads, core = fixture()
        netlists = {role: pinout.Netlist(payload) for role, payload in payloads.items()}
        plan = pinout.resolve(profile, netlists, core)
        original = json.loads(json.dumps(plan))
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            (stage / 'constraints').mkdir()
            peripherals.prepare(ROOT, stage, plan, stage)
            self.assertEqual(plan['ports']['dac_pdn_n']['balls'], ['C13'])
            self.assertEqual(plan['ports']['dac_mclk']['balls'], ['B13'])
            self.assertEqual(plan['ports']['hp_bck']['balls'], ['A13'])
            self.assertEqual(plan['ports']['amp_fpga_det']['balls'], ['C17'])
            self.assertEqual(plan['ports']['lcd_bl']['balls'], ['F21'])
            self.assertNotIn('K18', plan['reserved_balls'].values())
            self.assertEqual(pinout.parse_locations((stage / 'custom_138k.locations.cst').read_text()),
                             {port: record['balls'] for port, record in plan['ports'].items()})
        self.assertEqual(pinout.resolve(profile, netlists, core), original)

    def test_pin_collision_and_audio_drift_are_rejected(self):
        for mutation in ('lcd_collision', 'audio_drift'):
            profile, payloads, core = fixture()
            plan = pinout.resolve(profile, {role: pinout.Netlist(payload) for role, payload in payloads.items()}, core)
            if mutation == 'lcd_collision':
                plan['ports']['conflicting_user_pin'] = dict(balls=['F21'], origin='test')
            else:
                plan['ports']['dac_sd']['balls'] = ['Z99']
            with tempfile.TemporaryDirectory() as directory:
                stage = Path(directory)
                (stage / 'constraints').mkdir()
                with self.assertRaises(ValueError):
                    peripherals.prepare(ROOT, stage, plan, stage)
                self.assertFalse((stage / 'custom_138k.locations.cst').exists())

    def test_live_lcd_raster_snapshot_and_clock_recovery(self):
        baseline = load_baseline(ROOT, 'resource_rework_route0')
        with tempfile.TemporaryDirectory(prefix='workstation-lcd-') as directory:
            stage = Path(directory)
            for name in ('src/migration/gw138k_stream_cdc.sv', 'src/video/video_font_5x7.v'):
                (stage / Path(name).name).write_bytes(baseline.read_bytes(name))
            sources = [ROOT / name for name in ('sim/display/tb_workstation_lcd.sv',
                'rtl/display_data/workstation_lcd.sv', 'rtl/display_data/push2_surface_pixels.sv',
                'rtl/push2/push2_song_screen.sv')]
            sources += [stage / 'gw138k_stream_cdc.sv', stage / 'video_font_5x7.v']
            binary = stage / 'simulation'
            result = subprocess.run(['iverilog', '-g2012', '-s', 'tb_workstation_lcd', '-o', str(binary),
                                     *map(str, sources)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            result = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=240)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertIn('PASS LCD workstation:', result.stdout)


if __name__ == '__main__':
    unittest.main()
