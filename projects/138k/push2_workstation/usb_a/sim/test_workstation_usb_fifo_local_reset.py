#!/usr/bin/env python3
"""Locked default output, exact DEMO adaptation and sealed drift failures."""
from pathlib import Path
import hashlib
import copy
import shutil
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.workstation_baselines import load_baseline
from tools.workstation_resource_timing import event_fifo
from tools import workstation_usb_fifo_reset as policy


class LocalResetPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        original=load_baseline(ROOT,'resource_rework_route0').read_bytes(policy.FIFO)
        cls.payload=event_fifo(original.decode()).encode()

    def test_default_preserves_original_generated_bytes_and_hash(self):
        self.assertEqual(policy.adapt(self.payload),self.payload)
        self.assertEqual(hashlib.sha256(self.payload).hexdigest(),policy.INPUT_SHA256)
        self.assertEqual(policy.adapt(b'arbitrary\r\n'),b'arbitrary\r\n')

    def test_only_five_unique_adaptations_and_four_usb_reset_groups(self):
        changed=policy.adapt(self.payload,enabled=True).decode()
        for old,new in reversed(policy.changes()):
            self.assertEqual(changed.count(new),1)
            changed=changed.replace(new,old,1)
        self.assertEqual(changed.encode(),self.payload)
        self.assertEqual(len(policy.changes()),5)

    def test_generated_input_identity_drift_is_fatal(self):
        with self.assertRaisesRegex(ValueError,'identity drift'):
            policy.adapt(self.payload+b'\n',enabled=True)

    def test_anchor_drift_is_fatal_even_if_identity_check_is_separately_bypassed(self):
        old,new=policy.changes()[1]
        for text in ('',old+'\n'+old):
            with self.subTest(text=text),self.assertRaisesRegex(ValueError,'anchor drift'):
                policy.once(text,old,new)

    def test_prepare_and_reverse_verification_reject_every_artifact_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            stage=Path(directory)
            for relative in (policy.FIFO,policy.SOURCE,policy.TOOL):
                target=stage/relative;target.parent.mkdir(parents=True,exist_ok=True)
                if relative==policy.FIFO:target.write_bytes(self.payload)
                else:shutil.copyfile(ROOT/relative,target)
            record=policy.prepare(ROOT,stage,enabled=True)
            self.assertTrue(policy.verify_prepared(stage,record)['prepared_identity_verified'])
            for relative in (policy.FIFO,policy.SOURCE,policy.TOOL):
                p=stage/relative;old=p.read_bytes();p.write_bytes(old+b'\n')
                with self.subTest(relative=relative),self.assertRaises(ValueError):
                    policy.verify_prepared(stage,record)
                p.write_bytes(old)
            self.assertIsNone(policy.prepare(ROOT,stage))

    def test_explicit_configuration_requires_metadata_source_and_real_policy(self):
        expected=dict(demo_role='W',audio_policy='native_dual_rate_runtime_v1',usb_fifo_reset_policy=policy.POLICY)
        legacy={key:value for key,value in expected.items() if key!='usb_fifo_reset_policy'}
        with tempfile.TemporaryDirectory() as directory:
            stage=Path(directory)
            for relative in (policy.FIFO,policy.SOURCE,policy.TOOL):
                target=stage/relative;target.parent.mkdir(parents=True,exist_ok=True)
                if relative==policy.FIFO:target.write_bytes(self.payload)
                else:shutil.copyfile(ROOT/relative,target)
            self.assertFalse(policy.verify_demo_selection(stage,legacy,None,[],expected_configuration=expected)['explicit_local_release_selected'])
            record=policy.prepare(ROOT,stage,enabled=True)
            self.assertTrue(policy.verify_demo_selection(stage,expected,record,[policy.SOURCE],expected_configuration=expected)['explicit_local_release_selected'])
            for config,evidence,selected in (
                (expected,None,[policy.SOURCE]),(expected,record,[]),
                (expected,record,[policy.SOURCE,policy.SOURCE]),(legacy,record,[policy.SOURCE]),
                (legacy,None,[]),(dict(expected,usb_fifo_reset_policy='forged'),record,[policy.SOURCE]),
                (dict(expected,audio_policy='changed'),record,[policy.SOURCE]),
            ):
                with self.subTest(config=config,evidence=evidence),self.assertRaises(ValueError):
                    policy.verify_demo_selection(stage,config,evidence,selected,expected_configuration=expected)
            for key,value in (('write_release_usb_edges',1),('hardware_tested',True),
                    ('async_assertion_preserved',False),('false_paths_added',True),('enabled',False)):
                altered=copy.deepcopy(record);altered[key]=value
                with self.subTest(field=key),self.assertRaises(ValueError):
                    policy.verify_demo_selection(stage,expected,altered,[policy.SOURCE],expected_configuration=expected)


if __name__=='__main__':unittest.main()
