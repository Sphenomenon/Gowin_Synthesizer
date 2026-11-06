"""Fail closed on local-reset source drift, wrong roles and unselected options."""
from pathlib import Path
import copy
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import workstation_task3_tf_tail_reset as reset

CONFIG=dict(demo_role='M',tf_policy='task3_m_native_direct_tf_v1',
            phone_batch_policy='full_key_atomic_owner_snapshot_command_v1',
            tf_tail_reset_policy=reset.POLICY)


class SourceContract(unittest.TestCase):
    def stage(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        stage=Path(temp.name)
        for relative in (reset.RUNTIME,reset.TAIL):
            path=stage/relative;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes((ROOT/relative).read_bytes())
        return stage

    def test_exact_inverse_and_explicit_parameter_selection(self):
        stage=self.stage()
        for relative in (reset.RUNTIME,reset.TAIL):
            text=(stage/relative).read_text()
            self.assertEqual(reset.digest(reset.inverse(relative,text)),reset.records()[relative]['parent_sha256'])
        selected=reset.select(stage,CONFIG)
        self.assertEqual(selected,reset.evidence(stage,CONFIG))
        self.assertEqual(selected['new_reset_registers'],0)
        self.assertFalse(selected['session_fence_resets_mailbox'])
        self.assertFalse(selected['routed_timing_verified'])

    def test_wrong_role_owner_and_unknown_policy_rejected(self):
        for key,value in [('demo_role','W'),('tf_policy','other'),
                          ('phone_batch_policy',None),(reset.KEY,'unknown')]:
            changed=dict(CONFIG);changed[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):reset.select(self.stage(),changed)

    def test_source_reset_clock_fence_and_unrelated_drift_rejected(self):
        stage=self.stage();reset.select(stage,CONFIG)
        for relative in (reset.RUNTIME,reset.TAIL):
            path=stage/relative;original=path.read_text()
            for changed in (original+'\n// drift\n',
                            original.replace('compute_reset_n','unreviewed_reset_n'),
                            original.replace('serial_clk_i','other_clk_i')):
                if changed==original:continue
                path.write_text(changed)
                with self.subTest(relative=relative),self.assertRaises(ValueError):reset.evidence(stage,CONFIG)
                path.write_text(original)

    def test_unselected_and_missing_source_rejected(self):
        stage=self.stage()
        with self.assertRaises(ValueError):reset.evidence(stage,CONFIG)
        reset.select(stage,CONFIG)
        with self.assertRaises(ValueError):reset.evidence(stage,{})
        (stage/reset.TAIL).unlink()
        with self.assertRaises(ValueError):reset.evidence(stage,CONFIG)


if __name__=='__main__':unittest.main()
