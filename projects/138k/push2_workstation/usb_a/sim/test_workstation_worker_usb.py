#!/usr/bin/env python3
"""W-DEMO production MIDI/PL adapter and retired-USB-interface regression."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_usb2_input import input_bundle
from tools.stage_usb_firmware import stage_usb2_cpu_firmware


class WorkerUSB(unittest.TestCase):
    def test_touch_mapping_and_committed_pl_feedback(self):
        vendor = ROOT / 'vendor/usb_host_fs_8fc3/firmware'
        with tempfile.TemporaryDirectory(prefix='worker-usb-c-') as directory:
            binary = Path(directory) / 'worker'
            subprocess.run(['cc', '-std=c99', '-O1', '-g', '-Wall', '-Wextra',
                            '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                            '-DWORKSTATION_WORKER_DEMO=1', '-I'+str(vendor), '-I'+str(vendor/'usb'),
                            str(ROOT/'sim/test_gw25k_panel.c'), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True, timeout=60)

    def test_worker_owner_fifo_and_retired_service_requests(self):
        bundle = input_bundle(ROOT)
        with tempfile.TemporaryDirectory(prefix='worker-usb-rtl-') as directory:
            output = Path(directory)
            support = []
            for name, payload in bundle['payloads'].items():
                if name.endswith(('gw138k_stream_cdc.sv','gw138k_usb_event_fifo.v')):
                    path=output/Path(name).name
                    path.write_bytes(payload)
                    support.append(str(path))
            command=['iverilog','-g2012','-s','tb_workstation_worker_usb','-o',str(output/'test'),
                     str(ROOT/'rtl/workstation/workstation_worker_usb.sv'),
                     str(ROOT/'rtl/workstation/workstation_usb2_service_adapter.sv'),
                     *support,str(ROOT/'sim/usb2/tb_workstation_worker_usb.sv')]
            subprocess.run(command,cwd=ROOT,check=True,capture_output=True,text=True)
            subprocess.run(['vvp',str(output/'test')],cwd=ROOT,check=True,timeout=30)

    def test_real_worker_firmware(self):
        with tempfile.TemporaryDirectory(prefix='worker-usb-rom-') as directory:
            result=stage_usb2_cpu_firmware(ROOT,Path(directory)/'firmware',ROOT/'firmware.c',
                os.environ.get('GW138K_RISCV_PREFIX'),workstation=True,worker_demo=True)
            self.assertTrue(result['worker_demo'])
            self.assertTrue(result['high_speed_allowed'])
            self.assertLess(result['static_ram_end'],60000)
            self.assertEqual(len((Path(directory)/'firmware/usb2_cpu.hex').read_text().splitlines()),16384)
            print('PASS W-DEMO RV32I firmware:',result['firmware_bytes'],'bytes;',
                  result['stack_margin_bytes'],'bytes stack margin',flush=True)


if __name__=='__main__':
    unittest.main()
