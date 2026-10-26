"""FPC audio serial decoding with the real mailbox and direct DAC reference."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_baselines import load_baseline


class FpcAudio(unittest.TestCase):
    def test_push_and_25k_knobs_share_committed_cc7(self):
        with tempfile.TemporaryDirectory(prefix='workstation-volume-') as directory:
            stage = Path(directory)
            memory = stage / 'pitch_bend.mem'
            memory.write_bytes(load_baseline(ROOT, 'resource_rework_route0').read_bytes(
                'sim/data/audio_chain/pitch_bend_q20.mem'))
            binary = stage / 'simulation'
            sources = [ROOT / name for name in ('sim/audio/tb_workstation_volume.sv',
                'rtl/audio/push2_controls.sv', 'rtl/control/workstation_parameters.sv',
                'rtl/audio/scope_vec/scope_tf_control.sv')]
            result = subprocess.run(['iverilog', '-g2012', '-s', 'tb_workstation_volume',
                '-DAUDIO_BEND_MEM_FILE="'+str(memory)+'"', '-o', str(binary), *map(str,sources)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            result = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertIn('PASS volume controls:', result.stdout)

    def test_i2s_pcm_clocks_muting_and_reference_recovery(self):
        with tempfile.TemporaryDirectory(prefix='fpc-audio-') as directory:
            stage = Path(directory)
            mailbox = stage / 'gw138k_stream_cdc.sv'
            mailbox.write_bytes(load_baseline(ROOT, 'resource_rework_route0').read_bytes(
                'src/migration/gw138k_stream_cdc.sv'))
            binary = stage / 'simulation'
            compile_result = subprocess.run(['iverilog', '-g2012', '-s', 'tb_workstation_fpc_audio', '-o', str(binary),
                str(ROOT / 'sim/audio/tb_workstation_fpc_audio.sv'), str(ROOT / 'rtl/audio/workstation_fpc_audio.sv'),
                str(mailbox)], capture_output=True, text=True, timeout=30)
            self.assertEqual(compile_result.returncode, 0, compile_result.stdout + compile_result.stderr)
            result = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS FPC audio:', result.stdout)


if __name__ == '__main__':
    unittest.main()
