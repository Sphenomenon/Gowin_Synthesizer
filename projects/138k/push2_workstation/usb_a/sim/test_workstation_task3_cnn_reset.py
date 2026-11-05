#!/usr/bin/env python3
"""Guard opt-in reset changes against exact historical source drift."""
from pathlib import Path
import hashlib
import shutil
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tools'))
from tools import workstation_task3_cnn_reset as reset
from build_resource_rework import select_native_cnn_parameters,NATIVE_CNN_INPUTS
from workstation_cnn_cdc import transform as synchronize_diagnostics


class CnnResetSources(unittest.TestCase):
    def test_exact_source_inverse_and_paired_geometry(self):
        with tempfile.TemporaryDirectory() as folder:
            stage=Path(folder)
            for name in reset.PARENTS:
                target=stage/name;target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/name,target)
            proof=reset.source_evidence(stage)
            self.assertEqual(len(proof['sources']),3)
            link,selection=select_native_cnn_parameters(stage)
            self.assertTrue(selection['reset_policy_exact_inverse_checked'])
            (stage/reset.LINK).write_text(link)
            self.assertEqual(reset.source_evidence(stage)['policy'],reset.POLICY)
            staged=synchronize_diagnostics(link)
            self.assertEqual(reset.inverse(reset.LINK,staged),reset.inverse(reset.LINK,link))
            (stage/reset.LINK).write_text(staged)
            self.assertEqual(reset.source_evidence(stage)['policy'],reset.POLICY)
            for changed in (staged.replace('ddr_trace_sync[6:2]','ddr_trace_sync[5:1]'),
                    staged.replace("model_status,ddr_trace_sync[0],1'b1};","model_status,memory_calibrated,1'b1};")):
                with self.assertRaises(ValueError):reset.inverse(reset.LINK,changed)
            for name in reset.PARENTS:
                path=stage/name;original=path.read_text()
                with self.subTest(path=name),self.assertRaises(ValueError):
                    reset.inverse(name,original+'\n// unreviewed drift\n')
                if name in NATIVE_CNN_INPUTS:
                    parent=reset.inverse(name,original)
                    self.assertEqual(hashlib.sha256(parent.encode()).hexdigest(),NATIVE_CNN_INPUTS[name])
                    path.write_text(original+'\n// unreviewed drift\n')
                    with self.assertRaises(ValueError):select_native_cnn_parameters(stage)
                    path.write_text(original)

    def test_legacy_source_admission_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            stage=Path(folder)
            for name in NATIVE_CNN_INPUTS:
                path=stage/name;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(reset.inverse(name,(ROOT/name).read_text()))
            _,selection=select_native_cnn_parameters(stage)
            self.assertFalse(selection['reset_policy_exact_inverse_checked'])
            self.assertEqual(selection['input_sha256'],NATIVE_CNN_INPUTS)


if __name__=='__main__':unittest.main()
