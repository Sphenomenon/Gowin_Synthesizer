"""Reject mismatched source, capacity and firmware at the explicit RAM48 boundary."""
from pathlib import Path
from copy import deepcopy
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.stage_usb_firmware import (USB2_CPU_RAM_SOURCE, select_usb2_cpu_ram,
                                      sha, verify_usb2_cpu_ram_selection)
from tools.workstation_usb_cpu_rom import check_banked_rom


class UsbCpu48Selection(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='task3-usb-cpu48-')
        self.addCleanup(self.temporary.cleanup)
        self.stage = Path(self.temporary.name)
        target = self.stage / USB2_CPU_RAM_SOURCE
        target.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / USB2_CPU_RAM_SOURCE, target)
        self.original = target.read_bytes()
        self.configuration = {'usb2_cpu_ram_bytes': 49152}
        self.evidence = select_usb2_cpu_ram(ROOT, self.stage, 49152)
        generated = self.stage / 'native_usb_firmware'
        generated.mkdir()
        binary = bytes(range(128))
        (generated / 'firmware.bin').write_bytes(binary)
        padded = binary.ljust(49152, b'\0')
        rows = [f'{int.from_bytes(padded[i:i+4], "little"):08x}\n' for i in range(0, 49152, 4)]
        for directory in (self.stage, generated):
            (directory / 'usb2_cpu.hex').write_text(''.join(rows))
            for bank in range(3):
                (directory / f'usb2_cpu_bank{bank}.hex').write_text(''.join(rows[bank*4096:(bank+1)*4096]))
        (generated / 'start.S').write_text('.equ STACK_TOP, 0xc000\n')
        (generated / 'baremetal.ld').write_text('MEMORY { ram : ORIGIN = 0, LENGTH = 0xc000 }\n')
        self.firmware = dict(ram_bytes=49152, firmware_bytes=len(binary), static_ram_bytes=1024,
            static_ram_end=2048, stack_margin_bytes=49152-2048,
            binary_sha256=sha(generated / 'firmware.bin'), rom_sha256=sha(generated / 'usb2_cpu.hex'),
            generated_startup_sha256=sha(generated / 'start.S'),
            generated_linker_sha256=sha(generated / 'baremetal.ld'))

    def verify(self, **overrides):
        arguments = dict(configuration=self.configuration, evidence=self.evidence, firmware=self.firmware)
        arguments.update(overrides)
        return verify_usb2_cpu_ram_selection(ROOT, self.stage, **arguments)

    def test_matching_source_and_three_banks_accepted(self):
        self.assertEqual(self.verify(), self.evidence)
        restored = (self.stage / USB2_CPU_RAM_SOURCE).read_bytes().replace(
            b'parameter integer RAM_BYTES = 49152,', b'parameter integer RAM_BYTES = 65536,')
        self.assertEqual(restored, self.original)

    def test_default64_leaves_source_and_metadata_untouched(self):
        target = self.stage / USB2_CPU_RAM_SOURCE
        target.write_bytes(self.original)
        self.assertIsNone(select_usb2_cpu_ram(ROOT, self.stage, 65536))
        self.assertEqual(target.read_bytes(), self.original)
        self.assertIsNone(verify_usb2_cpu_ram_selection(ROOT, self.stage, {}, None))
        with self.assertRaisesRegex(ValueError, 'capacity mismatch'):
            verify_usb2_cpu_ram_selection(ROOT, self.stage, {}, None, firmware=self.firmware)

    def test_wrong_source_and_metadata_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unchanged maintained input'):
            select_usb2_cpu_ram(ROOT, self.stage, 49152)
        with self.assertRaisesRegex(ValueError, 'exact inverse changed'):
            self.verify(evidence={**self.evidence, 'after': '0' * 64})
        target = self.stage / USB2_CPU_RAM_SOURCE
        target.write_text(target.read_text() + '// unexpected input change\n')
        with self.assertRaisesRegex(ValueError, 'exact inverse changed'):
            self.verify()

    def test_capacity_and_missing_firmware_rejected(self):
        for capacity in (True, 32768, 65537):
            with self.subTest(capacity=capacity), self.assertRaisesRegex(ValueError, 'capacity'):
                self.verify(configuration={'usb2_cpu_ram_bytes': capacity})
        with self.assertRaisesRegex(ValueError, 'capacity mismatch'):
            self.verify(firmware={**self.firmware, 'ram_bytes': 65536})
        with self.assertRaisesRegex(ValueError, 'firmware evidence'):
            self.verify(firmware=None)

    def test_each_bank_corruption_is_rejected(self):
        for directory in (self.stage, self.stage / 'native_usb_firmware'):
            for bank in range(3):
                path = directory / f'usb2_cpu_bank{bank}.hex'
                original = path.read_text()
                path.write_text('ffffffff\n' + original[9:])
                with self.subTest(directory=directory.name, bank=bank), self.assertRaisesRegex(ValueError, 'bank ROM'):
                    self.verify()
                path.write_text(original)

    def test_rom_capacity_binary_stack_and_startup_drift_rejected(self):
        path = self.stage / 'usb2_cpu.hex'
        original = path.read_text()
        path.write_text(original[:-9])
        with self.assertRaisesRegex(ValueError, 'ROM identity/capacity'):
            self.verify()
        path.write_text(original)
        with self.assertRaisesRegex(ValueError, 'stack budget'):
            self.verify(firmware={**self.firmware, 'static_ram_end': 49152-8192})
        path = self.stage / 'native_usb_firmware/start.S'
        path.write_text('.equ STACK_TOP, 0x10000\n')
        with self.assertRaisesRegex(ValueError, 'startup/linker'):
            self.verify()

    def test_mapped_rom_rejects_missing_bank_width_and_initialized_word_changes(self):
        # Exercise the mapped primitive proof independently of the prepare
        # hashes: every expected word must be reconstructed from the 24 RAMs.
        words = [int(row, 16) for row in (self.stage / 'usb2_cpu.hex').read_text().splitlines()]
        cells = {}
        for bank in range(3):
            for byte in range(4):
                for nibble in range(2):
                    packed = sum(((words[bank*4096+address] >> (byte*8+nibble*4)) & 15) << (4*address)
                                 for address in range(4096))
                    name = (f'u_native_usb/host/bus/g_ram48.g_bank[{bank}].memory_{byte}_'
                            f'g_ram48.g_bank[{bank}].memory_{byte}_0_{nibble}_s')
                    parameters = dict(BIT_WIDTH_0='4', BIT_WIDTH_1='4')
                    for chunk in range(64):
                        value = (packed >> (chunk*256)) & ((1 << 256)-1)
                        if value:
                            parameters[f'INIT_RAM_{chunk:02X}'] = f"256'h{value:064x}"
                    cells[name] = dict(kind='SDPB', parameters=parameters)
        actual = SimpleNamespace(cells=cells)
        self.assertEqual(check_banked_rom(self.stage, actual, self.firmware)['words'], 12288)
        for mode in ('missing', 'width', 'word'):
            changed = deepcopy(cells)
            name = next(iter(changed))
            if mode == 'missing':
                del changed[name]
            elif mode == 'width':
                changed[name]['parameters']['BIT_WIDTH_1'] = '1'
            else:
                parameters = changed[name]['parameters']
                value = int(parameters.get('INIT_RAM_00', "256'h0").split("'h")[1], 16) ^ 1
                parameters['INIT_RAM_00'] = f"256'h{value:064x}"
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                check_banked_rom(self.stage, SimpleNamespace(cells=changed), self.firmware)


if __name__ == '__main__':
    unittest.main()
