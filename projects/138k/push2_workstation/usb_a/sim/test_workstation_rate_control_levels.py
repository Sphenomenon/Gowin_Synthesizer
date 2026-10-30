"""Real transaction/serializer source test; explicit digital skew, never PVT."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'rtl/audio/workstation_sample_rate_switch.sv'


def original_combinational_outputs(source):
    """Reconstruct the former output behavior without a private old RTL/VG copy."""
    declaration = 'output reg quiesce_o, dac_mute_o, stream_flush_o,'
    if source.count(declaration) != 1:
        raise ValueError('reviewed registered control output declaration changed')
    source = source.replace(declaration, 'output wire quiesce_o, dac_mute_o, stream_flush_o,')
    expressions = {
        'quiesce_o': 'target_state != RUN && target_state != PREFILL && target_state != RESUME',
        'dac_mute_o': 'target_state != RUN && target_state != QUIESCE && target_state != RESUME',
        'stream_flush_o': 'target_state != RUN && target_state != QUIESCE && target_state != PREFILL && target_state != RESUME',
    }
    for output, expression in expressions.items():
        anchor = '            ' + output + ' <= ' + expression + ';\n'
        if source.count(anchor) != 1:
            raise ValueError('reviewed registered control output assignment changed: ' + output)
        source = source.replace(anchor, '')
    anchor = '    task automatic transition_to(input [3:0] target_state);\n'
    if source.count(anchor) != 1:
        raise ValueError('reviewed state transition owner changed')
    decode = ''.join('    assign ' + output + ' = ' + expression.replace('target_state', 'state') + ';\n'
                     for output, expression in expressions.items())
    return source.replace(anchor, decode + '\n' + anchor)


class RateControlLevels(unittest.TestCase):
    def simulate(self, source, rate44=0):
        for command in ('iverilog', 'vvp'):
            self.assertIsNotNone(shutil.which(command), command + ' is required')
        with tempfile.TemporaryDirectory(prefix='workstation-rate-control-levels-') as directory:
            path = Path(directory)
            rtl = path / 'transaction.sv'
            rtl.write_text(source)
            binary = path / 'simulation'
            compiled = subprocess.run([
                'iverilog', '-g2012', '-s', 'tb_workstation_rate_control_levels',
                '-Ptb_workstation_rate_control_levels.RATE44=' + str(rate44), '-o', str(binary),
                str(ROOT / 'sim/audio/tb_workstation_rate_control_levels.sv'), str(rtl),
                str(ROOT / 'rtl/audio/workstation_i2s_serializer.sv')],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=30)

    def test_registered_owner_survives_legal_state_bit_skew(self):
        for rate44 in (0, 1):
            with self.subTest(rate44=rate44):
                result = self.simulate(SOURCE.read_text(), rate44)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('PASS rate-control CDC levels:', result.stdout)
                print('Rate44=' + str(rate44) + '\n' + result.stdout.strip())

    def test_former_combinational_outputs_are_rejected(self):
        for rate44 in (0, 1):
            with self.subTest(rate44=rate44):
                result = self.simulate(original_combinational_outputs(SOURCE.read_text()), rate44)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('FAIL rate-control CDC levels:', result.stdout)
                sample = re.search(r'sampled_quiesce_cycles=(\d+) unexpected_empty_cycles=(\d+) request_count=(\d+)', result.stdout)
                self.assertIsNotNone(sample, result.stdout)
                self.assertGreater(int(sample[1]), 0)
                self.assertGreater(int(sample[2]), 0)
                self.assertEqual(int(sample[3]), 2)
                print('Expected rejection of former combinational outputs, rate44=' + str(rate44) + ':\n' + result.stdout.strip())


if __name__ == '__main__':
    unittest.main()
