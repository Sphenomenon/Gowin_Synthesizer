"""Regression for the source-only custom-board example classification."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import check


class ExampleCatalog(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repository = Path(self.temporary.name)
        self.module = self.repository / 'examples/USB_HS'
        self.module.mkdir(parents=True)
        source = self.repository / 'driver.sv'
        source.write_text('module driver; endmodule\n')
        evidence = self.repository / 'verified.md'
        evidence.write_text('Reference module was checked.\n')
        (self.module / 'rtl.sv').symlink_to('../../driver.sv')
        self.manifest = dict(schema=1, id='USB_HS', assembly_status='pending',
                             source_links={'rtl.sv': 'driver.sv'},
                             source_sha256={'driver.sv': hashlib.sha256(source.read_bytes()).hexdigest()},
                             evidence=['verified.md'], reference_candidates=[dict(
                                 user_code='0xC11030A2', bitstream_sha256='1' * 64)])
        self.write_manifest(self.manifest)

    def write_manifest(self, manifest):
        (self.module / 'module.json').write_text(json.dumps(manifest))

    def test_all_real_modules_and_root_entry(self):
        root_entry = check.REPOSITORY / 'example/CUSTOM_138K'
        self.assertTrue(root_entry.is_symlink())
        self.assertFalse(root_entry.readlink().is_absolute())
        self.assertEqual(root_entry.resolve(), check.EXAMPLES)
        for name in check.MODULES:
            with self.subTest(module=name):
                self.assertEqual(check.verify_module(check.EXAMPLES / name)['module'], name)

    def test_relative_sources_are_portable_without_local_artifacts(self):
        result = check.verify_module(self.module, self.repository)
        self.assertEqual(result['assembly_status'], 'pending')
        self.assertEqual(result['source_files'], 1)

    def test_source_drift_is_reported(self):
        (self.repository / 'driver.sv').write_text('changed\n')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            check.verify_module(self.module, self.repository)

    def test_broken_link_is_reported(self):
        (self.repository / 'driver.sv').unlink()
        with self.assertRaisesRegex(ValueError, 'source entry is missing'):
            check.verify_module(self.module, self.repository)

    def test_absolute_source_link_is_rejected(self):
        link = self.module / 'rtl.sv'
        link.unlink()
        link.symlink_to(self.repository / 'driver.sv')
        with self.assertRaisesRegex(ValueError, 'relative symlink'):
            check.verify_module(self.module, self.repository)

    def test_missing_evidence_is_reported(self):
        (self.repository / 'verified.md').unlink()
        with self.assertRaisesRegex(ValueError, 'evidence is missing'):
            check.verify_module(self.module, self.repository)

    def test_classification_cannot_accept_the_workstation(self):
        changed = deepcopy(self.manifest)
        changed['assembly_status'] = 'accepted'
        self.write_manifest(changed)
        with self.assertRaisesRegex(ValueError, 'workstation acceptance'):
            check.verify_module(self.module, self.repository)

    def test_reference_identity_is_required(self):
        changed = deepcopy(self.manifest)
        changed['reference_candidates'][0]['bitstream_sha256'] = 'unknown'
        self.write_manifest(changed)
        with self.assertRaisesRegex(ValueError, 'bitstream identity'):
            check.verify_module(self.module, self.repository)


if __name__ == '__main__':
    unittest.main()
