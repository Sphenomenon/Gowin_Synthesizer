"""Clear-gated Gray paths must remain registered and prove the exact zeroing LUT."""
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from audit_clk50_cdc_routes import pointer_source


class ClearGate(unittest.TestCase):
    def design(self, same_clock=False, bad_seen=False):
        prefix = 'fifo/'
        cells = {
            'fifo/rd_gray_0_s0': ('DFFCE', {'Q': 'gray', 'D': 'next', 'CLK': 'src'}),
            'fifo/clear_wr_meta_s0': ('DFFCE', {'Q': 'meta', 'D': 'toggle', 'CLK': 'dst'}),
            'fifo/clear_wr_seen_s0': ('DFFCE', {'Q': 'seen', 'D': 'bad' if bad_seen else 'meta', 'CLK': 'dst'}),
            'fifo/gate': ('LUT3', {'I0': 'meta', 'I1': 'seen', 'I2': 'gray', 'F': 'result'}),
        }
        if same_clock:
            cells['fifo/rd_gray_0_s0'][1]['CLK'] = 'dst'
        drivers = {ports['Q']: (name, 'Q') for name, (kind, ports) in cells.items() if kind.startswith('DFF')}
        drivers['result'] = ('fifo/gate', 'F')
        return SimpleNamespace(cells=cells, drivers=drivers)

    def test_exact_clear_gate_passes_and_retains_delay_cell(self):
        result = pointer_source(self.design(), "defparam \\fifo/gate .INIT=8'h90;", 'result', 'dst', 'fifo')
        self.assertEqual(result, ('fifo/rd_gray_0_s0', 'Q', ['fifo/gate']))

    def test_wrong_lut_truth_table_rejected(self):
        with self.assertRaises(ValueError):
            pointer_source(self.design(), "defparam \\fifo/gate .INIT=8'h80;", 'result', 'dst', 'fifo')

    def test_arbitrary_local_register_is_not_a_clear_seen(self):
        with self.assertRaises(ValueError):
            pointer_source(self.design(bad_seen=True), "defparam \\fifo/gate .INIT=8'h90;", 'result', 'dst', 'fifo')

    def test_same_clock_first_stage_is_allowed_for_second_stage_analysis(self):
        result = pointer_source(self.design(same_clock=True), "defparam \\fifo/gate .INIT=8'h90;", 'result', 'dst', 'fifo')
        self.assertEqual(result[0], 'fifo/rd_gray_0_s0')

    def test_missing_truth_table_fails_closed(self):
        with self.assertRaises(ValueError):
            pointer_source(self.design(), '', 'result', 'dst', 'fifo')


if __name__ == '__main__':
    unittest.main()
