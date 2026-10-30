#!/usr/bin/env python3
"""Pin the optional owner8 bridge without changing historical HDMI evidence."""
from pathlib import Path
import copy
import json
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_hdmi_provenance as hdmi


class Provenance(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / hdmi.SOURCE).read_bytes()
        self.original = (ROOT / hdmi.PROVENANCE).read_bytes()
        self.adaptation = (ROOT / hdmi.ADAPTATION).read_bytes()
        self.bridge = json.loads(self.adaptation)

    def test_explicit_current_chain_and_unchanged_original_default(self):
        old = self.source.decode()
        for edit in reversed(self.bridge['exact_changes']):
            old = hdmi.reverse_edit(old, edit, 'test')
        prior, original = hdmi.verify(old.encode(), self.original)
        current_prior, current = hdmi.verify(self.source, self.original, hdmi.OWNER8_POLICY, self.adaptation)
        self.assertEqual(prior, current_prior)
        self.assertFalse(original['adaptation_applied'])
        self.assertEqual(current['adaptation_reverse_edits'], 2)
        self.assertEqual(current['original_reverse_edits'], 19)
        self.assertEqual(current['parent_sha256'], json.loads(self.original)['parent_sha256'])
        self.assertFalse(current['hardware_acceptance_inherited'])

    def test_current_source_is_rejected_without_explicit_adaptation(self):
        with self.assertRaisesRegex(ValueError, 'Native HDMI provenance checksum changed'):
            hdmi.verify(self.source, self.original)
        with self.assertRaisesRegex(ValueError, 'requires an explicit policy'):
            hdmi.verify(self.source, self.original, adaptation=self.adaptation)
        with self.assertRaisesRegex(ValueError, 'manifest changed or missing'):
            hdmi.verify(self.source, self.original, hdmi.OWNER8_POLICY)
        with self.assertRaisesRegex(ValueError, 'Unknown HDMI provenance policy'):
            hdmi.verify(self.source, self.original, 'automatic_latest')

    def test_source_and_original_manifest_drift_are_rejected(self):
        for payload in (self.source + b'\n', self.source.replace(b'recording_native_accepts[8]', b'recording_native_accepts[7]')):
            with self.subTest(source=hdmi.sha(payload)), self.assertRaisesRegex(ValueError, 'source identity changed'):
                hdmi.verify(payload, self.original, hdmi.OWNER8_POLICY, self.adaptation)
        forged = json.loads(self.original)
        forged['native_sha256'] = hdmi.sha(self.source)
        with self.assertRaisesRegex(ValueError, 'Original HDMI provenance bytes changed'):
            hdmi.verify(self.source, json.dumps(forged).encode())

    def test_adaptation_manifest_cannot_rewrite_expected_hashes_or_edits(self):
        variants = []
        for key in ('policy', 'source', 'source_commit', 'parent_source_sha256',
                    'current_source_sha256', 'original_provenance_sha256'):
            item = copy.deepcopy(self.bridge)
            item[key] = 'forged'
            variants.append(item)
        for edit in range(2):
            item = copy.deepcopy(self.bridge)
            item['exact_changes'][edit]['after'] += '// forged\n'
            variants.append(item)
        for item in variants:
            with self.subTest(item=item), self.assertRaisesRegex(ValueError, 'manifest changed or missing'):
                hdmi.verify(self.source, self.original, hdmi.OWNER8_POLICY, json.dumps(item).encode())

    def test_each_reverse_and_forward_anchor_must_be_unique(self):
        for index, edit in enumerate(self.bridge['exact_changes']):
            for kind, text in [('missing', self.source.decode().replace(edit['after'], '')),
                               ('duplicate', self.source.decode() + edit['after']),
                               ('forward_duplicate', self.source.decode() + edit['before'])]:
                with self.subTest(edit=index, kind=kind), self.assertRaisesRegex(ValueError, 'anchor drift'):
                    hdmi.reverse_edit(text, edit, 'test')


class PreparedOwner8(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='hdmi-owner8-selection-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'current'
        self.stage = Path(temporary.name) / 'Prj1'
        self.files = ET.Element('FileList')
        enabled = {}
        for relative in (*hdmi.OWNER8_SOURCES, hdmi.SOURCE):
            for base in (self.root, self.stage):
                path = base / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((ROOT / relative).read_bytes())
            if relative in hdmi.OWNER8_SOURCES:
                ET.SubElement(self.files, 'File', path=relative, enable='1')
                enabled[relative] = dict(sha256=hdmi.sha((self.root / relative).read_bytes()))
        self.profile = dict(enabled_inputs=enabled,
                            staged_input_sha256={hdmi.SOURCE: hdmi.sha((self.root / hdmi.SOURCE).read_bytes())})
        self.write()

    def write(self):
        project = ET.Element('Project')
        project.append(self.files)
        ET.ElementTree(project).write(self.stage / 'Prj1.gprj')

    def test_actual_enabled_sources_match_current_owner_bytes(self):
        selected = hdmi.prepared_owner8_sources(self.root, self.stage, self.profile)
        self.assertEqual(set(selected), set(hdmi.OWNER8_SOURCES))

    def test_disabled_missing_duplicate_and_wrong_compilation_owner_rejected(self):
        original = copy.deepcopy(self.files)
        for kind in ('disabled', 'missing', 'duplicate', 'wrong_path'):
            self.files = copy.deepcopy(original)
            if kind == 'disabled': self.files[0].set('enable', '0')
            if kind == 'missing': self.files.remove(self.files[0])
            if kind == 'duplicate': self.files.append(copy.deepcopy(self.files[0]))
            if kind == 'wrong_path': self.files[0].set('path', 'src/other.sv')
            self.write()
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'compilation source changed'):
                hdmi.prepared_owner8_sources(self.root, self.stage, self.profile)

    def test_prepared_profile_source_and_current_owner_drifts_are_independent_checks(self):
        for base, relative in ((self.stage, hdmi.OWNER8_SOURCES[0]),
                               (self.root, hdmi.OWNER8_SOURCES[1]), (self.stage, hdmi.SOURCE)):
            path = base / relative
            original = path.read_bytes()
            path.write_bytes(original + b'\n')
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'source changed'):
                hdmi.prepared_owner8_sources(self.root, self.stage, self.profile)
            path.write_bytes(original)
        for section, relative in (('enabled_inputs', hdmi.OWNER8_SOURCES[0]),
                                  ('staged_input_sha256', hdmi.SOURCE)):
            forged = copy.deepcopy(self.profile)
            forged[section][relative] = dict(sha256='0' * 64) if section == 'enabled_inputs' else '0' * 64
            with self.subTest(section=section), self.assertRaisesRegex(ValueError, 'source changed'):
                hdmi.prepared_owner8_sources(self.root, self.stage, forged)


if __name__ == '__main__':
    unittest.main()
