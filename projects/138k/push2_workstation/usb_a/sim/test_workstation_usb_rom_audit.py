"""Verify every firmware word and destructive controls on an explicit actual VG."""
from pathlib import Path
import hashlib
import os
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_custom_board_audit import check_rom


class ActualUsbRom(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected = os.environ.get('GW138K_ROM_AUDIT_CANDIDATE')
        if not selected:
            raise unittest.SkipTest('explicit real candidate required; no cache fallback')
        cls.stage = Path(selected) / 'workstation/Prj1'
        cls.vg = (cls.stage / 'impl/gwsynthesis/custom_138k_integration.vg').read_text()
        cls.sha = hashlib.sha256((cls.stage / 'usb2_cpu.hex').read_bytes()).hexdigest()

    def test_actual_generated_ram64_verifies_all_words(self):
        self.assertEqual(check_rom(self.stage, self.vg, self.sha), 16384)

    def test_legacy_instance_spelling_verifies_the_same_exact_rom(self):
        legacy = re.sub(r'\\g_ram64\.memory_(\d)_g_ram64\.memory_\1_0_(\d)_s\s',
                        r'memory_\1_memory_\1_0_\2_s', self.vg)
        self.assertNotEqual(legacy, self.vg)
        self.assertEqual(check_rom(self.stage, legacy, self.sha), 16384)

    def test_wrong_width_and_rom_byte_are_rejected(self):
        width, count = re.subn(r'(defparam \\g_ram64\.memory_0_g_ram64\.memory_0_0_0_s\s*\.BIT_WIDTH_1=)1',
                              r'\g<1>2', self.vg)
        self.assertEqual(count, 1)
        corrupted, count = re.subn(r"(defparam \\g_ram64\.memory_0_g_ram64\.memory_0_0_0_s\s*\.INIT_RAM_00=256'h)([0-9A-F])",
                                  lambda m: m[1] + format(int(m[2], 16) ^ 1, 'X'), self.vg)
        self.assertEqual(count, 1)
        for mutant in (width, corrupted):
            with self.subTest(), self.assertRaises(ValueError):
                check_rom(self.stage, mutant, self.sha)


if __name__ == '__main__':
    unittest.main()
