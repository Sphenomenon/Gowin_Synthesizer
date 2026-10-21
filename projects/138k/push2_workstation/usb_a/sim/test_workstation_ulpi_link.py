#!/usr/bin/env python3
"""ULPI physical-bus regression; no FPGA, private staging or external model."""

from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ElementTree


ROOT = Path(__file__).resolve().parents[1]


def controller_sources():
    return [ROOT / 'rtl/usb2' / name for name in (
        'workstation_ulpi_link.sv', 'workstation_ulpi_supervisor.sv',
        'workstation_usb2_host_controller.sv', 'workstation_usb2_host_mac.sv',
        'workstation_usb2_host_phy.sv', 'workstation_usb2_host_port.sv',
        'workstation_usb3300_host_init.sv', 'workstation_usb3300_host_link.sv',
    )]


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

    def test_host_mac_transactions_and_failures(self):
        for high_speed in (1, 0):
            with self.subTest(high_speed=high_speed):
                self.run_simulation('tb_workstation_usb2_host_mac', [
                    'rtl/usb2/workstation_usb2_host_mac.sv',
                    'sim/usb2/tb_workstation_usb2_host_mac.sv',
                ], f'PASS workstation_usb2_host_mac: HS={high_speed}',
                    compiler_options=(f'-Ptb_workstation_usb2_host_mac.HIGH_SPEED={high_speed}',))

    def test_host_mac_with_actual_25k_packets(self):
        _, vendor, sources = device_core_sources()
        for high_speed in (1, 0):
            with self.subTest(high_speed=high_speed):
                self.run_simulation('tb_workstation_usb2_mac_25k', [
                    ROOT / 'rtl/usb2/workstation_usb2_host_mac.sv',
                    ROOT / 'sim/usb2/tb_workstation_usb2_mac_25k.sv', *sources,
                ], f'PASS workstation_usb2_mac_25k: HS={high_speed}',
                    compiler_options=('-I', str(vendor), f'-Ptb_workstation_usb2_mac_25k.HIGH_SPEED={high_speed}'), timeout=90)

    def test_host_mac_on_physical_ulpi(self):
        for high_speed in (1, 0):
            with self.subTest(high_speed=high_speed):
                self.run_simulation('tb_workstation_usb2_host_mac', [
                    'rtl/usb2/workstation_usb2_host_mac.sv', 'rtl/usb2/workstation_ulpi_link.sv',
                    'sim/usb2/usb3300_packet_model.sv', 'sim/usb2/tb_workstation_usb2_host_mac.sv',
                ], f'PASS workstation_usb2_host_mac: HS={high_speed} physical=1',
                    compiler_options=(f'-Ptb_workstation_usb2_host_mac.HIGH_SPEED={high_speed}',
                                      '-Ptb_workstation_usb2_host_mac.PHYSICAL_LINK=1'))

    def test_native_host_controller_with_actual_25k(self):
        _, vendor, sources = device_core_sources()
        for high_speed in (1, 0):
            with self.subTest(high_speed=high_speed):
                self.run_simulation('tb_workstation_usb2_mac_25k', [
                    *controller_sources(),
                    ROOT / 'sim/usb2/usb3300_register_model.sv', ROOT / 'sim/usb2/usb3300_packet_model.sv',
                    ROOT / 'sim/usb2/usb3300_host_model.sv', ROOT / 'sim/usb2/tb_workstation_usb2_mac_25k.sv', *sources,
                ], f'PASS workstation_usb2_mac_25k: HS={high_speed} native=1',
                    compiler_options=('-I', str(vendor), f'-Ptb_workstation_usb2_mac_25k.HIGH_SPEED={high_speed}',
                                      '-Ptb_workstation_usb2_mac_25k.NATIVE_PORT=1'), timeout=600)

    @unittest.skipUnless(shutil.which('gw_sh'), 'gw_sh is required for the Gowin component-synthesis check')
    def test_controller_gowin_component_synthesis_uses_block_ram(self):
        part = json.loads((ROOT / 'boards/custom_138k/pinout.json').read_text())['device']
        self.assertEqual(part, 'GW5AST-LV138PG484AC2/I1')
        with tempfile.TemporaryDirectory(prefix='workstation-usb2-gowin-') as directory:
            stage = Path(directory)
            project = ElementTree.Element('Project')
            ElementTree.SubElement(project, 'Template').text = 'FPGA'
            ElementTree.SubElement(project, 'Version').text = '5'
            ElementTree.SubElement(project, 'Device', name='GW5AST-138C', pn=part).text = 'gw5ast138c-006'
            files = ElementTree.SubElement(project, 'FileList')
            for source in controller_sources():
                ElementTree.SubElement(files, 'File', path=str(source), type='file.verilog', enable='1')
            ElementTree.SubElement(files, 'File', path='controller.sdc', type='file.sdc', enable='1')
            ElementTree.ElementTree(project).write(stage / 'controller.gprj', encoding='UTF-8', xml_declaration=True)
            (stage / 'controller.sdc').write_text(
                'create_clock -name reference_50 -period 20.000 [get_ports {clk_ref}]\n'
                'create_clock -name ulpi_60 -period 16.666667 [get_ports {clk_ulpi}]\n')
            (stage / 'controller.tcl').write_text(
                'cd [file dirname [info script]]\nopen_project controller.gprj\n'
                'set_option -top_module workstation_usb2_host_controller\n'
                'set_option -output_base_name controller_component\n'
                'set_option -verilog_std sysv2017\nset_option -timing_driven 1\nrun syn\n')
            synthesis = subprocess.run(['gw_sh', str(stage / 'controller.tcl')], cwd=stage,
                                       text=True, capture_output=True, timeout=180)
            self.assertEqual(synthesis.returncode, 0, synthesis.stdout + synthesis.stderr)
            netlist = (stage / 'impl/gwsynthesis/controller_component.vg').read_text()
            block_rams = re.findall(r'^\s*SDPB\s+\S+\s*\(', netlist, re.M)
            registers = re.findall(r'^\s*DFF[A-Z0-9_]*\s+\S+\s*\(', netlist, re.M)
            self.assertEqual(len(block_rams), 2, 'TX and RX buffers must remain two SDPB primitives')
            self.assertLess(len(registers), 2048, 'standalone controller exceeded its register budget')
            print(f'PASS Gowin USB2 controller synthesis: {len(block_rams)} SDPB, {len(registers)} registers, no P&R or bitstream')

    @unittest.skipUnless(shutil.which('yosys'), 'yosys is required for the memory-inference check')
    def test_host_mac_buffers_keep_synchronous_memory_ports(self):
        source = ROOT / 'rtl/usb2/workstation_usb2_host_mac.sv'
        with tempfile.TemporaryDirectory(prefix='workstation-usb2-memory-') as directory:
            preparation = subprocess.run([
                'yosys', '-Q', '-T', '-p',
                f'read_verilog -sv "{source}"; hierarchy -check -top workstation_usb2_host_mac; '
                'proc; opt; memory_dff; memory_collect; opt_clean; check -assert; write_json memories.json',
            ], cwd=directory, text=True, capture_output=True, timeout=30)
            self.assertEqual(preparation.returncode, 0, preparation.stdout + preparation.stderr)
            module = json.loads((Path(directory) / 'memories.json').read_text())['modules']['workstation_usb2_host_mac']
            memories = {name: cell for name, cell in module['cells'].items() if cell['type'] == '$mem_v2'}
            self.assertEqual(set(memories), {'transmit_buffer', 'receive_buffer'})
            for name, cell in memories.items():
                with self.subTest(memory=name):
                    for parameter, expected in (('SIZE', 512), ('WIDTH', 8), ('RD_PORTS', 1), ('WR_PORTS', 1),
                                                ('RD_CLK_ENABLE', 1), ('WR_CLK_ENABLE', 1)):
                        self.assertEqual(int(cell['parameters'][parameter], 2), expected, parameter)
                    for port in ('RD_CLK', 'WR_CLK'):
                        self.assertEqual(cell['connections'][port], module['ports']['clk_ulpi']['bits'])


if __name__ == '__main__':
    unittest.main()
