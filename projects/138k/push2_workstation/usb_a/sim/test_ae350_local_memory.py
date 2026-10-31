#!/usr/bin/env python3
"""Run generated RV32 cold-loader instructions and reject broken boundaries."""
from pathlib import Path
import copy
import json
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]
from tools import stage_ae350_firmware as staging
from tools.ae350_local_memory import local_memory_report, verify_elf_image, call_chain_report
from ae350_rv32_startup import StartupCpu, ModelError, ROM, ILM, DLM

BOOT_ROM_BYTES = 65536  # The explicit whole-profile cold storage; 16K rejection is tested separately.


class LocalMemoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temp.name)
        cls.prefix = staging.compiler_prefix()
        cls.output = cls.directory / 'local'
        cls.result = staging.stage_ae350_firmware(ROOT, cls.output, cls.prefix,
                                                memory_profile='ilm64k_dlm64k', recording_api=True,
                                                boot_rom_bytes=BOOT_ROM_BYTES)
        cls.symbols = cls.result['capacity']['symbols']
        cls.image = staging.decode_rom(cls.output / 'boot.mem', BOOT_ROM_BYTES)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def cpu(self, **kwargs):
        return StartupCpu(self.image, self.symbols, **kwargs)

    def assert_failed(self, cpu, reason=None, cause=None):
        self.assertEqual(cpu.run(), 'halt')
        self.assertEqual(cpu.diagnostics.get(4), 0x4641494C)
        if reason is not None:
            self.assertEqual(cpu.diagnostics.get(8), reason)
        if cause is not None:
            self.assertEqual(cpu.diagnostics.get(12), cause)
            self.assertEqual(cpu.diagnostics.get(16), cpu.traps[-1]['pc'])
        self.assertFalse(cpu.executed_ilm)

    def test_actual_binary_copies_both_spans_and_enters_ilm_after_fence(self):
        cpu = self.cpu()
        self.assertEqual(cpu.run(), 'services_main')
        self.assertTrue(cpu.executed_ilm)
        self.assertTrue(cpu.fenced)
        self.assertEqual(cpu.csrs[0x304], 0)
        self.assertEqual(cpu.csrs[0x305], self.symbols['local_trap'])
        self.assertEqual(cpu.diagnostics[4], 0x50415353)
        s = self.symbols
        self.assertEqual(bytes(cpu.ilm[:s['__ilm_end'] - ILM]),
                         self.image[s['__ilm_load_start'] - ROM:s['__data_load_start'] - ROM])
        self.assertEqual(bytes(cpu.dlm[s['__data_start'] - DLM:s['__data_end'] - DLM]),
                         self.image[s['__data_load_start'] - ROM:s['__image_end'] - ROM])
        self.assertEqual(bytes(cpu.dlm[s['__bss_start'] - DLM:s['__bss_end'] - DLM]),
                         b'\0' * (s['__bss_end'] - s['__bss_start']))
        self.assertEqual(cpu.registers[2], s['__stack_top'])
        self.assertEqual(cpu.min_sp, s['__stack_top'] - 16)
        self.assertEqual(cpu.dlm[s['__stack_bottom'] - DLM:s['__stack_bottom'] - DLM + 4],
                         bytes.fromhex('a5555aa5'))

    def test_reset_reinitializes_dirty_local_memory_and_preserves_control_bits(self):
        cpu = self.cpu(csr_overrides={0x7C0: ILM | 0x19, 0x7C1: DLM | 0x19})
        cpu.ilm[:] = bytes([0xCC]) * 65536
        cpu.dlm[:] = bytes([0xDD]) * 65536
        self.assertEqual(cpu.run(), 'services_main')
        self.assertEqual(cpu.csrs[0x7C0], ILM | 0x19)
        self.assertEqual(cpu.csrs[0x7C1], DLM | 0x19)

    def test_wrong_geometry_or_absent_local_memory_and_cache_enabled_fail(self):
        for csr in (0xFC0, 0xFC1):
            for value in (0, 0x439ADA & ~(7 << 12), (0x439ADA & ~(31 << 15)) | (6 << 15)):
                with self.subTest(csr=csr, value=value):
                    self.assert_failed(self.cpu(csr_overrides={csr: value}), reason=2)
        for enabled in (1, 2, 3):
            self.assert_failed(self.cpu(csr_overrides={0x7CA: enabled}), reason=1)

    def test_unsupported_csr_traps_to_rom_without_stack(self):
        for csr in (0xFC0, 0xFC1, 0x7C0, 0x7C1, 0x7CA):
            with self.subTest(csr=csr):
                cpu = self.cpu(unsupported_csrs=[csr])
                self.assert_failed(cpu, reason=0x80, cause=2)
                self.assertIsNone(cpu.min_sp)

    def test_enable_readback_or_memory_bus_or_rom_data_failure_stops_before_execution(self):
        for csr in (0x7C0, 0x7C1):
            self.assert_failed(self.cpu(stuck_enable=[csr]), reason=3)
        self.assert_failed(self.cpu(writable=False), reason=0x80, cause=7)
        self.assert_failed(self.cpu(rom_readable=False), reason=0x80, cause=5)

    def test_copy_final_word_corruption_is_detected_for_ilm_and_data(self):
        for address, reason in ((self.symbols['__ilm_end'] - 4, 5), (self.symbols['__data_end'] - 4, 6)):
            with self.subTest(address=address):
                self.assert_failed(self.cpu(corrupt_copy_address=address), reason=reason)

    def test_actual_bss_loop_clears_late_poison_and_stack_branch_target_are_checked(self):
        cpu = self.cpu()
        while cpu.pc != self.symbols['local_clear_bss']:
            cpu.step()
        start = self.symbols['__bss_start'] - DLM
        end = self.symbols['__bss_end'] - DLM
        cpu.dlm[start:end] = b'\xDD' * (end - start)
        self.assertEqual(cpu.run(), 'services_main')
        self.assertEqual(cpu.dlm[start:end], b'\0' * (end - start))
        cpu = self.cpu()
        while cpu.pc != self.symbols['local_enter_ilm']:
            cpu.step()
        self.assertEqual(cpu.registers[5], self.symbols['local_memory_entry'])
        cpu.registers[5] = 0xDEAD0000
        self.assert_failed(cpu, reason=0x80, cause=1)

    def test_unknown_opcode_is_never_silently_accepted(self):
        cpu = self.cpu()
        cpu.image[:4] = bytes.fromhex('ffffffff')
        with self.assertRaisesRegex(ModelError, 'unsupported RV32'):
            cpu.run()

    def test_missing_instruction_fence_and_stack_access_escape_fail_closed(self):
        cpu = self.cpu()
        fence = bytes.fromhex('0f100000')
        self.assertEqual(cpu.image[:self.symbols['__ilm_load_start'] - ROM].count(fence), 1)
        offset = cpu.image.index(fence)
        cpu.image[offset:offset + 4] = bytes.fromhex('13000000')  # Actual instruction mutation: NOP.
        with self.assertRaisesRegex(ModelError, 'before fence.i'):
            cpu.run()
        cpu = self.cpu()
        while cpu.registers[2] != self.symbols['__stack_top'] - 16:
            cpu.step()
        cpu.registers[2] = self.symbols['__stack_bottom'] - 4
        with self.assertRaisesRegex(ModelError, 'stack access escaped'):
            cpu.step()

    def test_elf_binary_rom_map_and_capacity_agree_and_tampering_fails(self):
        j = self.result
        self.assertTrue(j['elf_image_validation']['binary_reconstructed'])
        self.assertEqual(self.image, (self.output / 'firmware.bin').read_bytes().ljust(BOOT_ROM_BYTES, b'\0'))
        self.assertEqual(j['capacity']['heap_bytes'], 0)
        self.assertEqual(j['capacity']['stack_capacity_bytes'], 16384)
        self.assertLess(j['capacity']['binary_bytes'], BOOT_ROM_BYTES)
        binary = bytearray((self.output / 'firmware.bin').read_bytes())
        binary[-1] ^= 1
        with self.assertRaisesRegex(ValueError, 'reconstruct'):
            verify_elf_image(self.output / 'firmware.elf', bytes(binary), self.symbols, BOOT_ROM_BYTES)
        symbols_text = (self.output / 'firmware.nm').read_text()
        for old, new in (('a0210000', 'a0220000'), ('80000000', '80000004')):
            with self.assertRaises(ValueError):
                local_memory_report((self.output / 'firmware.size').read_text(),
                                    symbols_text.replace(old, new), j['capacity']['binary_bytes'], BOOT_ROM_BYTES)
        with self.assertRaises(ValueError):
            local_memory_report((self.output / 'firmware.size').read_text(), symbols_text,
                                BOOT_ROM_BYTES + 1, BOOT_ROM_BYTES)

    def test_call_chain_is_conservative_and_rejects_unknown_dynamic_recursive_and_machine_calls(self):
        j = self.result
        self.assertTrue(j['call_chain_stack']['verified'])
        self.assertGreater(j['call_chain_stack']['conservative_peak_bytes'],
                           max(f['bytes'] for f in j['compiler_stack_frames']
                               if f['function'].split(':', 3)[-1] in j['call_chain_stack']['reachable_functions']))
        self.assertFalse(j['call_chain_stack']['hardware_watermark_verified'])
        for case in ('unknown', 'dynamic', 'recursive', 'machine', 'missing_edge'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                target = Path(temp)
                for source in self.output.glob('*.ci'):
                    shutil.copyfile(source, target / source.name)
                frames = copy.deepcopy(j['compiler_stack_frames'])
                disassembly = (self.output / 'firmware.dis').read_text()
                graph = target / 'ui_main.ci'
                if case == 'dynamic':
                    next(f for f in frames if f['function'].endswith(':services_main'))['kind'] = 'dynamic'
                elif case == 'machine':
                    disassembly += '\na0000000 <services_main>:\na0000000: 000280e7 jalr t0\n'
                elif case == 'missing_edge':
                    graph.write_text('\n'.join(line for line in graph.read_text().splitlines()
                                               if 'targetname: "ui_render_rows"' not in line))
                else:
                    child = 'unknown_callback' if case == 'unknown' else 'services_main'
                    graph.write_text(graph.read_text() + '\nedge: { sourcename: "services_main" targetname: "' + child + '" }\n')
                with self.assertRaises(ValueError):
                    call_chain_report(target, frames, disassembly, 16384)

    def test_default_rom_is_byte_identical_with_original_startup_and_variant_is_deterministic(self):
        baseline = staging.load_baseline(ROOT, 'resource_rework_route0')
        original_root = self.directory / 'original-source'
        shutil.copytree(ROOT / 'firmware/ae350', original_root / 'firmware/ae350')
        (original_root / 'firmware/ae350/start.S').write_bytes(baseline.read_bytes('firmware/start.S'))
        # Baseline resolver reads locked inputs in ROOT; only maintained start differs.
        from unittest.mock import patch
        with patch.object(staging, 'load_baseline', return_value=baseline):
            original = staging.stage_ae350_firmware(original_root, self.directory / 'original', self.prefix)
        default = staging.stage_ae350_firmware(ROOT, self.directory / 'default', self.prefix)
        self.assertEqual(original['rom_sha256'], default['rom_sha256'])
        self.assertEqual(default['memory_profile'], 'pl16k_8k')
        self.assertNotIn('cold_boot', default)
        self.assertNotIn('firmware/ae350/start_ilm_dlm.inc', default['input_sha256'])
        repeated = staging.stage_ae350_firmware(ROOT, self.directory / 'repeated', self.prefix,
                                               memory_profile='ilm64k_dlm64k', recording_api=True,
                                               boot_rom_bytes=BOOT_ROM_BYTES)
        for key in ('elf_sha256', 'binary_sha256', 'rom_sha256'):
            self.assertEqual(self.result[key], repeated[key])


class CompilerCloneIdentityTest(unittest.TestCase):
    def test_mixed_clone_suffix_resolves_only_exact_unique_gcc_title(self):
        clone = 'revoke.part.0.constprop.0.isra.0'
        label = 'revoke.part.0.constprop.isra'
        frames = [dict(function='test.c:1:1:services_main', bytes=16, kind='static'),
                  dict(function='test.c:2:1:' + label, bytes=32, kind='static')]
        disassembly = ('a0000000 <services_main>:\n'
                       'a0000000: 008000ef jal a0000008 <' + clone + '>\n'
                       'a0000004: 00008067 ret\n'
                       'a0000008 <' + clone + '>:\n'
                       'a0000008: 00008067 ret\n')
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            graph = out / 'fixture.ci'
            graph.write_text('node: { title: "services_main" label: "services_main\\n" }\n'
                             'node: { title: "test.c:' + clone + '" label: "' + label + '\\n" }\n'
                             'edge: { sourcename: "services_main" targetname: "test.c:' + clone + '" }\n')
            report = call_chain_report(out, frames, disassembly, 16384)
            self.assertEqual(report['conservative_peak_bytes'], 48)
            self.assertEqual(report['longest_chain'], ['services_main', label])
            graph.write_text(graph.read_text() + 'node: { title: "other.c:' + clone +
                             '" label: "other_clone\\n" }\n')
            frames.append(dict(function='test.c:3:1:other_clone', bytes=32, kind='static'))
            with self.assertRaisesRegex(ValueError, 'ambiguous compiler clone identity'):
                call_chain_report(out, frames, disassembly, 16384)


if __name__ == '__main__':
    unittest.main()
