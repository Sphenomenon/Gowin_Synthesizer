#!/usr/bin/env python3
"""DDR include-order regression using real old/current headers and CNN source."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_ddr_map_aliases as aliases
from tools import workstation_profile as profiles
from tools.workstation_baselines import source_bytes


class DDRAliases(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.stage = Path(self.temp.name)
        descriptor = json.loads((ROOT / 'baselines/resource_rework_route0_source_only.json').read_text())
        self.original = source_bytes(ROOT.parents[3], descriptor['files'][aliases.ALIAS], aliases.ALIAS)
        self.selected = (ROOT / aliases.SOURCE).read_bytes()
        for relative, data in ((aliases.ALIAS, self.original), (aliases.SOURCE, self.selected),
                               ('rtl/music/workstation_cnn_task_service.sv',
                                (ROOT / 'rtl/music/workstation_cnn_task_service.sv').read_bytes())):
            target = self.stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        baseline = SimpleNamespace(read_bytes=lambda relative: self.original)
        self.load = patch('tools.workstation_recording_policy.load_baseline', return_value=baseline)
        self.load.start()
        self.addCleanup(self.load.stop)

    def preprocess(self, includes):
        self.assertIsNotNone(shutil.which('iverilog'), 'Icarus is required for the include-order regression')
        wrapper = self.stage / 'wrapper.sv'
        wrapper.write_text(''.join('`include "' + name + '"\n' for name in includes))
        output = self.stage / 'preprocessed.sv'
        run = subprocess.run(['iverilog', '-g2012', '-E', '-I', str(self.stage),
                              '-o', str(output), str(wrapper)], cwd=self.stage, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        return output.read_text(), run.stderr

    def test_opt_in_retains_original_profile_configuration(self):
        self.assertFalse(aliases.configured({}))
        self.assertTrue(aliases.configured({aliases.KEY: aliases.POLICY}))
        with self.assertRaisesRegex(ValueError, 'unknown DDR'):
            aliases.configured({aliases.KEY: 'unknown'})
        old = profiles.specification(profiles.TASK3_M_INDEPENDENT_NAME)
        new = profiles.specification(profiles.TASK3_M_INDEPENDENT_MAP_NAME)
        self.assertEqual(new['configuration'], dict(old['configuration'], **{aliases.KEY: aliases.POLICY}))
        self.assertEqual(new['provider'], old['provider'])
        self.assertNotIn(aliases.KEY, old['configuration'])

    def test_original_single_file_check_misses_shared_guard_collision(self):
        cnn = 'rtl/music/workstation_cnn_task_service.sv'
        alone, warnings = self.preprocess([cnn])
        self.assertFalse(warnings)
        self.assertIn("CAPACITY_FRAMES=32'd96_000", alone)
        collision, warnings = self.preprocess([aliases.ALIAS, cnn])
        self.assertIn('macro PRJ1_DDR_TASK3_W_CNN_PCM_CAPACITY_FRAMES undefined', warnings)
        self.assertNotIn("CAPACITY_FRAMES=32'd96_000", collision)

    def test_equal_aliases_resolve_real_CNN_in_both_orders(self):
        evidence = aliases.install(ROOT, self.stage)
        aliases.verify(ROOT, self.stage, evidence)
        self.assertEqual(evidence['preserved_parent_macros'], 69)
        for includes in ([aliases.ALIAS, 'rtl/music/workstation_cnn_task_service.sv'],
                         [aliases.SOURCE, aliases.ALIAS, 'rtl/music/workstation_cnn_task_service.sv']):
            text, warnings = self.preprocess(includes)
            self.assertFalse(warnings)
            self.assertIn("CAPACITY_FRAMES=32'd96_000", text)

    def test_changed_parent_fails_without_overwrite(self):
        target = self.stage / aliases.ALIAS
        target.write_bytes(self.original + b'\n// drift\n')
        before = target.read_bytes()
        with self.assertRaisesRegex(ValueError, 'parent changed'):
            aliases.install(ROOT, self.stage)
        self.assertEqual(target.read_bytes(), before)

    def test_changed_authority_and_old_allocation_fail(self):
        target = self.stage / aliases.SOURCE
        target.write_bytes(self.selected + b'\n// drift\n')
        with self.assertRaisesRegex(ValueError, 'authority changed'):
            aliases.install(ROOT, self.stage)
        with tempfile.TemporaryDirectory() as changed:
            changed = Path(changed)
            target = changed / aliases.SOURCE
            target.parent.mkdir(parents=True)
            target.write_bytes(self.selected.replace(b"32'h4000_0000", b"32'h2000_0000", 1))
            with self.assertRaisesRegex(ValueError, 'existing allocation'):
                aliases.address_map_inputs(changed)

    def test_both_aliases_and_evidence_are_checked_after_prepare(self):
        evidence = aliases.install(ROOT, self.stage)
        for relative in (aliases.SOURCE, aliases.ALIAS):
            target = self.stage / relative
            target.write_bytes(self.original)
            with self.assertRaisesRegex(ValueError, 'bytes changed'):
                aliases.verify_staged(self.stage, evidence, authority_sha256=aliases.digest(self.selected))
            target.write_bytes(self.selected)
        with self.assertRaisesRegex(ValueError, 'evidence changed'):
            aliases.verify_staged(self.stage, dict(evidence, equal_include_bytes=False),
                                  authority_sha256=aliases.digest(self.selected))
        with self.assertRaisesRegex(ValueError, 'original allocations changed'):
            aliases.verify(ROOT, self.stage, dict(evidence, parent_sha256='0' * 64))


if __name__ == '__main__':
    unittest.main()
