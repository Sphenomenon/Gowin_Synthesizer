#!/usr/bin/env python3
"""Exercise physical ROM selection and actual cold images beyond the old 16 KiB."""
from pathlib import Path
import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]
from tools import stage_ae350_firmware as staging
from tools import workstation_ae350_memory as memory
from tools import workstation_profile as profile
from ae350_rv32_startup import StartupCpu, ROM, ILM


PORTS = '''.rom_clk(clk),.rom_reset_n(reset_n),.rom_address(rom_address),
.rom_transfer(rom_transfer),.rom_data(rom_data{suffix}),.fetch_count(fetch_count{suffix}),
.last_fetch(last_fetch{suffix}),.ram_clk(clk),.ram_reset_n(reset_n),.ram_address(ram_address),
.ram_transfer(ram_transfer),.ram_size(ram_size),.ram_write(ram_write),
.ram_write_data(ram_write_data),.ram_read_data(ram_read_data{suffix})'''
SIGNALS = '''reg clk=0,reset_n=0; always #5 clk=~clk;
reg [31:0] rom_address=0,ram_address=0;
reg [1:0] rom_transfer=0,ram_transfer=0;
reg [2:0] ram_size=0;reg ram_write=0;reg [63:0] ram_write_data=0;
wire [31:0] rom_data,fetch_count,last_fetch;
wire [63:0] ram_read_data;
integer i;'''


class BootStorageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def simulate(self, testbench, files):
        (self.directory / 'tb.sv').write_text(testbench)
        subprocess.run(['iverilog', '-g2012', '-s', 'tb', '-o', 'sim', 'tb.sv', *files],
                       cwd=self.directory, check=True, capture_output=True, text=True)
        run = subprocess.run(['vvp', 'sim'], cwd=self.directory, check=True,
                             capture_output=True, text=True, timeout=30)
        self.assertIn('PASS', run.stdout)

    def image(self, size):
        firmware = self.directory / 'firmware'
        firmware.mkdir(exist_ok=True)
        (firmware / 'boot.mem').write_text(''.join(f'{i ^ 0x91357248:08x}\n' for i in range(size // 4)))

    def test_native_16k_matches_locked_rom_and_all_scratch_ram_transactions(self):
        self.image(16384)
        baseline = staging.load_baseline(ROOT, 'resource_rework_route0')
        reference = baseline.read_bytes(memory.PARENT).decode()
        self.assertEqual(reference.count('module gw138k_boot_memory'), 1)
        (self.directory / 'reference.sv').write_text(reference.replace('module gw138k_boot_memory', 'module reference_boot_memory'))
        tb = 'module tb;\n' + SIGNALS + '''
wire [31:0] rom_data_ref,fetch_count_ref,last_fetch_ref;wire [63:0] ram_read_data_ref;
gw138k_boot_memory #(.ROM_BYTES(16384)) dut(''' + PORTS.format(suffix='') + ''');
reference_boot_memory refdut(''' + PORTS.format(suffix='_ref') + ''');
task check;begin
  @(posedge clk);#1;
  if ({rom_data,fetch_count,last_fetch,ram_read_data} !==
      {rom_data_ref,fetch_count_ref,last_fetch_ref,ram_read_data_ref}) $fatal(1,"ABI behavior differs");
end endtask
initial begin
  for(i=0;i<1024;i=i+1) begin dut.ram[i]=64'h9037a555ea321b08^i;refdut.ram[i]=64'h9037a555ea321b08^i;end
  check();@(negedge clk);reset_n=1;
  for(i=0;i<4096;i=i+1) begin
    @(negedge clk);rom_transfer=2;rom_address=32'h80000000+i*4;check();
  end
  for(i=0;i<4000;i=i+1) begin
    @(negedge clk);rom_address=$urandom;rom_transfer=$urandom;
    ram_address=$urandom_range(0,4095)*8+$urandom_range(0,7);
    ram_transfer=$urandom;ram_size=$urandom;ram_write=$urandom;
    ram_write_data={$urandom,$urandom};reset_n=(i%47!=0);check();
  end
  @(negedge clk);reset_n=0;check();@(negedge clk);reset_n=1;check();
  $display("PASS native16k reference equivalence, ROM4096 and RAM4000 transactions");$finish;
end endmodule'''
        self.simulate(tb, ['reference.sv', str(ROOT / memory.SOURCE)])

    def test_64k_upper_addresses_do_not_alias_and_outside_returns_break(self):
        self.image(65536)
        tb = 'module tb;\n' + SIGNALS + '\ngw138k_boot_memory dut(' + PORTS.format(suffix='') + ''');
task fetch(input [31:0] address,input [31:0] expected);begin
  @(negedge clk);rom_transfer=2;rom_address=address;
  @(posedge clk);#1;if(rom_data!==expected)$fatal(1,"ROM boundary %h got %h expected %h",address,rom_data,expected);
end endtask
initial begin
  @(negedge clk);reset_n=1;
  for(i=0;i<16384;i=i+1) fetch(32'h80000000+i*4,i^32'h91357248);
  fetch(32'h80010000,32'h00100073);fetch(32'h7ffffffc,32'h00100073);
  fetch(32'h80014000,32'h00100073);fetch(32'h90000000,32'h00100073);
  if(fetch_count!==16388 || last_fetch!==32'h90000000)$fatal(1,"fetch diagnostics changed");
  @(negedge clk);rom_transfer=0;rom_address=32'h80000000;
  @(posedge clk);#1;if(rom_data!==32'h00100073 || fetch_count!==16388)$fatal(1,"idle transfer changed output");
  $display("PASS all16384 ROM words, upper boundaries, idle and counters");$finish;
end endmodule'''
        self.simulate(tb, [str(ROOT / memory.SOURCE)])

    def test_actual_46k_cold_image_requires_64k_storage_and_copies_upper_bytes(self):
        source = self.directory / 'source'
        shutil.copytree(ROOT / 'firmware/ae350', source / 'firmware/ae350')
        code = source / 'firmware/ae350/ui_runtime.c'
        code.write_text(code.read_text() + '\n__attribute__((used)) const unsigned capacity_payload[8192] = {[0]=0xA1386401,[8191]=0xA1386402};\n')
        baseline = staging.load_baseline(ROOT, 'resource_rework_route0')
        with patch.object(staging, 'load_baseline', return_value=baseline):
            with self.assertRaises(subprocess.CalledProcessError):
                staging.stage_ae350_firmware(source, self.directory / 'too-small',
                    recording_api=True, memory_profile=memory.LOCAL_PROFILE)
            output = self.directory / 'expanded'
            result = staging.stage_ae350_firmware(source, output, recording_api=True,
                memory_profile=memory.LOCAL_PROFILE, boot_rom_bytes=65536)
        self.assertGreater(result['capacity']['binary_bytes'], 45000)
        self.assertEqual(result['capacity']['rom_capacity_bytes'], 65536)
        image = staging.decode_rom(output / 'boot.mem', 65536)
        self.assertEqual(image, (output / 'firmware.bin').read_bytes().ljust(65536, b'\0'))
        self.assertEqual(len(image), 65536)
        symbols = result['capacity']['symbols']
        self.assertGreater(symbols['__image_end'], ROM + 16384)
        cpu = StartupCpu(image, symbols)
        self.assertEqual(cpu.run(), 'services_main')
        self.assertEqual(bytes(cpu.ilm[:symbols['__ilm_end'] - ILM]),
            image[symbols['__ilm_load_start'] - ROM:symbols['__data_load_start'] - ROM])
        self.assertIn(bytes.fromhex('026438a1'), cpu.ilm)
        self.assertEqual(result['reference_rom']['differing_words_scope_bytes'], 16384)
        self.assertFalse(result['cold_boot']['hardware_acceptance'])
        code.write_text(code.read_text() + '\n__attribute__((used)) const unsigned overflow_payload[8192] = {0xA138FFFF};\n')
        with patch.object(staging, 'load_baseline', return_value=baseline), self.assertRaises(subprocess.CalledProcessError):
            staging.stage_ae350_firmware(source, self.directory / 'runtime-overflow', recording_api=True,
                memory_profile=memory.LOCAL_PROFILE, boot_rom_bytes=65536)

    def test_profile_contract_rejects_capacity_owner_and_platform_mismatch(self):
        config = profile.specification(profile.LOCAL_BOOT64_NAME)['configuration']
        self.assertEqual(memory.selection(config), dict(memory_profile=memory.LOCAL_PROFILE, boot_rom_bytes=65536))
        self.assertEqual(memory.selection({}), dict(memory_profile=memory.DEFAULT_PROFILE, boot_rom_bytes=16384))
        for changed in ({'ae350_memory_profile': memory.LOCAL_PROFILE}, {'ae350_boot_rom_bytes': 65536},
                        {'ae350_boot_rom_bytes': 32768}):
            with self.assertRaises(ValueError):memory.selection(changed)
        entries = ElementTree.Element('Project');files = ElementTree.SubElement(entries,'FileList')
        ElementTree.SubElement(files,'File',path=memory.PARENT,enable='0')
        ElementTree.SubElement(files,'File',path=memory.SOURCE,enable='1')
        project = self.directory / 'Prj1.gprj';ElementTree.ElementTree(entries).write(project)
        self.image(65536)
        build = dict(memory_profile=memory.LOCAL_PROFILE, capacity=dict(rom_capacity_bytes=65536),
            cold_boot=dict(image_capacity_bytes=65536,image_storage='explicit_64k_pl_boot_rom',
                cache_policy='reject_enabled_i_or_d_cache_on_entry'))
        sha = lambda path:memory.PLATFORM[Path(path).relative_to(self.directory).as_posix()]
        selected = memory.verify_prepared(self.directory,build,config,sha)
        self.assertEqual(selected['physical_rom_source'],memory.SOURCE)
        bad = copy.deepcopy(build);bad['capacity']['rom_capacity_bytes']=16384
        with self.assertRaises(ValueError):memory.verify_prepared(self.directory,bad,config,sha)
        with self.assertRaises(ValueError):memory.verify_prepared(self.directory,build,config,lambda path:'0'*64)
        files[0].set('enable','1');ElementTree.ElementTree(entries).write(project)
        with self.assertRaises(ValueError):memory.verify_prepared(self.directory,build,config,sha)


if __name__ == '__main__':
    unittest.main()
