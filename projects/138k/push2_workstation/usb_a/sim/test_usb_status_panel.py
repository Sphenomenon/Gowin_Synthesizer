"""Real CDC, renderer-stream backpressure and USB device/status pixel checks."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import sys
import os

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.workstation_baselines import load_baseline


class UsbStatusPanel(unittest.TestCase):
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
