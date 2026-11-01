#!/usr/bin/env python3
"""Exact new chain, unchanged CRC manifest and complete source-drift controls."""
from pathlib import Path
import importlib.util,json,os,sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.workstation_tf_fat_cache_provenance import validate_adaptation,MANIFEST,BASIS
from tools.workstation_tf_sd_crc16_provenance import validate_adaptation as validate_crc

class FatCacheProvenance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.chain=None;cls.mutations=[]
    @classmethod
    def tearDownClass(cls):
        path=os.environ.get('GW138K_TF_FAT_CACHE_PROVENANCE_EVIDENCE')
        if path:Path(path).write_text(json.dumps(dict(actual_chain=cls.chain,rejected_mutations=cls.mutations,
            mutation_count=len(cls.mutations),in_memory_only=True,source_files_written=False),indent=2)+'\n')
    def test_actual_two_stage_inverse_and_original_chain(self):
        report,prior=validate_adaptation(ROOT)
        self.assertEqual(set(prior),set(BASIS))
        self.assertTrue(report['prior_CRC_manifest_bytes_unchanged'])
        self.assertTrue(report['prior_CRC_chain']['original_manifests_and_vendor_bytes_unchanged'])
        self.assertTrue(report['prior_CRC_chain']['original_file_forward_derivation_exact'])
        self.assertFalse(report['default_cache_enabled'])
        self.__class__.chain=report
    def test_explicit_new_branch_only(self):
        with self.assertRaisesRegex(ValueError,'maintained adapted source changed'):validate_crc(ROOT)
        report,original=validate_crc(ROOT,fat_cache_source_adaptation=True)
        self.assertEqual(len(original),4)
        self.assertTrue(report['explicit_FAT_cache_source_adaptation']['enabled_cache_requires_CRC'])
        p=ROOT/'sim/tf_audio/run_workstation_tf_file_reader_wire.py'
        spec=importlib.util.spec_from_file_location('fat_default_file_validator',p)
        old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
        with self.assertRaisesRegex(ValueError,'maintained adapted source changed'):
            old.provenance(ROOT,direct_crc_source_adaptation=True)
        report=old.provenance(ROOT,direct_fat_cache_source_adaptation=True)
        self.assertTrue(report['exact_forward_and_reverse'])
    def test_source_drift_cannot_hide_behind_inverse(self):
        paths=[*BASIS,MANIFEST,'rtl/tf_audio/storage/workstation_tf_fat_sector_cache_v1.sv',
            'rtl/tf_audio/storage/workstation_tf_sd_crc16_v1.adaptation.json',
            'rtl/tf_audio/storage/workstation_tf_sd_crc16_v1.sv',
            'rtl/tf_audio/storage/workstation_tf_sd_sector_reader.sv',
            'rtl/tf_audio/storage/workstation_tf_sd_sector_reader.provenance.json',
            'rtl/tf_audio/storage/workstation_tf_file_reader.provenance.json',
            'rtl/tf_audio/storage/workstation_tf_spi_session.sv',
            'rtl/tf_audio/storage/tang_mp3/vendor/tf_sd_spi_sector_reader.v',
            'rtl/tf_audio/storage/tang_mp3/vendor/tf_spi_session.v',
            'rtl/tf_audio/storage/tang_mp3/sd/tf_sd_file_reader.v']
        original=Path.read_bytes
        for relative in paths:
            selected=ROOT/relative
            def changed(path,selected=selected):
                raw=original(path);return raw+b'\n' if path==selected else raw
            with self.subTest(path=relative),patch.object(Path,'read_bytes',changed):
                with self.assertRaises(ValueError) as error:validate_adaptation(ROOT)
            self.mutations.append(dict(path=relative,rejected=True,error=str(error.exception)))
        self.assertEqual(len(paths),15)
if __name__=='__main__':unittest.main()
