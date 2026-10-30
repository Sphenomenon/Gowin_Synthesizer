"""Prove the native memory mapping preserves the complete delay FIFO contract."""

from pathlib import Path
import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ElementTree


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_baselines import load_baseline
from tools.workstation_synthesis_netlist import SynthesisNetlist
SOURCE = ROOT / 'rtl/music/music_async_fifo.sv'
BENCH = ROOT / 'sim/audio/tb_workstation_delay_fifo_storage.sv'


class DelayFifoStorage(unittest.TestCase):
    def simulate(self, directory, address_bits, write_half, read_half, extra=()):
        binary = directory / ('simulation-' + str(address_bits) + '-' + str(write_half))
        command = ['iverilog', '-g2012', '-s', 'tb', f'-Ptb.ADDRESS_BITS={address_bits}',
                   f'-Ptb.WRITE_HALF={write_half}', f'-Ptb.READ_HALF={read_half}',
                   '-o', str(binary), *map(str, extra), str(SOURCE), str(BENCH)]
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=120)
        self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
        executed = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=120)
        self.assertEqual(executed.returncode, 0, executed.stdout + executed.stderr)
        self.assertIn('PASS FIFO storage:', executed.stdout)

    def test_both_clock_ratios_full_capacity_wrap_stall_and_reset(self):
        with tempfile.TemporaryDirectory(prefix='workstation-delay-fifo-') as temporary:
            directory = Path(temporary)
            for address_bits in (8, 9):
                for write_half, read_half in ((5, 7.3), (11.1, 4)):
                    with self.subTest(address_bits=address_bits, write_half=write_half):
                        self.simulate(directory, address_bits, write_half, read_half)

    @unittest.skipUnless(shutil.which('gw_sh'), 'Gowin is required for mapped-memory verification')
    def test_actual_gowin_block_ram_netlist_is_cycle_equivalent(self):
        with tempfile.TemporaryDirectory(prefix='workstation-delay-bram-') as temporary:
            directory = Path(temporary)
            wrapper = directory / 'probe.sv'
            wrapper.write_text('''module workstation_fifo_bram_probe (
input wire write_clk,read_clk,reset_n,write_valid,read_ready,
input wire [64:0] write_data,
output wire write_ready,read_valid,output wire [64:0] read_data);
defparam fifo.RAM_STYLE="block_ram";
music_async_fifo #(.WIDTH(65),.ADDRESS_BITS(9)) fifo (
write_clk,reset_n,write_valid,write_ready,write_data,
read_clk,reset_n,read_valid,read_ready,read_data);
endmodule
''')
            script = directory / 'run.tcl'
            script.write_text(f'''cd {{{directory}}}
set_device GW5AST-LV138PG484AC2/I1 -device_version C
set_option -synthesis_tool gowinsynthesis
set_option -top_module workstation_fifo_bram_probe
set_option -output_base_name workstation_fifo_bram_probe
set_option -verilog_std sysv2017
add_file -type verilog {{{SOURCE}}}
add_file -type verilog {{{wrapper}}}
run syn
''')
            synthesized = subprocess.run(['gw_sh', str(script)], capture_output=True, text=True, timeout=120)
            self.assertEqual(synthesized.returncode, 0, synthesized.stdout + synthesized.stderr)
            base = directory / 'impl/gwsynthesis/workstation_fifo_bram_probe'
            resources = ElementTree.parse(base.with_name(base.name + '_syn_rsc.xml')).getroot()
            self.assertEqual(resources.get('T_Bsram'), '4(0)')
            self.assertIsNone(resources.get('T_Ssram'))
            mapped_text, renamed = re.subn(
                r'(?m)^([ \t]*(?:module[ \t]+)?)music_async_fifo(?=[ \t]*(?:\(|[A-Za-z_$][\w$]*[ \t]*\())',
                r'\1mapped_music_async_fifo', base.with_suffix('.vg').read_text())
            self.assertEqual(renamed, 2, 'mapped FIFO module and its wrapper instance must both be renamed')
            mapped = directory / 'mapped.vg'
            mapped.write_text(mapped_text)
            locator = directory / 'gowin_paths.py'
            locator.write_bytes(load_baseline(ROOT, 'resource_rework_route0').read_bytes('scripts/gowin_paths.py'))
            spec = importlib.util.spec_from_file_location('fifo_storage_gowin_paths', locator)
            paths = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(paths)
            primitives = paths.gowin_simlib() / 'prim_sim.v'
            self.assertTrue(primitives.is_file(), 'installed official GW5A simulation library missing')
            official = primitives.read_text()
            parsed = SynthesisNetlist(base.with_suffix('.vg').read_text(), 'workstation_fifo_bram_probe')
            kinds = {cell['kind'] for cell in parsed.cells.values()}
            helpers = official[:official.index('module LUT1')]
            models = [helpers]
            for name in sorted(kinds | {'GSR'}):
                if name.startswith('MUX'):
                    self.assertRegex(helpers, r'module\s+' + re.escape(name) + r'\s*\(')
                    continue
                match = re.search(r'^module\s+' + re.escape(name) + r'\s*\(.*?^endmodule\b[^\n]*', official, re.M | re.S)
                self.assertTrue(match or name in parsed.modules, 'official primitive model missing: ' + name)
                if match:
                    models.append(match[0])
            primitive_models = directory / 'official_models.v'
            primitive_models.write_text('`timescale 1ns/1ps\n' + '\n\n'.join(models) + '\n')
            for write_half, read_half in ((5, 7.3), (11.1, 4)):
                with self.subTest(write_half=write_half):
                    self.simulate(directory, 9, write_half, read_half,
                                  ('-DMAPPED_FIFO', mapped, primitive_models))


if __name__ == '__main__':
    unittest.main()
