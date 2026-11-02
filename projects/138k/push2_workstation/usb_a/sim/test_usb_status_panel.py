"""Real CDC, renderer-stream backpressure and USB device/status pixel checks."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import sys
import os
import re

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.workstation_baselines import load_baseline


class UsbStatusPanel(unittest.TestCase):
    @unittest.skipUnless(shutil.which('iverilog'),'requires Icarus Verilog')
    def test_status_ports_are_internal_only(self):
        source=ROOT/'rtl/workstation/workstation_usb2_hotplug_top.sv'
        with tempfile.TemporaryDirectory(prefix='usb-status-pins-') as directory:
            output=Path(directory)/'preprocessed.sv'
            for internal in (False,True):
                subprocess.run(['iverilog','-g2012','-E',
                    *(['-DWORKSTATION_USB_STATUS_SOURCE'] if internal else []),
                    '-o',str(output),str(source)],check=True)
                header=re.search(r'module workstation_usb2_hotplug_top.*?\);',
                                 output.read_text(),re.S).group(0)
                for name in ('status_clk_o','status_reset_n_o','display_status_o'):
                    self.assertEqual(name in header,internal,name)

    @unittest.skipUnless(shutil.which('iverilog'),'requires Icarus Verilog')
    def test_upstream_clock_stops(self):
        baseline=load_baseline(ROOT,'resource_rework_route0')
        with tempfile.TemporaryDirectory(prefix='usb-status-upstream-') as directory:
            output=Path(directory)
            cdc=output/'gw138k_stream_cdc.sv'
            cdc.write_bytes(baseline.read_bytes('src/migration/gw138k_stream_cdc.sv'))
            subprocess.run(['iverilog','-g2012','-s','tb_usb_link_status','-o',str(output/'sim'),
                str(ROOT/'sim/display/tb_usb_status_panel.sv'),
                str(ROOT/'rtl/workstation/workstation_usb2_hotplug_top.sv'),str(cdc)],check=True)
            result=subprocess.run(['vvp',str(output/'sim')],cwd=output,capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('PASS upstream USB status',result.stdout)

    @unittest.skipUnless(shutil.which('iverilog'),'requires Icarus Verilog')
    def test_status_and_raster(self):
        baseline=load_baseline(ROOT,'resource_rework_route0')
        with tempfile.TemporaryDirectory(prefix='usb-hdmi-status-') as directory:
            output=Path(directory)
            font=output/'video_font_5x7.v'
            font.write_bytes(baseline.read_bytes('src/video/video_font_5x7.v'))
            cdc=output/'gw138k_stream_cdc.sv'
            cdc.write_bytes(baseline.read_bytes('src/migration/gw138k_stream_cdc.sv'))
            subprocess.run(['iverilog','-g2012','-s','tb_usb_status_panel','-o',str(output/'sim'),
                str(ROOT/'sim/display/tb_usb_status_panel.sv'),
                str(ROOT/'rtl/display_data/workstation_usb_status_panel.sv'),
                str(cdc),str(font)],check=True)
            result=subprocess.run(['vvp',str(output/'sim')],cwd=output,capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('PASS USB status',result.stdout)
            if os.environ.get('GW138K_USB_STATUS_EVIDENCE'):
                evidence=Path(os.environ['GW138K_USB_STATUS_EVIDENCE'])
                evidence.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(output/'usb_status_panel.ppm',evidence/'usb_status_panel.ppm')
                (evidence/'simulation.log').write_text(result.stdout+result.stderr)


if __name__=='__main__':
    unittest.main(verbosity=2)
