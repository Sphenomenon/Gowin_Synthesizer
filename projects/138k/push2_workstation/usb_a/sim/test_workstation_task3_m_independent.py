#!/usr/bin/env python3
"""Independent M source lock and strict USB48 synthesis proof selection."""
from pathlib import Path
import copy
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_profile as profiles
from tools import workstation_demo_audit as audit
from tools.workstation_runtime_profile import DEPENDENCIES


class IndependentM(unittest.TestCase):
    def test_explicit_source_lock_reuses_M_provider_and_remote_RAM48(self):
        selected = profiles.load(ROOT, profiles.TASK3_M_INDEPENDENT_NAME)
        spec = profiles.specification(selected['name'])
        parent = profiles.specification(profiles.M_DEMO_NAME)
        self.assertEqual(spec['provider'], parent['provider'])
        self.assertEqual(selected['configuration'], dict(parent['configuration'], usb2_cpu_ram_bytes=49152))
        self.assertNotIn('usb2_cpu_ram_bytes', parent['configuration'])
        self.assertEqual(audit.PROFILES[selected['name']][2], parent['provider'])
        self.assertEqual(selected['checkpoint_parent']['profile'], profiles.M_DEMO_NAME)
        self.assertFalse(selected['checkpoint_parent']['historical_descriptor_modified'])
        prefix = ROOT.relative_to(ROOT.parents[3]).as_posix() + '/'
        for source in ('tools/workstation_usb_cpu_rom.py', 'rtl/usb2/workstation_usb2_cpu_bus.sv',
                       'rtl/audio/workstation_runtime_render_engines.sv', 'rtl/ddr_address_map.vh',
                       'rtl/workstation/workstation_task3_w_media_top_reference.json'):
            self.assertIn(prefix + source, selected['source_sha256'])
        self.assertIn('rtl/ddr_address_map.vh', DEPENDENCIES)
        self.assertIn('rtl/workstation/workstation_task3_w_media_top_reference.json', DEPENDENCIES)

    def test_changed_source_and_configuration_fail_before_prepare(self):
        selected = profiles.load(ROOT, profiles.TASK3_M_INDEPENDENT_NAME)
        source = ROOT / 'rtl/usb2/workstation_usb2_cpu_bus.sv'
        original = profiles.sha
        with patch.object(profiles, 'sha', side_effect=lambda path: '0' * 64
                          if Path(path) == source else original(path)):
            with self.assertRaisesRegex(ValueError, 'source drift'):
                profiles.load(ROOT, selected['name'])
        changed = copy.deepcopy(selected)
        changed['configuration']['usb2_cpu_ram_bytes'] = 65536
        descriptor = ROOT / profiles.specification(selected['name'])['config']
        original_read = Path.read_text
        with patch.object(Path, 'read_text', lambda path, *args, **kwargs: json.dumps(changed)
                          if path == descriptor else original_read(path, *args, **kwargs)):
            with self.assertRaisesRegex(ValueError, 'configuration mismatch'):
                profiles.load(ROOT, selected['name'])

    def test_RAM48_uses_primitive_word_proof_and_propagates_failure(self):
        config = {'usb2_cpu_ram_bytes': 49152}
        firmware = {'ram_bytes': 49152, 'rom_sha256': 'f' * 64}
        proof = dict(words=12288, bytes=49152, blocks=24, every_word_verified=True)
        with patch('tools.workstation_usb_cpu_rom.check_banked_rom', return_value=proof) as banked, \
             patch('tools.workstation_custom_board_audit.check_rom') as legacy:
            self.assertEqual(audit.audit_usb_rom(ROOT, 'mapped', 'netlist', firmware, config), proof)
            banked.assert_called_once_with(ROOT, 'netlist', firmware)
            legacy.assert_not_called()
        with patch('tools.workstation_usb_cpu_rom.check_banked_rom',
                   side_effect=ValueError('CPU synthesized ROM mismatch at word 4096')):
            with self.assertRaisesRegex(ValueError, 'ROM mismatch'):
                audit.audit_usb_rom(ROOT, 'mapped', 'netlist', firmware, config)
        for wrong in (65536, None):
            with self.assertRaisesRegex(ValueError, 'firmware capacity mismatch'):
                audit.audit_usb_rom(ROOT, 'mapped', 'netlist', dict(firmware, ram_bytes=wrong), config)
        for wrong in (True, 32768):
            with self.assertRaisesRegex(ValueError, 'unregistered USB CPU RAM capacity'):
                audit.audit_usb_rom(ROOT, '', None, firmware, {'usb2_cpu_ram_bytes': wrong})

    def test_default_RAM64_keeps_original_word_checker(self):
        firmware = {'ram_bytes': 65536, 'rom_sha256': 'e' * 64}
        with patch('tools.workstation_custom_board_audit.check_rom', return_value=16384) as legacy, \
             patch('tools.workstation_usb_cpu_rom.check_banked_rom') as banked:
            self.assertEqual(audit.audit_usb_rom(ROOT, 'mapped', None, firmware, {})['words'], 16384)
            legacy.assert_called_once_with(ROOT, 'mapped', firmware['rom_sha256'])
            banked.assert_not_called()
        with patch('tools.workstation_custom_board_audit.check_rom', return_value=16384):
            historical = {'rom_sha256': firmware['rom_sha256']}
            self.assertEqual(audit.audit_usb_rom(ROOT, 'mapped', None, historical, {})['words'], 16384)


if __name__ == '__main__':
    unittest.main()
