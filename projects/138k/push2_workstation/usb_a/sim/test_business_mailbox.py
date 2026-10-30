#!/usr/bin/env python3
"""Unselected S1a transport RTL and real C driver; no EDA/hardware operation."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BusinessMailbox(unittest.TestCase):
    def test_mailbox_fences_and_bounded_immutable_slots(self):
        with tempfile.TemporaryDirectory(prefix='business-mailbox-rtl-') as directory:
            binary=Path(directory)/'simulation'
            result=subprocess.run(['iverilog','-g2012','-Wall','-s','tb_business_mailbox','-o',str(binary),
                str(ROOT/'sim/services/tb_business_mailbox.sv'),str(ROOT/'rtl/services/workstation_business_mailbox.sv')],
                capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('PASS business mailbox:',result.stdout)

    def test_real_c_api_all_access_failures_with_sanitizers(self):
        compiler=shutil.which('cc')
        self.assertIsNotNone(compiler,'host C compiler required for the checked callback boundary')
        with tempfile.TemporaryDirectory(prefix='business-mailbox-c-') as directory:
            binary=Path(directory)/'host'
            result=subprocess.run([compiler,'-std=c11','-O2','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(ROOT/'firmware/ae350'),
                str(ROOT/'firmware/ae350/business_mailbox.c'),str(ROOT/'sim/ae350_business_mailbox_host.c'),'-o',str(binary)],
                capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('PASS business mailbox C API:',result.stdout)

    def test_no_production_or_shared_wire_selection(self):
        sys.path.insert(0,str(ROOT))
        from tools.workstation_runtime_profile import SOURCES,DEPENDENCIES
        from tools.workstation_recording_policy import SOURCES as REC_SOURCES,DEPENDENCIES as REC_DEPENDENCIES
        from tools.stage_ae350_firmware import selected_sources
        self.assertNotIn('rtl/services/workstation_business_mailbox.sv',(*SOURCES,*DEPENDENCIES,*REC_SOURCES,*REC_DEPENDENCIES))
        for enabled in (False,True):
            self.assertNotIn('business_mailbox.c',selected_sources(enabled))
        for wrapper in ROOT.glob('rtl/workstation/workstation_profile*.sv'):
            self.assertNotIn('business_mailbox',wrapper.read_text())


if __name__=='__main__':
    unittest.main()
