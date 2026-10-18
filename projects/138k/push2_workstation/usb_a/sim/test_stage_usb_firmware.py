#!/usr/bin/env python3
"""Offline staging regression; compiler invocation is mocked, not an RTL build."""
from pathlib import Path
import importlib.util
import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import stage_usb_firmware as staging


class UsbFirmwareStagingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'live'
        self.output = self.base / 'result'
        self.stage = self.output / 'Prj1'
        self.stage.mkdir(parents=True)
        shutil.copytree(ROOT / 'vendor/usb_host_fs_8fc3/firmware',
                        self.root / 'vendor/usb_host_fs_8fc3/firmware')
        (self.root / 'firmware.c').write_text('#include "gw25k_panel.h"\nint main(void){return PANEL;}\n')
        (self.root / 'gw25k_panel.h').write_text('#define PANEL 138\n')
        # A stale accepted ROM must be replaced at both readmemh locations.
        (self.stage / 'push2_usb_a.hex').write_text('stale accepted ROM\n')
        (self.stage / 'src/usb_a').mkdir(parents=True)
        (self.stage / 'src/usb_a/push2_usb_a.hex').write_text('stale local ROM\n')
        self.frozen_sha = {str(path.relative_to(self.root)): staging.sha(path)
                           for path in (self.root / 'vendor').rglob('*') if path.is_file()}
        self.commands = []

    def compiler(self, command, **kwargs):
        self.commands.append(command)
        self.assertTrue(kwargs['check'])
        self.assertEqual(kwargs['cwd'], self.output / 'firmware')
        cwd = kwargs['cwd']
        if '-c' in command:
            self.assertIn('-march=rv32i', command)
            self.assertIn('-mabi=ilp32', command)
            (cwd / command[command.index('-o') + 1]).write_bytes(b'OBJECT')
        elif command[0].endswith('-gcc'):
            self.assertIn('-nostdlib', command)
            (cwd / 'firmware.elf').write_bytes(b'ELF fixture')
        elif command[0].endswith('-objcopy'):
            (cwd / 'firmware.bin').write_bytes(bytes.fromhex('0123456789ab'))
        elif command[0].endswith('-size'):
            return subprocess.CompletedProcess(command, 0,
                stdout='   text    data     bss     dec     hex filename\n   1200      20     300    1520     5f0 firmware.elf\n')
        elif command[0].endswith('-nm'):
            return subprocess.CompletedProcess(command, 0, stdout='000005f0 B _ebss\n')
        return subprocess.CompletedProcess(command, 0)

    def test_live_sources_compile_and_replace_both_frozen_rom_paths(self):
        with patch.object(staging, 'compiler_prefix', return_value='fixture-riscv'), \
             patch.object(staging.subprocess, 'run', side_effect=self.compiler):
            result = staging.stage_usb_firmware(self.root, self.stage, self.output)
        fw = self.output / 'firmware'
        for name in ('firmware.c', 'gw25k_panel.h'):
            self.assertEqual((fw / name).read_bytes(), (self.root / name).read_bytes())
            self.assertEqual(result['live_sha256'][name], staging.sha(self.root / name))
        text = (fw / 'usb/usb_hw.c').read_text()
        self.assertEqual(text.count('int usbhw_transfer_out_preloaded('), 1)
        self.assertIn('return usbhw_transfer_out_preloaded(', text)
        self.assertEqual(text.count('for (int l=0;l<tx_length;l++)'), 1)
        self.assertIn('int usbhw_transfer_out_preloaded(', (fw / 'usb/usb_hw.h').read_text())
        first = self.stage / 'push2_usb_a.hex'
        second = self.stage / 'src/usb_a/push2_usb_a.hex'
        self.assertEqual(first.read_bytes(), second.read_bytes())
        words = first.read_text().splitlines()
        self.assertEqual(len(words), 16384)
        self.assertEqual(words[:3], ['67452301', '0000ab89', '00000000'])
        self.assertEqual(result['firmware_bytes'], 6)
        self.assertEqual(result['static_ram_bytes'], 1520)
        self.assertEqual(result['stack_margin_bytes'], 65536-1520)
        self.assertEqual(result['rom_sha256']['push2_usb_a.hex'], staging.sha(first))
        self.assertFalse(result['hardware_tested'])
        self.assertEqual(len(self.commands), 9)  # five objects, link, objcopy, size, nm
        self.assertIn('gw25k_panel.h', result['staged_source_sha256'])
        self.assertEqual(self.frozen_sha, {str(path.relative_to(self.root)): staging.sha(path)
                         for path in (self.root / 'vendor').rglob('*') if path.is_file()})

    def test_missing_live_header_fails_before_staging(self):
        (self.root / 'gw25k_panel.h').unlink()
        with patch.object(staging, 'compiler_prefix', return_value='fixture-riscv'):
            with self.assertRaisesRegex(FileNotFoundError, 'missing live USB adapter source'):
                staging.stage_usb_firmware(self.root, self.stage, self.output)
        self.assertFalse((self.output / 'firmware').exists())

    def test_explicit_missing_compiler_is_actionable(self):
        with patch.object(staging.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(FileNotFoundError, 'GW138K_RISCV_PREFIX'):
                staging.compiler_prefix('/missing/riscv')

    def test_bss_overflow_fails_even_when_binary_is_small(self):
        def oversized_bss(command, **kwargs):
            if command[0].endswith('-size'):
                return subprocess.CompletedProcess(command, 0,
                    stdout='text data bss dec hex filename\n1200 20 59000 60220 eb3c firmware.elf\n')
            return self.compiler(command, **kwargs)
        with patch.object(staging, 'compiler_prefix', return_value='fixture-riscv'), \
             patch.object(staging.subprocess, 'run', side_effect=oversized_bss):
            with self.assertRaisesRegex(ValueError, 'static RAM bytes=60220'):
                staging.stage_usb_firmware(self.root, self.stage, self.output)
        self.assertEqual((self.stage / 'push2_usb_a.hex').read_text(), 'stale accepted ROM\n')

    def test_linker_alignment_and_gaps_are_included_in_ram_limit(self):
        def gap_overflow(command, **kwargs):
            if command[0].endswith('-nm'):
                return subprocess.CompletedProcess(command, 0, stdout='0000ea60 B _ebss\n')
            return self.compiler(command, **kwargs)
        with patch.object(staging, 'compiler_prefix', return_value='fixture-riscv'), \
             patch.object(staging.subprocess, 'run', side_effect=gap_overflow):
            with self.assertRaisesRegex(ValueError, 'static RAM end=60000'):
                staging.stage_usb_firmware(self.root, self.stage, self.output)

    def test_current_builder_rejects_missing_accepted_baseline_without_building(self):
        path = ROOT / 'tools/build_current_workstation.py'
        spec = importlib.util.spec_from_file_location('current_workstation_test', path)
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        builder.BASE = self.base / 'absent-full83'
        error_text = io.StringIO()
        with patch.object(sys, 'argv', [str(path), '--prepare-only']), \
             patch.object(builder, 'stage_usb_firmware') as compile_firmware, \
             contextlib.redirect_stderr(error_text):
            with self.assertRaises(SystemExit) as error:
                builder.main()
        self.assertEqual(error.exception.code, 2)
        self.assertIn('accepted full83 staging tree is missing', error_text.getvalue())
        compile_firmware.assert_not_called()


if __name__ == '__main__':
    unittest.main()
