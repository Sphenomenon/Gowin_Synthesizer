#!/usr/bin/env python3
"""AE350 source closure, real compiler output and memory-bound regressions."""

from pathlib import Path
import json
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import stage_ae350_firmware as staging


SIZE = 'text data bss dec hex filename\n1000 16 64 1080 438 firmware.elf\n'
SYMBOLS = '''80000000 T _start
800003e8 A __data_load_start
00000200 D __data_start
00000210 D __data_end
00000210 B __bss_start
00000250 B __bss_end
'''


class Ae350FirmwareTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def maintained_root(self, name='root'):
        root = self.directory / name
        shutil.copytree(ROOT / 'firmware/ae350', root / 'firmware/ae350')
        return root

    def test_ram_alignment_and_reserved_stack_are_checked_separately_from_small_rom(self):
        result = staging.memory_report(SIZE, SYMBOLS, 'li sp, 0x2000\n', 1016)
        self.assertEqual(result['static_ram_span_bytes'], 0x50)
        self.assertEqual(result['stack_capacity_bytes'], 0x1db0)
        with self.assertRaisesRegex(ValueError, 'RAM globals overlap'):
            staging.memory_report(SIZE, SYMBOLS.replace('00000250', '00001004'), 'li sp, 0x2000\n', 1016)

    def test_rom_entry_and_startup_stack_cannot_escape_audited_hardware_ranges(self):
        with self.assertRaisesRegex(ValueError, 'ROM overflow'):
            staging.memory_report(SIZE, SYMBOLS, 'li sp, 0x2000\n', 16385)
        with self.assertRaisesRegex(ValueError, 'reset entry'):
            staging.memory_report(SIZE, SYMBOLS.replace('80000000', '80000004'), 'li sp, 0x2000\n', 1016)
        with self.assertRaisesRegex(ValueError, 'stack top'):
            staging.memory_report(SIZE, SYMBOLS, 'li sp, 0x4000\n', 1016)
        with self.assertRaisesRegex(ValueError, 'linker symbols missing'):
            staging.memory_report(SIZE, SYMBOLS.replace('__bss_end', 'unused'), 'li sp, 0x2000\n', 1016)

    def test_missing_source_fails_before_any_compiler_or_output(self):
        root = self.maintained_root()
        (root / 'firmware/ae350/ui_model.h').unlink()
        with patch.object(staging, 'compiler_prefix') as compiler:
            with self.assertRaisesRegex(FileNotFoundError, 'ui_model.h'):
                staging.stage_ae350_firmware(root, self.directory / 'output')
        compiler.assert_not_called()
        self.assertFalse((self.directory / 'output').exists())

    def test_existing_output_is_never_reused_or_overwritten(self):
        output = self.directory / 'output'
        output.mkdir()
        sentinel = output / 'firmware.elf'
        sentinel.write_bytes(b'preserve this candidate')
        with self.assertRaises(FileExistsError):
            staging.stage_ae350_firmware(ROOT, output)
        self.assertEqual(sentinel.read_bytes(), b'preserve this candidate')

    def test_truncated_or_nonhex_reference_rom_is_rejected(self):
        reference = self.directory / 'reference.mem'
        for content in ('00000000\n', 'xxxxxxxx\n' * 4096):
            reference.write_text(content)
            with self.assertRaisesRegex(ValueError, '4096 hexadecimal words'):
                staging.decode_rom(reference)

    def test_import_provenance_is_bound_to_the_actual_baseline(self):
        root = self.maintained_root()
        provenance = root / 'firmware/ae350/provenance.json'
        data = json.loads(provenance.read_text())
        data['files']['ui_main.c']['sha256'] = '0' * 64
        provenance.write_text(json.dumps(data))
        baseline = staging.load_baseline(ROOT, 'resource_rework_route0')
        with patch.object(staging, 'load_baseline', return_value=baseline), \
             patch.object(staging, 'compiler_prefix') as compiler:
            with self.assertRaisesRegex(ValueError, 'source provenance drift: ui_main.c'):
                staging.stage_ae350_firmware(root, self.directory / 'output')
        compiler.assert_not_called()
        self.assertFalse((self.directory / 'output').exists())

    def test_first_party_sources_have_a_separate_exact_provenance_closure(self):
        baseline = staging.load_baseline(ROOT, 'resource_rework_route0')
        for case in ('missing', 'extra', 'hash', 'source', 'kind', 'bytes', 'imported'):
            with self.subTest(case=case):
                root = self.maintained_root(case)
                path = root / 'firmware/ae350/provenance.json'
                data = json.loads(path.read_text())
                descriptor = data['first_party_files']['audio_clock_service.c']
                if case == 'missing':
                    del data['first_party_files']['audio_clock_service.c']
                elif case == 'extra':
                    data['first_party_files']['unreviewed.c'] = descriptor.copy()
                elif case == 'hash':
                    descriptor['sha256'] = '0' * 64
                elif case == 'source':
                    descriptor['source'] = 'private/historical/audio_clock_service.c'
                elif case == 'kind':
                    descriptor['kind'] = 'imported'
                elif case == 'bytes':
                    with (root / 'firmware/ae350/audio_clock_service.c').open('a') as f:
                        f.write('\n/* unrecorded change */\n')
                else:
                    data['files']['audio_clock_service.c'] = descriptor.copy()
                path.write_text(json.dumps(data))
                with patch.object(staging, 'load_baseline', return_value=baseline), \
                     patch.object(staging, 'compiler_prefix') as compiler:
                    with self.assertRaisesRegex(ValueError, 'source (inventory|provenance) drift'):
                        staging.stage_ae350_firmware(root, self.directory / ('out-' + case))
                compiler.assert_not_called()
                self.assertFalse((self.directory / ('out-' + case)).exists())

    def test_missing_first_party_inputs_fail_before_compiler(self):
        for name in (*staging.FIRST_PARTY_SOURCES, *staging.FIRST_PARTY_HEADERS):
            with self.subTest(name=name):
                root = self.maintained_root(name)
                (root / 'firmware/ae350' / name).unlink()
                with patch.object(staging, 'compiler_prefix') as compiler:
                    with self.assertRaisesRegex(FileNotFoundError, name):
                        staging.stage_ae350_firmware(root, self.directory / ('out-' + name))
                compiler.assert_not_called()

    def test_real_toolchain_builds_deterministic_rom_without_modifying_frozen_sources(self):
        try:
            prefix = staging.compiler_prefix()
        except FileNotFoundError as error:
            self.skipTest(str(error))
        baseline = staging.load_baseline(ROOT, 'resource_rework_route0')
        original_rom = baseline.read_bytes('firmware/boot.mem')
        first, second = self.directory / 'first', self.directory / 'second'
        one = staging.stage_ae350_firmware(ROOT, first, prefix)
        two = staging.stage_ae350_firmware(ROOT, second, prefix)
        for key in ('elf_sha256', 'binary_sha256', 'rom_sha256'):
            self.assertEqual(one[key], two[key])
        self.assertEqual(one['compiled_sources'],
                         ['start.S', 'ui_main.c', 'ui_render.c', 'ui_runtime.c', 'audio_clock_service.c'])
        self.assertEqual(set(one['imported_inputs']), set((*staging.IMPORTED_SOURCES, *staging.IMPORTED_HEADERS, 'boot.ld')))
        self.assertEqual(set(one['first_party_inputs']), {'audio_clock_service.c', 'audio_clock_service.h'})
        for name, value in one['first_party_inputs'].items():
            self.assertEqual(value, one['source_provenance']['first_party_files'][name]['sha256'])
        symbols = (first / 'firmware.nm').read_text()
        for name in ('a138_clock_mmio_bus', 'a138_clock_probe', 'a138_clock_submit', 'a138_clock_poll'):
            self.assertIn(' T ' + name + '\n', symbols)
        self.assertEqual(staging.decode_rom(first / 'boot.mem'),
                         (first / 'firmware.bin').read_bytes().ljust(16384, b'\0'))
        self.assertEqual(one['capacity']['rom_capacity_bytes'], 16384)
        self.assertGreaterEqual(one['capacity']['stack_capacity_bytes'], 4096)
        self.assertTrue(one['compiler_stack_frames'])
        self.assertFalse(one['hardware_tested'])
        self.assertFalse(one['project_rom_installed'])
        self.assertEqual(baseline.read_bytes('firmware/boot.mem'), original_rom)
        self.assertEqual((first / 'reference_boot.mem').read_bytes(), original_rom)
        self.assertEqual(json.loads((first / 'build_metadata.json').read_text()), one)


if __name__ == '__main__':
    unittest.main()
