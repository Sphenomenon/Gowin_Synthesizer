from pathlib import Path
import runpy
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
ADAPTER=ROOT/'reports/hdmi_usb3_20261025/prepare_jtag.py'


class HdmiUsb3Jtag(unittest.TestCase):
    def test_reuses_d3_netlist_without_rtl_synthesis_or_pin_changes(self):
        adapter=runpy.run_path(str(ADAPTER),run_name='jtag_probe_test')
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'probe'
            record=adapter['prepare'](output)
            self.assertEqual(record['user_code'],'0xC11025D5')
            self.assertFalse(record['diagnostic_subset_synthesized'])
            self.assertFalse(record['entire_workstation_resynthesized'])
            self.assertFalse(record['sram_programmed'])
            self.assertFalse(record['flash_programmed'])
            self.assertEqual(adapter['digest'](output/adapter['NETLIST']),adapter['PARENT_NETLIST_SHA'])
            for name in ('diagnostic.cst','diagnostic.sdc','hdmi_usb3_diagnostic.sv'):
                self.assertEqual((output/name).read_bytes(),(adapter['PARENT']/name).read_bytes())
            script=(output/'run.tcl').read_text()
            self.assertIn('\nrun pnr\n',script)
            self.assertNotIn('run all',script)
            self.assertNotIn('run syn',script)
            self.assertNotIn('open_project',script)
            self.assertIn('add_file -type netlist',script)
            self.assertNotIn('add_file -type verilog',script)
            self.assertFalse((output/'diagnostic.gprj').exists())
            configuration=ET.parse(output/'diagnostic.gao')
            core=configuration.getroot().find('AoCore')
            self.assertEqual(core.attrib['sample_clock'],'clk_50m_d')
            self.assertEqual([signal.text for signal in core.find('SignalList')],list(adapter['SIGNALS']))
            self.assertEqual(len(set(adapter['SIGNALS'])),len(adapter['SIGNALS']))
            for relative,expected in record['input_sha256'].items():
                self.assertEqual(adapter['digest'](output/relative),expected)
            with self.assertRaises(ValueError):
                adapter['prepare'](output)

    def test_rejects_changed_parent_before_creating_output(self):
        adapter=runpy.run_path(str(ADAPTER),run_name='jtag_probe_test')
        with tempfile.TemporaryDirectory() as directory:
            parent=Path(directory)/'changed_d3'
            parent.mkdir()
            (parent/'inputs.json').write_text('{}\n')
            output=Path(directory)/'probe'
            with self.assertRaisesRegex(ValueError,'identity changed'):
                adapter['prepare'](output,parent=parent)
            self.assertFalse(output.exists())


if __name__=='__main__':
    unittest.main()
