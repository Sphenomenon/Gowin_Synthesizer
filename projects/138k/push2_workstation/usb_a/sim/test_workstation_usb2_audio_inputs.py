#!/usr/bin/env python3
"""Fail-closed selection of byte-identical native audio simulation inputs."""

from pathlib import Path
from unittest.mock import patch
import json
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ElementTree


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import workstation_usb2_audio_inputs as inputs


class AuditedAudioInputs(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='audited-audio-inputs-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.candidate = self.base / 'candidate'
        self.source = self.candidate / 'workstation/Prj1'
        self.stage = self.base / 'simulation'
        project = ElementTree.Element('Project')
        files = ElementTree.SubElement(project, 'FileList')
        for relative in inputs.AUDIO_SOURCES:
            source = self.source / relative
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text('')
            ElementTree.SubElement(files, 'File', path=relative, enable='1')
        ElementTree.ElementTree(project).write(self.source / 'Prj1.gprj')
        (self.source / 'legacy_audio.sv').write_text('`include "legacy/fixture.sv"\n')
        include = self.source / 'legacy/fixture.sv'
        include.parent.mkdir()
        include.write_text('module fixture; endmodule\n')
        asset = self.source / 'sim/data/audio_chain/pitch_bend_q20.mem'
        asset.parent.mkdir(parents=True)
        asset.write_text('100000\n')
        (self.candidate / 'integration_inputs.json').write_text(json.dumps(dict(
            source_policy='unit_test_fixture_not_production', source_snapshot_sha256={},
            bluetooth=dict(source_snapshot_sha256={}))))
        self.audit = patch.object(inputs, 'audit', return_value=dict(identity='unit_test_fixture'))
        self.mock_audit = self.audit.start()
        self.addCleanup(self.audit.stop)

    def test_copies_selected_sources_includes_and_runtime_assets_without_adaptation(self):
        selected, evidence, originals, copies = inputs.stage_audio(self.candidate, self.stage)
        self.mock_audit.assert_called_once_with(self.candidate)
        self.assertEqual(selected, [self.stage / 'audio_inputs' / relative for relative in inputs.AUDIO_SOURCES])
        self.assertFalse(evidence['physical_audio_verified'])
        self.assertIn('not_physical_DDR', evidence['memory_model'])
        self.assertEqual((self.stage / 'audio_inputs/legacy/fixture.sv').read_bytes(),
                         (self.source / 'legacy/fixture.sv').read_bytes())
        self.assertEqual((self.stage / 'sim/data/audio_chain/pitch_bend_q20.mem').read_text(), '100000\n')
        self.assertTrue(all(inputs.sha(path) == digest for path, digest in originals.items()))
        self.assertTrue(all(inputs.sha(path) == digest for path, digest in copies.items()))

    def test_failed_independent_audit_does_not_copy_inputs(self):
        self.mock_audit.side_effect = ValueError('source identity drift')
        with self.assertRaisesRegex(ValueError, 'source identity drift'):
            inputs.stage_audio(self.candidate, self.stage)
        self.assertFalse(self.stage.exists())

    def test_disabled_audio_boundary_is_not_replaced_by_historical_inputs(self):
        project = ElementTree.parse(self.source / 'Prj1.gprj')
        project.find('FileList')[0].set('enable', '0')
        project.write(self.source / 'Prj1.gprj')
        with self.assertRaisesRegex(ValueError, 'required complete audio chain'):
            inputs.stage_audio(self.candidate, self.stage)
        self.assertFalse(self.stage.exists())

    def test_missing_include_is_rejected_before_copying(self):
        (self.source / 'legacy/fixture.sv').unlink()
        with self.assertRaisesRegex(ValueError, 'missing or escaping'):
            inputs.stage_audio(self.candidate, self.stage)
        self.assertFalse(self.stage.exists())

    def test_escaping_include_is_rejected_before_copying(self):
        outside = self.base / 'outside.sv'
        outside.write_text('module outside; endmodule\n')
        (self.source / 'legacy/fixture.sv').unlink()
        (self.source / 'legacy/fixture.sv').symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'missing or escaping'):
            inputs.stage_audio(self.candidate, self.stage)
        self.assertFalse(self.stage.exists())


if __name__ == '__main__':
    unittest.main()
