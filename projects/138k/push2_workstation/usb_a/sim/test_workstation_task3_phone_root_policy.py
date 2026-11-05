#!/usr/bin/env python3
"""Source admission negatives for the actual M full96 phone guard.

The full mapped root/batch mutation suite remains a separate required check.
An explicit immutable prepared stage is required; there is no cache fallback.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import workstation_task3_root_reset_audit as roots
from tools import workstation_task3_phone_batch_mapped_m as batch
from tools import workstation_task3_phone_identity_compare as phone


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class PhoneRootAdmission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected=os.environ.get('GW138K_TASK3_BATCH_MAPPED_M_STAGE')
        if not selected:
            raise unittest.SkipTest('explicit actual M phone-grouped stage required')
        cls.stage=Path(selected).resolve()
        cls.before={str(p):sha(p) for p in cls.stage.rglob('*') if p.is_file() and
                    'impl' not in p.relative_to(cls.stage).parts}
        artifact=cls.stage.parent.parent/'workstation_profile.json'
        cls.before[str(artifact)]=sha(artifact)
        cls.artifact=json.loads(artifact.read_text())
        if cls.artifact['profile'] not in roots.PHONE_GROUPED_ROOT_PROFILES:
            raise ValueError('actual phone-grouped M candidate required')
        cls.rejections=[]

    @classmethod
    def tearDownClass(cls):
        assert cls.before=={p:sha(p) for p in cls.before},'immutable stage changed'

    def fixture(self,temp):
        output=Path(temp)/'fixture';stage=output/'workstation/Prj1'
        shutil.copytree(self.stage,stage,ignore=shutil.ignore_patterns('impl'))
        artifact=output/'workstation_profile.json'
        artifact.write_text(json.dumps(self.artifact))
        return stage,artifact

    def test_exact_new_source_inverse_and_historical_seals(self):
        proof=batch.source_evidence(self.stage)
        source=proof['root_source']
        self.assertEqual(source['root_mapping_variant'],roots.PHONE_GROUPED_ROOT_VARIANT)
        self.assertEqual(roots.publisher_policy(source)[1],'reset_n')
        self.assertEqual(batch.GROUPED_SOURCE_SHA256[phone.ENDPOINT],phone.REFERENCE_ENDPOINT_SHA256)
        self.assertEqual(roots.GROUPED_ROOT_SOURCES[phone.BOARD],phone.REFERENCE_BOARD_SHA256)
        self.assertEqual(sha(self.stage/phone.ENDPOINT),proof['reviewed_source_sha256'][phone.ENDPOINT])
        phone.restore_endpoint((self.stage/phone.ENDPOINT).read_text())
        phone.restore_board((self.stage/phone.BOARD).read_text())

    def test_profile_and_policy_loans_rejected(self):
        def legacy(p,name):
            p['profile']=name
            p['configuration'].pop('m_phone_identity_compare_policy',None)
        with tempfile.TemporaryDirectory(prefix='task3-phone-root-policy-') as temp:
            stage,artifact=self.fixture(temp)
            changes=[
                ('phone policy missing',lambda p:p['configuration'].pop('m_phone_identity_compare_policy')),
                ('phone policy unknown',lambda p:p['configuration'].update(m_phone_identity_compare_policy='unknown')),
                ('pair policy missing',lambda p:p['configuration'].pop('m_identity_compare_policy')),
                ('new source under old profile',lambda p:legacy(p,roots.GROUPED_ROOT_PROFILE)),
                ('phone policy under old profile',lambda p:p.update(profile=roots.GROUPED_ROOT_PROFILE)),
                ('wrong role',lambda p:p.update(profile='custom138k-workstation-task3-w-paired-checkpoint-v16')),
                ('unreviewed future',lambda p:p.update(profile='custom138k-workstation-task3-m-paired-checkpoint-v17')),
            ]
            for label,change in changes:
                value=deepcopy(self.artifact);change(value);artifact.write_text(json.dumps(value))
                with self.subTest(case=label),self.assertRaises(ValueError):
                    batch.source_evidence(stage)

    def test_wrong_root_variant_cannot_borrow_new_profile(self):
        source=roots.source_binding(self.stage)
        for variant,profile in [
            (roots.GROUPED_ROOT_VARIANT,self.artifact['profile']),
            (roots.TERMINAL_ROOT_VARIANT,self.artifact['profile']),
            (roots.PHONE_GROUPED_ROOT_VARIANT,roots.GROUPED_ROOT_PROFILE),
            (roots.PHONE_GROUPED_ROOT_VARIANT,'custom138k-workstation-task3-w-paired-checkpoint-v16'),
        ]:
            with self.subTest(variant=variant,profile=profile),self.assertRaises(ValueError):
                roots.publisher_policy(dict(source,root_mapping_variant=variant,root_profile=profile))

    def test_partial_comparator_and_board_selection_rejected(self):
        with tempfile.TemporaryDirectory(prefix='task3-phone-root-source-') as temp:
            stage,_=self.fixture(temp)
            for relative,old,new in [
                (phone.ENDPOINT,'byte_group<12','byte_group<11'),
                (phone.ENDPOINT,'82+byte_group*8','83+byte_group*8'),
                (phone.BOARD,phone.BINDING,''),
                (phone.BOARD,phone.BINDING,phone.BINDING.replace('=8','=96')),
            ]:
                path=stage/relative;text=path.read_text();self.assertEqual(text.count(old),1)
                try:
                    path.write_text(text.replace(old,new,1))
                    with self.subTest(source=relative,mutation=old),self.assertRaises(ValueError):
                        batch.source_evidence(stage)
                finally:path.write_text(text)


if __name__=='__main__':
    unittest.main()
