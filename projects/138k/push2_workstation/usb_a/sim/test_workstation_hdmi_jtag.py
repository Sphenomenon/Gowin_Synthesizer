from pathlib import Path
import runpy
import tempfile
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / 'reports/hdmi_usb3_20261025/prepare_workstation_jtag.py'


class WorkstationHdmiJtag(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = runpy.run_path(str(ADAPTER), run_name='workstation_jtag_test')

    def test_exact_netlist_and_constraints_with_no_synthesis_or_deployment(self):
        adapter = self.adapter
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'probe'
            record = adapter['prepare'](output)
            self.assertEqual(record['user_code'], '0xC11025E1')
            for field in ('entire_workstation_resynthesized', 'implementation_started',
                          'hardware_tested', 'sram_programmed', 'flash_programmed',
                          'deployment_authorized', 'release_ready'):
                self.assertFalse(record[field])
            for relative in (adapter['NETLIST'], 'physical.cst', 'physical.sdc'):
                self.assertEqual(adapter['digest'](output / relative),
                                 adapter['digest'](adapter['PARENT'] / relative))
            for relative, expected in record['input_sha256'].items():
                self.assertEqual(adapter['digest'](output / relative), expected)
            script = (output / 'run.tcl').read_text()
            self.assertIn('\nrun pnr\n', script)
            for forbidden in ('run all', 'run syn', 'open_project', 'programmer', 'set_false_path'):
                self.assertNotIn(forbidden, script)
            original = (adapter['PARENT'] / 'run.tcl').read_text()
            for anchor, replacement in record['exact_tcl_adaptations'].items():
                original = original.replace(anchor, replacement)
            self.assertEqual(script, original)
            self.assertEqual(set(source.suffix for source in output.iterdir()),
                             {'.vg', '.cst', '.sdc', '.tcl', '.gao', '.json'})
            configuration = ET.parse(output / 'workstation.gao').getroot()
            core = configuration.find('AoCore')
            self.assertEqual(core.get('sample_clock'), 'clk_50m_d')
            self.assertEqual(core.get('storage_depth'), '1024')
            self.assertEqual(core.get('module_name'), adapter['TOP_MODULE'])
            signals = [signal.text for signal in core.find('SignalList')]
            self.assertEqual(signals, list(adapter['SIGNALS']))
            self.assertEqual(len(signals), 64)
            self.assertEqual(len(signals), len(set(signals)))
            self.assertEqual(configuration.findtext('GAO_ID'), '0010010111100001')
            self.assertEqual(core.findtext('Triggers/Trigger/SignalList/Signal'), 'reset_n')
            with self.assertRaisesRegex(ValueError, 'new experiment output'):
                adapter['prepare'](output)

    def test_changed_physical_parent_is_rejected_before_output_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / 'changed'
            parent.mkdir()
            (parent / 'physical_inputs.json').write_text('{}\n')
            output = Path(directory) / 'probe'
            with self.assertRaisesRegex(ValueError, 'identity changed'):
                self.adapter['prepare'](output, parent=parent)
            self.assertFalse(output.exists())

    def test_missing_signal_and_changed_bit_range_are_rejected(self):
        adapter = self.adapter
        netlist = (adapter['PARENT'] / adapter['NETLIST']).read_text()
        adapter['verify_signals'](netlist)
        for original, changed in (
            ('wire [127:8] video_diagnostics;', 'wire [127:16] video_diagnostics;'),
            ('wire [7:0] memory_flags;', 'wire [7:4] memory_flags;'),
            ('wire [1:0] flags_sync;', 'wire [1:1] flags_sync;'),
            ('wire clk_50m_d;', 'wire missing_50m;'),
        ):
            with self.subTest(original=original):
                self.assertIn(original, netlist)
                with self.assertRaisesRegex(ValueError, 'observation (bit|signal) missing'):
                    adapter['verify_signals'](netlist.replace(original, changed))


if __name__ == '__main__':
    unittest.main()
