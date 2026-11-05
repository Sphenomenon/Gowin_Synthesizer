#!/usr/bin/env python3
"""Reject unreviewed format sources/manifests without changing old provenance."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_recording_format_provenance as formats
from tools import workstation_task3_w_paired_firmware as paired


class RecordingFormatLineage(unittest.TestCase):
    def test_actual_four_sources_bind_original_manifest_through_reviewed_parents(self):
        original = json.loads((ROOT / 'firmware/ae350/provenance.json').read_text())
        for name in formats.NAMES:
            with self.subTest(name=name):
                payload = (ROOT / 'firmware/ae350' / name).read_bytes()
                identity, evidence = formats.original_identity(ROOT, name, payload)
                self.assertEqual(identity, original['first_party_files'][name]['sha256'])
                self.assertTrue(evidence['exact_inverse_round_trip_verified'])
                parent, _ = formats.parent_source(ROOT, name, payload)
                self.assertEqual(formats.parent_source(ROOT, name, parent), (parent, None))
                self.assertEqual(formats.original_identity(ROOT, name, parent)[0], identity)
                for changed in (payload + b'\n', payload[:-1], payload.replace(b'44100', b'44000', 1)):
                    if changed != payload:
                        with self.assertRaises(ValueError):
                            formats.original_identity(ROOT, name, changed)

    def test_lineage_manifest_tampering_is_rejected_before_source_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / formats.MANIFEST
            path.parent.mkdir(parents=True)
            payload = (ROOT / 'firmware/ae350/recording_service.c').read_bytes()
            for altered in ((ROOT / formats.MANIFEST).read_bytes() + b'\n', b'{}\n'):
                path.write_bytes(altered)
                with self.assertRaisesRegex(ValueError, 'manifest drift'):
                    formats.parent_source(root, 'recording_service.c', payload)

    def test_paired_start_adaptation_keeps_the_new_format_checks_and_exact_inverse(self):
        payload = (ROOT / paired.SOURCE).read_text()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            evidence = paired.apply(ROOT, output)
            self.assertEqual(paired.verify(ROOT, output, evidence), evidence)
            self.assertEqual(evidence['parent_sha256'], formats.digest(payload.encode()))
            self.assertIn('recording_format_lineage', evidence)
            selected = (output / Path(paired.SOURCE).name).read_text()
            self.assertIn('if(format==2 && o->format_grant_session', selected)
            self.assertEqual(selected.replace(paired.SELECTED, paired.PARENT, 1), payload)
            (output / Path(paired.SOURCE).name).write_text(selected + '\n')
            with self.assertRaisesRegex(ValueError, 'compiled-source adaptation drift'):
                paired.verify(ROOT, output, evidence)
        with self.assertRaises(ValueError):
            paired.adapt(payload + '\n')


if __name__ == '__main__':
    unittest.main()
