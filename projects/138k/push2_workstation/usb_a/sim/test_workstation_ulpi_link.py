#!/usr/bin/env python3
"""ULPI physical-bus regression; no FPGA, private staging or external model."""

from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def device_core_sources():
    device = ROOT.parents[2] / '25k/prj/usb2_device'
    vendor = device.parent / 'vendor/ultraembedded_usb_hs/cdc'
    upstream = json.loads((vendor.parent / 'UPSTREAM.json').read_text())
    for group, record in upstream.items():
        for name, expected in record['files'].items():
            source = vendor.parent / group / name
            actual = hashlib.sha256(source.read_bytes()).hexdigest()
            if actual != expected:
                raise AssertionError(f'Immutable USB support source changed: {source}')
    return device, vendor, [
        device / 'hs/usb_cdc_core.v', device / 'hs/usb_desc_rom.v',
        *(vendor / name for name in ('usbf_device_core.v', 'usbf_sie_tx.v', 'usbf_sie_rx.v', 'usbf_crc16.v')),
    ]


class PhysicalLink(unittest.TestCase):
    def run_simulation(self, top, sources, expected, compiler_options=(), timeout=30):
        self.assertIsNotNone(shutil.which('iverilog'), 'iverilog is required')
        self.assertIsNotNone(shutil.which('vvp'), 'vvp is required')
        with tempfile.TemporaryDirectory(prefix='workstation-ulpi-') as directory:
            executable = Path(directory) / 'simulation'
            compilation = subprocess.run([
                'iverilog', '-g2012', '-Wall', '-s', top, '-o', str(executable),
                *compiler_options,
                *(str(ROOT / source) for source in sources),
            ], text=True, capture_output=True, timeout=30)
            self.assertEqual(compilation.returncode, 0, compilation.stdout + compilation.stderr)
            simulation = subprocess.run(['vvp', str(executable)], text=True, capture_output=True, timeout=timeout)
            self.assertEqual(simulation.returncode, 0, simulation.stdout + simulation.stderr)
            self.assertIn(expected, simulation.stdout)
            print(simulation.stdout.strip())

    def test_register_packet_arbitration_and_failures(self):
        self.run_simulation('tb_workstation_ulpi_link', [
            'rtl/usb2/workstation_ulpi_link.sv',
            'sim/usb2/tb_workstation_ulpi_link.sv',
        ], 'PASS workstation_ulpi_link:')

    def test_host_initialization_on_physical_bus(self):
        self.run_simulation('tb_workstation_usb3300_host_init', [
            'rtl/usb2/workstation_ulpi_link.sv',
            'rtl/usb2/workstation_usb3300_host_init.sv',
            'sim/usb2/usb3300_register_model.sv',
            'sim/usb2/tb_workstation_usb3300_host_init.sv',
        ], 'PASS workstation_usb3300_host_init:')

    def test_clock_supervisor_without_a_running_phy_clock(self):
        self.run_simulation('tb_workstation_ulpi_supervisor', [
            'rtl/usb2/workstation_ulpi_supervisor.sv',
            'sim/usb2/tb_workstation_ulpi_supervisor.sv',
        ], 'PASS workstation_ulpi_supervisor:')

    def test_supervised_host_composition_and_runtime_handoff(self):
        self.run_simulation('tb_workstation_usb3300_host_link', [
            'rtl/usb2/workstation_ulpi_supervisor.sv',
            'rtl/usb2/workstation_ulpi_link.sv',
            'rtl/usb2/workstation_usb3300_host_init.sv',
            'rtl/usb2/workstation_usb3300_host_link.sv',
            'sim/usb2/usb3300_register_model.sv',
            'sim/usb2/tb_workstation_usb3300_host_link.sv',
        ], 'PASS workstation_usb3300_host_link:')

    def test_high_speed_host_port_and_full_speed_fallback(self):
        self.run_simulation('tb_workstation_usb2_host_port', [
            'rtl/usb2/workstation_usb2_host_port.sv',
            'sim/usb2/tb_workstation_usb2_host_port.sv',
        ], 'PASS workstation_usb2_host_port:')

    def test_physical_host_composition_with_existing_25k_device(self):
        _, vendor, device_sources = device_core_sources()
        sources = [
            *sorted((ROOT / 'rtl/usb2').glob('*.sv')),
            ROOT / 'sim/usb2/usb3300_register_model.sv',
            ROOT / 'sim/usb2/tb_workstation_usb2_25k_negotiation.sv',
            *device_sources,
        ]
        for high_speed in (1, 0):
            with self.subTest(high_speed=high_speed):
                self.run_simulation('tb_workstation_usb2_25k_negotiation', sources,
                                    f'PASS workstation_usb2_25k_negotiation: deviceHS={high_speed}',
                                    compiler_options=('-I', str(vendor),
                                                      f'-Ptb_workstation_usb2_25k_negotiation.DEVICE_HIGH_SPEED={high_speed}'),
                                    timeout=180)

    def test_existing_25k_control_and_warm_reset(self):
        device, vendor, sources = device_core_sources()
        self.run_simulation('tb_usb2_hs_control', [
            device / 'sim/tb_usb2_hs_control.sv', *sources,
        ], 'PASS USB2 HS UTMI:', compiler_options=('-I', str(vendor)), timeout=90)


if __name__ == '__main__':
    unittest.main()
