#!/usr/bin/env python3
from pathlib import Path
from types import SimpleNamespace
import sys
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_usb1 import audit_input_samplers, audit_reset_release, HOST_RESET_ASYNC


class Usb1ConstraintTests(unittest.TestCase):
    def test_native_reset_release_with_stopped_clock(self):
        with tempfile.TemporaryDirectory(prefix='usb1-clock-') as directory:
            output = Path(directory) / 'clock.vvp'
            compilation = subprocess.run(['iverilog', '-g2012', '-s', 'tb_workstation_usb1_clock', '-o', str(output),
                                          str(ROOT / 'rtl/usb1/workstation_usb1_clock.sv'),
                                          str(ROOT / 'sim/usb1/tb_workstation_usb1_clock.sv')], capture_output=True, text=True)
            self.assertEqual(compilation.returncode, 0, compilation.stdout + compilation.stderr)
            result = subprocess.run(['vvp', str(output)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS USB1 reset CDC', result.stdout)
            print(result.stdout, flush=True)

    def test_reset_exception_requires_the_three_stage_chain(self):
        cells = {f'clock/pll/u_pll_init/state_{index}_s0': dict(kind='DFFCE') for index in range(3)}
        pins = {}
        for index in range(3):
            name = f'clock/release_q_{index}_s0'
            cells[name] = dict(kind='DFFCE', parameters=dict(INIT="1'b0"))
            pins[name] = dict(D='clock/VCC' if index==0 else 'stage' + str(index-1),
                              Q='stage' + str(index), CLK='usb48', CLEAR='qualified', CE='clock/VCC')
        netlist = SimpleNamespace(cells=cells, pin=lambda name, port: pins[name][port])
        self.assertEqual(audit_reset_release(netlist, HOST_RESET_ASYNC)['release_cycles'], 3)
        with self.assertRaisesRegex(ValueError, 'exception is missing'):
            audit_reset_release(netlist, HOST_RESET_ASYNC.replace('release_q', 'business_state'))
        pins['clock/release_q_2_s0']['D'] = 'raw_clock50_signal'
        with self.assertRaisesRegex(ValueError, 'connectivity drifted'):
            audit_reset_release(netlist, HOST_RESET_ASYNC)

    def fixture(self, board):
        prefix = 'host/phy/phy_0' if board == '138k' else 'usb/phy/phy_0'
        pattern = 'host/phy/phy*' if board == '138k' else 'usb*/phy/phy*'
        negative = 'usb1_dn' if board == '138k' else 'usb1_dm'
        cells = {}
        timing = []
        for ports, register in (('usb1_dp', 'rx_dp_ms'), (negative, 'rx_dn_ms'),
                                ('usb1_dp ' + negative, 'rxd_ms')):
            cells[prefix + '/' + register + '_s0'] = dict(kind='DFFCE')
            timing.append(f'set_false_path -from [get_ports {{{ports}}}] '
                          f'-to [get_pins {{{pattern}/{register}*_s*/D}}]')
        return SimpleNamespace(cells=cells), '\n'.join(timing)

    def test_actual_phy_instance_suffix_for_both_boards(self):
        for board in ('138k', '25k'):
            with self.subTest(board=board):
                netlist, timing = self.fixture(board)
                result = audit_input_samplers(netlist, timing, board)
                self.assertEqual(len(result), 3)
                self.assertTrue(all('/phy_0/' in pin for pin in result.values()))

    def test_missing_or_ambiguous_first_stage_rejected(self):
        for board in ('138k', '25k'):
            with self.subTest(board=board):
                netlist, timing = self.fixture(board)
                first = next(iter(netlist.cells))
                netlist.cells.pop(first)
                with self.assertRaisesRegex(ValueError, 'exactly one first-stage'):
                    audit_input_samplers(netlist, timing, board)
                netlist, timing = self.fixture(board)
                first = next(iter(netlist.cells))
                netlist.cells[first.replace('/phy_0/', '/phy_1/')] = dict(kind='DFFCE')
                with self.assertRaisesRegex(ValueError, 'exactly one first-stage'):
                    audit_input_samplers(netlist, timing, board)

    def test_old_unmatched_or_missing_constraint_rejected(self):
        for board in ('138k', '25k'):
            with self.subTest(board=board):
                netlist, timing = self.fixture(board)
                with self.assertRaisesRegex(ValueError, 'exactly one first-stage'):
                    audit_input_samplers(netlist, timing.replace('/phy*/', '/phy/'), board)
                with self.assertRaisesRegex(ValueError, 'exactly one first-stage'):
                    audit_input_samplers(netlist, timing.split('\n', 1)[1], board)


if __name__ == '__main__':
    unittest.main()
