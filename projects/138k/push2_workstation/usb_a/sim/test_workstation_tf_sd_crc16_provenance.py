#!/usr/bin/env python3
"""Exact CRC source chain, original-manifest retention and fail-closed probes."""
from pathlib import Path
import importlib.util
import json
import os
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.workstation_tf_sd_crc16_provenance import validate_adaptation,MANIFEST,BASIS


class CrcSourceProvenance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.positive,cls.mutations=None,[]

    @classmethod
    def tearDownClass(cls):
        target=os.environ.get('GW138K_SD_CRC_PROVENANCE_EVIDENCE')
        if target:
            Path(target).write_text(json.dumps(dict(actual_chain=cls.positive,
                rejected_mutations=cls.mutations,mutation_count=len(cls.mutations),
                in_memory_probes_only=True,original_source_files_written=False,
                hardware_tested=False),indent=2)+'\n')

    def test_01_actual_chain_and_original_manifests(self):
        r,restored=validate_adaptation(ROOT)
        self.assertEqual(set(restored),set(BASIS))
        self.assertTrue(r['original_manifests_and_vendor_bytes_unchanged'])
        self.assertTrue(r['original_file_forward_derivation_exact'])
        self.assertFalse(r['default_CRC_verification_enabled'])
        self.__class__.positive=r

    def test_02_explicit_DIRECT_validator_branch_only(self):
        path=ROOT/'sim/tf_audio/run_workstation_tf_file_reader_wire.py'
        spec=importlib.util.spec_from_file_location('crc16_legacy_file_validator',path)
        old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
        with self.assertRaisesRegex(ValueError,'file-owner source identity drift'):
            old.provenance(ROOT)
        r=old.provenance(ROOT,direct_crc_source_adaptation=True)
        self.assertTrue(r['exact_forward_and_reverse'])
        self.assertTrue(r['explicit_DIRECT_crc_source_adaptation']['original_manifests_and_vendor_bytes_unchanged'])
        self.assertNotEqual(r['native_sha256'],r['original_manifest_native_sha256'])

    def test_03_real_source_and_original_drift_controls(self):
        original=Path.read_bytes
        paths=[*BASIS,MANIFEST,
            'rtl/tf_audio/storage/workstation_tf_sd_crc16_v1.sv',
            'rtl/tf_audio/storage/workstation_tf_sd_sector_reader.provenance.json',
            'rtl/tf_audio/storage/workstation_tf_file_reader.provenance.json',
            'rtl/tf_audio/storage/tang_mp3/vendor/tf_sd_spi_sector_reader.v',
            'rtl/tf_audio/storage/tang_mp3/vendor/tf_spi_session.v',
            'rtl/tf_audio/storage/tang_mp3/sd/tf_sd_file_reader.v',
            'rtl/tf_audio/storage/workstation_tf_spi_session.sv']
        for relative in paths:
            selected=ROOT/relative
            def changed(path,selected=selected):
                raw=original(path)
                return raw+b'\n' if path==selected else raw
            with self.subTest(source=relative),patch.object(Path,'read_bytes',changed):
                with self.assertRaises(ValueError) as error:
                    validate_adaptation(ROOT)
            self.mutations.append(dict(source=relative,rejected=True,error=str(error.exception)))
        self.assertEqual(len(paths),12)


if __name__=='__main__':
    unittest.main()
