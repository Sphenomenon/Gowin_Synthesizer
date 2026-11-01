"""Capacity changes must retain the original firmware manifest and fail on drift."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.workstation_recording_capacity_provenance import original_identity,MANIFEST


class RecordingCapacityLineage(unittest.TestCase):
    def test_real_current_sources_reverse_to_original_manifest(self):
        old=json.loads((ROOT/'firmware/ae350/provenance.json').read_text())
        for name in ('ble_business_owner.c','ble_business_owner.h'):
            payload=(ROOT/'firmware/ae350'/name).read_bytes()
            parent,evidence=original_identity(ROOT,name,payload)
            self.assertEqual(parent,old['first_party_files'][name]['sha256'])
            self.assertTrue(evidence['exact_inverse_round_trip_verified'])
            with self.assertRaises(ValueError):original_identity(ROOT,name,payload+b'\n')

    def test_original_bytes_remain_valid_but_manifest_tampering_fails(self):
        row=json.loads((ROOT/MANIFEST).read_text())
        for name in row['files']:
            payload=(ROOT/'firmware/ae350'/name).read_text()
            for edit in reversed(row['files'][name]['exact_changes']):
                payload=payload.replace(edit['after'],edit['before'],1)
            parent,evidence=original_identity(ROOT,name,payload.encode())
            self.assertEqual(parent,row['files'][name]['parent_sha256'])
            self.assertIsNone(evidence)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=root/MANIFEST;p.parent.mkdir(parents=True)
            p.write_bytes((ROOT/MANIFEST).read_bytes()+b'\n')
            with self.assertRaises(ValueError):
                original_identity(root,'ble_business_owner.c',(ROOT/'firmware/ae350/ble_business_owner.c').read_bytes())


if __name__=='__main__':unittest.main()
