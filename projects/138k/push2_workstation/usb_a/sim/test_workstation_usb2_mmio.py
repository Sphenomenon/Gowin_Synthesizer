#!/usr/bin/env python3
"""Native USB2 CPU boundary checks, separate from accepted workstation profiles."""

from pathlib import Path
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ElementTree

import test_workstation_ulpi_link as ulpi_regression


ROOT = ulpi_regression.ROOT
controller_sources = ulpi_regression.controller_sources
device_core_sources = ulpi_regression.device_core_sources


def mmio_sources():
    return [*controller_sources(), ROOT / 'rtl/usb2/workstation_usb2_cpu_bridge.sv',
            ROOT / 'rtl/usb2/workstation_usb2_host_mmio.sv']


class CpuBoundary(unittest.TestCase):
    run_simulation = ulpi_regression.PhysicalLink.run_simulation

    def test_live_reference_diagnostics_without_phy_clock(self):
        self.run_simulation('tb_workstation_usb2_mmio_clock', [
            *mmio_sources(), ROOT / 'sim/usb2/usb3300_register_model.sv',
            ROOT / 'sim/usb2/tb_workstation_usb2_mmio_clock.sv',
        ], 'PASS workstation_usb2_mmio_clock:')

    def test_first_party_driver_with_bounded_io_model(self):
        self.assertIsNotNone(shutil.which('gcc'), 'gcc is required for the driver test')
        source = ROOT / 'drivers/usb2/workstation_usb2_host.c'
        with tempfile.TemporaryDirectory(prefix='workstation-usb2-driver-') as directory:
            executable = Path(directory) / 'driver_test'
            compilation = subprocess.run([
                'gcc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-pedantic', '-fsanitize=address,undefined',
                '-I', str(source.parent), str(source), str(ROOT / 'sim/usb2/test_workstation_usb2_driver.c'),
                '-o', str(executable),
            ], text=True, capture_output=True, timeout=30)
            self.assertEqual(compilation.returncode, 0, compilation.stdout + compilation.stderr)
            execution = subprocess.run([str(executable)], text=True, capture_output=True, timeout=10)
            self.assertEqual(execution.returncode, 0, execution.stdout + execution.stderr)
            self.assertIn('PASS workstation_usb2_driver:', execution.stdout)
            print(execution.stdout.strip())

    def test_first_party_driver_compiles_for_workstation_riscv(self):
        sys.path.insert(0, str(ROOT / 'tools'))
        from stage_usb_firmware import compiler_prefix
        prefix = compiler_prefix()
        source = ROOT / 'drivers/usb2/workstation_usb2_host.c'
        with tempfile.TemporaryDirectory(prefix='workstation-usb2-driver-riscv-') as directory:
            compilation = subprocess.run([
                prefix + '-gcc', '-march=rv32i', '-mabi=ilp32', '-Os', '-ffreestanding', '-std=c11',
                '-Wall', '-Wextra', '-Werror', '-c', str(source), '-o', str(Path(directory) / 'host.o'),
            ], text=True, capture_output=True, timeout=30)
            self.assertEqual(compilation.returncode, 0, compilation.stdout + compilation.stderr)

    @unittest.skipUnless(shutil.which('gw_sh'), 'gw_sh is required for the target RAM-mapping check')
    def test_mmio_gowin_component_uses_four_block_rams(self):
        part = json.loads((ROOT / 'boards/custom_138k/pinout.json').read_text())['device']
        self.assertEqual(part, 'GW5AST-LV138PG484AC2/I1')
        with tempfile.TemporaryDirectory(prefix='workstation-usb2-mmio-gowin-') as directory:
            stage = Path(directory)
            project = ElementTree.Element('Project')
            ElementTree.SubElement(project, 'Template').text = 'FPGA'
            ElementTree.SubElement(project, 'Version').text = '5'
            ElementTree.SubElement(project, 'Device', name='GW5AST-138C', pn=part).text = 'gw5ast138c-006'
            files = ElementTree.SubElement(project, 'FileList')
            for source in mmio_sources():
                ElementTree.SubElement(files, 'File', path=str(source), type='file.verilog', enable='1')
            ElementTree.SubElement(files, 'File', path='mmio.sdc', type='file.sdc', enable='1')
            ElementTree.ElementTree(project).write(stage / 'mmio.gprj', encoding='UTF-8', xml_declaration=True)
            (stage / 'mmio.sdc').write_text(
                'create_clock -name cpu_48 -period 20.833333 [get_ports {clk_cpu}]\n'
                'create_clock -name reference_50 -period 20.000 [get_ports {clk_ref}]\n'
                'create_clock -name ulpi_60 -period 16.666667 [get_ports {clk_ulpi}]\n')
            (stage / 'mmio.tcl').write_text(
                'cd [file dirname [info script]]\nopen_project mmio.gprj\n'
                'set_option -top_module workstation_usb2_host_mmio\n'
                'set_option -output_base_name mmio_component\n'
                'set_option -verilog_std sysv2017\nset_option -timing_driven 1\nrun syn\n')
            synthesis = subprocess.run(['gw_sh', str(stage / 'mmio.tcl')], cwd=stage,
                                       text=True, capture_output=True, timeout=180)
            self.assertEqual(synthesis.returncode, 0, synthesis.stdout + synthesis.stderr)
            netlist = (stage / 'impl/gwsynthesis/mmio_component.vg').read_text()
            block_rams = re.findall(r'^\s*SDPB\s+\S+\s*\(', netlist, re.M)
            registers = re.findall(r'^\s*DFF[A-Z0-9_]*\s+\S+\s*\(', netlist, re.M)
            self.assertEqual(len(block_rams), 4, 'MAC and cross-clock TX/RX must remain four SDPB primitives')
            self.assertLess(len(registers), 2304, 'native MMIO component exceeded its register budget')
            print(f'PASS Gowin USB2 MMIO synthesis: {len(block_rams)} SDPB, {len(registers)} registers, no P&R or bitstream')

    def test_cpu_mmio_to_physical_ulpi_and_actual_25k(self):
        _, vendor, sources = device_core_sources()
        for high_speed in (1, 0):
            with self.subTest(high_speed=high_speed):
                self.run_simulation('tb_workstation_usb2_mac_25k', [
                    *mmio_sources(), ROOT / 'sim/usb2/usb3300_register_model.sv',
                    ROOT / 'sim/usb2/usb3300_packet_model.sv', ROOT / 'sim/usb2/usb3300_host_model.sv',
                    ROOT / 'sim/usb2/tb_workstation_usb2_mac_25k.sv', *sources,
                ], f'PASS workstation_usb2_mac_25k: HS={high_speed} native=1 mmio=1',
                    compiler_options=('-I', str(vendor), f'-Ptb_workstation_usb2_mac_25k.HIGH_SPEED={high_speed}',
                                      '-Ptb_workstation_usb2_mac_25k.NATIVE_PORT=1',
                                      '-Ptb_workstation_usb2_mac_25k.NATIVE_MMIO=1'), timeout=600)

    def test_dual_clock_packet_mailbox_and_cancellation(self):
        for half_period in (10417, 7353, 25000):
            with self.subTest(cpu_half_period_ps=half_period):
                self.run_simulation('tb_workstation_usb2_cpu_bridge', [
                    'rtl/usb2/workstation_usb2_cpu_bridge.sv', 'sim/usb2/tb_workstation_usb2_cpu_bridge.sv',
                ], 'PASS workstation_usb2_cpu_bridge:',
                    [f'-Ptb_workstation_usb2_cpu_bridge.CPU_HALF_PERIOD_PS={half_period}'])

    @unittest.skipUnless(shutil.which('yosys'), 'yosys is required for dual-clock RAM checks')
    def test_bridge_buffers_have_separate_synchronous_clocks(self):
        with tempfile.TemporaryDirectory(prefix='workstation-usb2-cdc-') as directory:
            preparation = subprocess.run([
                'yosys', '-Q', '-T', '-p',
                f'read_verilog -sv "{ROOT / "rtl/usb2/workstation_usb2_cpu_bridge.sv"}"; '
                'hierarchy -check -top workstation_usb2_cpu_bridge; proc; opt; memory_dff; '
                'memory_collect; opt_clean; check -assert; write_json memories.json',
            ], cwd=directory, text=True, capture_output=True, timeout=30)
            self.assertEqual(preparation.returncode, 0, preparation.stdout + preparation.stderr)
            module = json.loads((Path(directory) / 'memories.json').read_text())['modules']['workstation_usb2_cpu_bridge']
            memories = {name: cell for name, cell in module['cells'].items() if cell['type'] == '$mem_v2'}
            self.assertEqual(set(memories), {'transmit_memory', 'receive_memory'})
            for name, write_clock, read_clock in (('transmit_memory', 'clk_cpu', 'clk_ulpi'),
                                                  ('receive_memory', 'clk_ulpi', 'clk_cpu')):
                with self.subTest(memory=name):
                    cell = memories[name]
                    for parameter, expected in (('SIZE', 512), ('WIDTH', 8), ('RD_PORTS', 1), ('WR_PORTS', 1),
                                                ('RD_CLK_ENABLE', 1), ('WR_CLK_ENABLE', 1)):
                        self.assertEqual(int(cell['parameters'][parameter], 2), expected, parameter)
                    for port, clock in (('RD_CLK', read_clock), ('WR_CLK', write_clock)):
                        self.assertEqual(cell['connections'][port], module['ports'][clock]['bits'])


if __name__ == '__main__':
    unittest.main()
