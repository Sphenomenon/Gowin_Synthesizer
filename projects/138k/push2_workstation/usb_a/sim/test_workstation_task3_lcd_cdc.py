#!/usr/bin/env python3
"""Real paired VG pad isolation and synchronizer mutation controls."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_runtime_pcm_cdc import Graph
from tools.workstation_task3_lcd_cdc_audit import audit_lcd_input_chains, SOURCE_SHA256, PAIR, PHY


@unittest.skipUnless(os.environ.get('GW138K_TASK3_PAIRED_M') and os.environ.get('GW138K_TASK3_PAIRED_W'),
    'set GW138K_TASK3_PAIRED_M/W to immutable prepared candidate directories with synthesis')
class PairedLCDChains(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidates = {}
        for role in ('M', 'W'):
            stage = Path(os.environ['GW138K_TASK3_PAIRED_' + role]) / 'workstation/Prj1'
            vg = stage / 'impl/gwsynthesis/custom_138k_integration.vg'
            cls.candidates[role] = (stage, protocol_netlist(vg.read_text(), mapping='synthesis'))

    def test_actual_m_and_w_chains(self):
        for role, (stage, n) in self.candidates.items():
            with self.subTest(role=role):
                result = audit_lcd_input_chains(n, stage=stage, role=role)
                self.assertEqual(result['input_pad_count'], 7)
                self.assertEqual(result['synchronized_state_bits'], 20)
                self.assertTrue(result['all_raw_pad_fanout_exact'])
                self.assertFalse(result['whole_source_CDC_accepted'])
                self.assertFalse(result['hardware_tested'])

    def test_actual_netlist_mutations_fail(self):
        for role, (stage, n) in self.candidates.items():
            g = Graph(n)
            first = g.register(PHY, 'req_meta')
            second = g.register(PHY, 'req_sync')
            data = g.register(PHY, 'data_settled', 0)
            spare = g.register(PHY, 'rx_low', 0)
            port, bit = ('lcd_g', 5) if role == 'M' else ('lcd_r', 4)
            pad = '%s_%d_iobuf' % (port, bit)
            raw = n.cells[first]['ports']['D']
            mutations = (
                ('first stage clock', first, 'ports', 'CLK', 'audio_clk'),
                ('first stage disabled', first, 'ports', 'CE', "1'b0"),
                ('first stage reset', first, 'ports', 'CLEAR', "1'b0"),
                ('first stage init', first, 'parameters', 'INIT', "1'b1"),
                ('second stage bypass', second, 'ports', 'D', raw),
                ('third data stage clock', data, 'ports', 'CLK', 'audio_clk'),
                ('receive pad drive', pad, 'ports', 'OEN', "1'b0"),
                ('early metastable fanout', spare, 'ports', 'D', n.cells[first]['ports']['Q']),
                ('raw asynchronous fanout', spare, 'ports', 'D', raw),
            )
            for label, path, part, pin, value in mutations:
                with self.subTest(role=role, mutation=label):
                    original = deepcopy(n.cells[path])
                    try:
                        n.cells[path][part][pin] = value
                        with self.assertRaises(ValueError):
                            audit_lcd_input_chains(n, stage=stage, role=role)
                    finally:
                        n.cells[path].clear()
                        n.cells[path].update(original)

    def test_source_and_role_binding_fail_closed(self):
        for role, (stage, n) in self.candidates.items():
            with self.subTest(role=role, mutation='opposite role'):
                with self.assertRaises(ValueError):
                    audit_lcd_input_chains(n, stage=stage, role='W' if role == 'M' else 'M')
            with TemporaryDirectory() as directory:
                copy = Path(directory)
                for relative in SOURCE_SHA256:
                    target = copy / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes((stage / relative).read_bytes())
                relative = next(iter(SOURCE_SHA256))
                with (copy / relative).open('a') as source:
                    source.write('\n// changed source\n')
                with self.subTest(role=role, mutation='source drift'):
                    with self.assertRaisesRegex(ValueError, 'reviewed source changed'):
                        audit_lcd_input_chains(n, stage=copy, role=role)


if __name__ == '__main__':
    unittest.main()
