#!/usr/bin/env python3
"""Explicit R00 panel-off lock and prepared closure; no EDA or hardware fallback.

GW138K_NO_LOCAL_PANEL_PREPARE selects an existing prepared candidate. All
prepared-input mutations operate on isolated temporary copies.
"""

from pathlib import Path
from unittest.mock import patch
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_profile as profile
from tools.workstation_board_peripherals import LCD_SDC, LOCAL_PANEL_OUTPUTS, LOCAL_PANEL_SOURCE, local_panel_bundle
from tools.workstation_custom_clocks import clock_bundle


NAME = profile.R00_NO_LOCAL_PANEL_NAME
PROVIDER = profile.R00_NO_LOCAL_PANEL_PROVIDER


class ProfileSelection(unittest.TestCase):
    def test_new_lock_is_explicit_and_old_profiles_retain_local_panel_defaults(self):
        selected = profile.load(ROOT, NAME)
        spec = profile.specification(NAME)
        self.assertEqual(selected['configuration'], spec['configuration'])
        self.assertEqual(selected['configuration']['local_panel_policy'], 'disabled_local_lcd_touch_v1')
        self.assertFalse(spec['local_panel_enabled'])
        self.assertFalse(spec['recognition_enabled'])
        self.assertTrue(spec['recording_enabled'])
        self.assertEqual(spec['provider'], 'rtl/workstation/workstation_profile_r00_no_local_panel.sv')
        for name in (profile.NAME, profile.NO_CNN_NAME, profile.R00_NAME):
            with self.subTest(profile=name):
                original = profile.load(ROOT, name)
                self.assertTrue(profile.specification(name).get('local_panel_enabled', True))
                self.assertNotIn('local_panel_policy', original['configuration'])
                self.assertNotEqual(profile.specification(name)['provider'], PROVIDER)
        for relative in (PROVIDER, 'tools/workstation_board_peripherals.py',
                         'tools/workstation_custom_clocks.py', 'tools/workstation_runtime_clock_audit.py'):
            self.assertIn('projects/138k/push2_workstation/usb_a/' + relative, selected['source_sha256'])

    def test_off_policy_cannot_be_omitted_or_rebound_to_another_configuration(self):
        config_path = ROOT / profile.R00_NO_LOCAL_PANEL_CONFIG
        original = Path.read_text
        selected = json.loads(config_path.read_text())
        mutations = []
        for replacement in (None, 'enabled_local_lcd_v1'):
            changed = copy.deepcopy(selected)
            if replacement is None:
                del changed['configuration']['local_panel_policy']
            else:
                changed['configuration']['local_panel_policy'] = replacement
            mutations.append(changed)
        changed = copy.deepcopy(selected)
        changed['name'] = profile.R00_NAME
        mutations.append(changed)
        for changed in mutations:
            with self.subTest(configuration=changed['configuration']), \
                 patch.object(Path, 'read_text', lambda path, *a, **kw:
                    json.dumps(changed) if path == config_path else original(path, *a, **kw)), \
                 self.assertRaisesRegex(ValueError, 'identity changed|configuration mismatch'):
                profile.load(ROOT, NAME)
        for kwargs in (dict(hdmi_mode='720p60'), dict(allow_high_speed=False)):
            with self.subTest(options=kwargs), self.assertRaisesRegex(ValueError, 'configuration mismatch'):
                profile.load(ROOT, NAME, **kwargs)


@unittest.skipUnless(os.environ.get('GW138K_NO_LOCAL_PANEL_PREPARE'),
    'set GW138K_NO_LOCAL_PANEL_PREPARE to an existing explicit panel-off prepare; no build fallback')
class PreparedNoLocalPanel(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='no-local-panel-profile-')
        self.addCleanup(temporary.cleanup)
        self.output = Path(temporary.name) / 'candidate'
        shutil.copytree(Path(os.environ['GW138K_NO_LOCAL_PANEL_PREPARE']), self.output,
                        ignore=shutil.ignore_patterns('impl', '__pycache__'))
        self.stage = self.output / 'workstation/Prj1'
        self.metadata_path = self.output / 'integration_inputs.json'
        self.metadata = json.loads(self.metadata_path.read_text())

    def test_prepared_profile_retires_only_local_panel_and_seals_wrapper_closure(self):
        artifact = profile.verify(ROOT, self.output)
        self.assertEqual(artifact['profile'], NAME)
        self.assertEqual(artifact['configuration'], profile.specification(NAME)['configuration'])
        self.assertEqual(self.metadata['local_panel'], local_panel_bundle(False))
        self.assertIs(self.metadata['peripherals']['local_panel_enabled'], False)
        self.assertNotIn(LOCAL_PANEL_SOURCE, artifact['enabled_inputs'])
        self.assertNotIn(LOCAL_PANEL_SOURCE, self.metadata['copied_sources_sha256'])
        self.assertEqual([path for path in artifact['enabled_inputs'] if path in {
            spec['provider'] for spec in profile.PROFILE_REGISTRY.values()}], [PROVIDER])
        self.assertEqual(artifact['selected_source_owners'][PROVIDER]['selection'], 'compiled_source')
        for wrapper in (profile.R00_PROVIDER, profile.NO_CNN_PROVIDER, profile.RUNTIME_PROVIDER,
                        'rtl/workstation/workstation_profile_hdmi.sv'):
            self.assertIn(wrapper, artifact['staged_input_sha256'])
            self.assertNotIn(wrapper, artifact['enabled_inputs'])
            self.assertEqual(artifact['selected_source_owners'][wrapper]['selection'], 'staged_dependency')
        for retained in ('rtl/display_data/push2_surface_pixels.sv',
                         'rtl/display_data/workstation_ddr_scan_window.sv'):
            self.assertIn(retained, artifact['enabled_inputs'])
        sdc = (self.stage / 'constraints/custom_138k.sdc').read_text()
        self.assertTrue(sdc.startswith(clock_bundle(ROOT, local_panel_enabled=False)['sdc']))
        self.assertNotIn('u_lcd', sdc)
        self.assertNotIn('lcd_pixel31m5', sdc)
        self.assertEqual(sum(line.startswith('create_') for line in sdc.splitlines()), 15)
        cst = (self.stage / 'constraints/custom_138k.cst').read_text()
        for port, width in LOCAL_PANEL_OUTPUTS.items():
            for index in range(width):
                bit = f'{port}[{index}]' if width > 1 else port
                self.assertIn('IO_LOC "' + bit + '"', cst)
                self.assertIn('IO_PORT "' + bit + '"', cst)
        self.assertFalse(artifact['physical_gates_passed'])
        self.assertFalse(artifact['hardware_tested'])
        self.assertFalse(artifact['deployment_allowed'])

    def test_tampered_panel_selection_or_retirement_inventory_is_rejected(self):
        mutations = []
        changed = copy.deepcopy(self.metadata)
        changed['peripherals']['local_panel_enabled'] = True
        mutations.append((changed, 'local panel selection changed'))
        changed = copy.deepcopy(self.metadata)
        changed['local_panel']['retired_clocks'] = []
        mutations.append((changed, 'local panel retirement changed'))
        changed = copy.deepcopy(self.metadata)
        changed['enabled_inputs'].append(LOCAL_PANEL_SOURCE)
        mutations.append((changed, 'retired LCD source or clock remains'))
        for changed, message in mutations:
            with self.subTest(message=message):
                self.metadata_path.write_text(json.dumps(changed))
                with self.assertRaisesRegex(ValueError, message):
                    profile.verify(ROOT, self.output)
        self.metadata_path.write_text(json.dumps(self.metadata))

    def test_retired_clock_or_lcd_cdc_cannot_be_reintroduced_into_staged_sdc(self):
        source = self.stage / 'constraints/custom_138k.sdc'
        original = source.read_text()
        lcd_clock = next(line for line in clock_bundle(ROOT)['sdc'].splitlines() if 'lcd_pixel31m5' in line)
        for addition in (LCD_SDC, lcd_clock + '\n'):
            with self.subTest(addition=addition):
                source.write_text(original + addition)
                with self.assertRaisesRegex(ValueError, 'retired LCD source or clock remains'):
                    profile.verify(ROOT, self.output)
        source.write_text(original)

    def test_changed_included_wrapper_cannot_escape_staged_dependency_identity(self):
        source = self.stage / profile.R00_PROVIDER
        source.write_bytes(source.read_bytes() + b'\n// unreviewed included dependency\n')
        with self.assertRaisesRegex(ValueError, 'copied source drift|staged closure changed'):
            profile.verify(ROOT, self.output)


if __name__ == '__main__':
    unittest.main()
