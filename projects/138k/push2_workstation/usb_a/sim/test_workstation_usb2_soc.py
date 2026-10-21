#!/usr/bin/env python3
"""Real RV32I execution through the native USB2 component; no programming."""

from pathlib import Path
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import test_workstation_usb2_mmio as mmio_regression


ROOT = mmio_regression.ROOT
sys.path.insert(0, str(ROOT / 'tools'))
from stage_usb_firmware import stage_usb2_cpu_firmware, verify_usb2_cpu_vendor


def soc_sources():
    vendor = verify_usb2_cpu_vendor(ROOT)
    return [*mmio_regression.mmio_sources(), ROOT / 'rtl/usb2/workstation_usb2_cpu_bus.sv',
            ROOT / 'rtl/usb2/workstation_usb2_soc.sv', vendor / 'src/VexRiscv.v', vendor / 'src/simpleuart.v']


class NativeCpu(unittest.TestCase):
    run_simulation = mmio_regression.CpuBoundary.run_simulation

    def test_cpu_bus_memory_ordering_and_faults(self):
        vendor = verify_usb2_cpu_vendor(ROOT)
        self.run_simulation('tb_workstation_usb2_cpu_bus', [
            ROOT / 'rtl/usb2/workstation_usb2_cpu_bus.sv', vendor / 'src/simpleuart.v',
            ROOT / 'sim/usb2/tb_workstation_usb2_cpu_bus.sv',
        ], 'PASS workstation_usb2_cpu_bus:')

    def test_actual_rv32i_firmware_with_high_and_full_speed_25k(self):
        self.assertIsNotNone(shutil.which('verilator'), 'Verilator is required for actual CPU execution')
        _, device_vendor, device_sources = mmio_regression.device_core_sources()
        with tempfile.TemporaryDirectory(prefix='workstation-usb2-cpu-system-') as directory:
            stage = Path(directory)
            metadata = stage_usb2_cpu_firmware(ROOT, stage / 'firmware', ROOT / 'sim/usb2/cpu_enumeration.c')
            self.assertEqual(metadata['isa'], 'rv32i')
            self.assertLess(metadata['static_ram_end'], 60000)
            for high_speed in (1, 0):
                with self.subTest(high_speed=high_speed):
                    build = stage / f'obj_{high_speed}'
                    command = ['verilator', '--binary', '--timing', '--timescale-override', '1ns/1ps',
                               '-Wno-fatal', '-j', '4', '--top-module', 'tb_workstation_usb2_soc_25k',
                               '--Mdir', str(build), '-o', 'simulation', f'-GHIGH_SPEED={high_speed}',
                               '-I' + str(device_vendor), *(str(source) for source in soc_sources()),
                               str(ROOT / 'sim/usb2/usb3300_register_model.sv'), str(ROOT / 'sim/usb2/usb3300_packet_model.sv'),
                               str(ROOT / 'sim/usb2/usb3300_host_model.sv'), str(ROOT / 'sim/usb2/tb_workstation_usb2_soc_25k.sv'),
                               *(str(source) for source in device_sources)]
                    compilation = subprocess.run(command, text=True, capture_output=True, timeout=180)
                    self.assertEqual(compilation.returncode, 0, compilation.stdout + compilation.stderr)
                    for warning in re.findall(r'^%Warning[^\n]*', compilation.stderr, re.M):
                        if '/rtl/usb2/' in warning:
                            self.assertTrue(warning.startswith('%Warning-SYNCASYNCNET:'), warning)
                    execution = subprocess.run([str(build / 'simulation')], cwd=stage / 'firmware',
                                               text=True, capture_output=True, timeout=600)
                    self.assertEqual(execution.returncode, 0, execution.stdout + execution.stderr)
                    self.assertIn(f'PASS workstation_usb2_soc_25k: HS={high_speed}', execution.stdout)
                    print(execution.stdout.strip(), flush=True)
            print('CPU firmware:', json.dumps(metadata, sort_keys=True), flush=True)


if __name__ == '__main__':
    unittest.main()
