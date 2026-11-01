#!/usr/bin/env python3
"""Actual DIRECT preprocess/elaboration and destructive source-policy probes."""
from pathlib import Path
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import workstation_profile as profiles
from tools import workstation_task3_tf_direct as direct
from tools import workstation_task3_tf_storage_selection as storage
from tools.workstation_task3_w_media_profile import inverse_top as inverse_w

class DirectStorageSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence={};cls.mutations=[];cls.outcomes=[]
        cls.config=profiles.specification(profiles.TASK3_M_DIRECT_NAME)['configuration']
        cls.provider=profiles.specification(profiles.TASK3_M_DIRECT_NAME)['provider']

    def run(self,result=None):
        result=super().run(result)
        belongs=lambda test:test is self or getattr(test,'test_case',None) is self
        problems={kind:[detail for test,detail in getattr(result,kind) if belongs(test)]
                  for kind in ('failures','errors','skipped','expectedFailures')}
        problems['unexpectedSuccesses']=[str(test) for test in result.unexpectedSuccesses if belongs(test)]
        self.__class__.outcomes.append(dict(test=self._testMethodName,
            passed=not any(problems.values()),**problems))
        return result

    @classmethod
    def tearDownClass(cls):
        target=os.environ.get('GW138K_TASK3_DIRECT_STORAGE_EVIDENCE')
        if target:
            expected=unittest.defaultTestLoader.getTestCaseNames(cls)
            complete=(len(cls.outcomes)==len(expected) and
                      {row['test'] for row in cls.outcomes}==set(expected))
            Path(target).write_text(json.dumps(dict(
                passed=complete and all(row['passed'] for row in cls.outcomes),
                expected_tests=expected,unittest_results=cls.outcomes,**cls.evidence,
                rejected_mutations=cls.mutations,hardware_tested=False,
                synthesis_verified=False,physical_cdc_verified=False),indent=2)+'\n')

    def stage(self,path):
        files=(*direct.SOURCES,*direct.DEPENDENCIES,self.provider,storage.TOP,'rtl/music/music_async_fifo.sv',
            'rtl/workstation/workstation_profile_runtime.sv')
        for relative in dict.fromkeys(files):
            target=path/relative;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/relative,target)
        rows=''.join('<File path="'+p+'" enable="1" />' for p in (*direct.SOURCES,self.provider))
        (path/'Prj1.gprj').write_text('<Project><FileList>'+rows+'</FileList></Project>')

    def test_01_exact_inverse_chain_and_configuration(self):
        raw=(ROOT/storage.TOP).read_text()
        prior=storage.inverse_top(ROOT,raw)
        self.assertEqual(storage.digest(prior),storage.PARENT_SHA256)
        old=inverse_w(ROOT,prior)
        self.assertEqual(storage.digest(old),'2bd14a9c81c28817dc0fd2bf39a87d208f0344f7f1c8f06571953bc2550f3cd0')
        self.assertEqual(storage.inverse_top(ROOT,prior),prior)
        self.assertEqual(storage.configuration_selection(self.config),dict(
            policy=direct.STORAGE_POLICY,VERIFY_DATA_CRC=1,FAT_SECTOR_CACHE=1,sdc_revision=3))
        for key,value in (('tf_storage_policy',None),('tf_storage_policy','unverified'),
                          ('tf_sdc_revision',1),('tf_sdc_revision',2),('tf_sdc_revision',True)):
            changed=copy.deepcopy(self.config)
            if value is None:changed.pop(key)
            else:changed[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                storage.configuration_selection(changed)
            self.mutations.append(dict(case='configuration '+key,value=value,rejected=True))
        self.evidence['exact_inverse']=dict(native_sha256=storage.digest(raw),
            a070_top_sha256=storage.digest(prior),old_W_parent_sha256=storage.digest(old),
            old_W_reference_bytes_unchanged=True,verification_only=True)

    def test_02_actual_preprocess_and_crc_cache_elaboration(self):
        with tempfile.TemporaryDirectory(prefix='task3-direct-storage-') as temp:
            stage=Path(temp);self.stage(stage)
            selected=storage.prepared_selection(ROOT,stage,self.config)
            output=stage/'actual.pp'
            result=subprocess.run(['iverilog','-g2012','-E','-I',str(ROOT),'-o',str(output),self.provider],
                cwd=stage,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            text=output.read_text()
            self.assertEqual(len(re.findall(r'workstation_tf_direct_runtime_service\s*#\(\s*'
                r'\.SEPARATE_COMMON_RESET\(1\),\s*\.VERIFY_DATA_CRC\(1\),'
                r'\.FAT_SECTOR_CACHE\(1\)\)\s*u_tf_audio\(',text)),1)
            self.assertNotIn('workstation_tf_runtime_service u_tf_audio(',text)
            self.assertNotIn('workstation_cnn_task_service',text)
            compiled=stage/'actual.vvp'
            result=subprocess.run(['iverilog','-g2012','-s','workstation_tf_direct_runtime_service',
                '-Pworkstation_tf_direct_runtime_service.VERIFY_DATA_CRC=1',
                '-Pworkstation_tf_direct_runtime_service.FAT_SECTOR_CACHE=1','-o',str(compiled),
                *direct.SOURCES,'rtl/music/music_async_fifo.sv'],
                cwd=stage,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            compiled_text=compiled.read_text()
            self.assertIn('"g_fat_cache"',compiled_text)
            self.assertIn('"workstation_tf_fat_sector_cache_v1"',compiled_text)
            self.assertIn('"g_data_crc"',compiled_text)
            self.assertIn('"workstation_tf_sd_crc16_v1"',compiled_text)
            self.assertNotIn('"g_no_fat_cache"',compiled_text)
            self.assertNotIn('"g_no_data_crc"',compiled_text)
            self.evidence['actual_compiler']=dict(preprocessed_native_top_sha256=storage.digest(text),
                explicit_instance_parameters=dict(VERIFY_DATA_CRC=1,FAT_SECTOR_CACHE=1),
                real_CRC_checker_elaborated=True,real_FAT_cache_elaborated=True,
                compiled_sources=selected['source_sha256'],old_owner_and_W_CNN_unselected=True)

    def test_03_real_staged_source_and_compilation_negative_controls(self):
        with tempfile.TemporaryDirectory(prefix='task3-direct-storage-negative-') as temp:
            stage=Path(temp);self.stage(stage)
            storage.prepared_selection(ROOT,stage,self.config)
            top=stage/storage.TOP;original=top.read_text()
            for label,before,after in (
                ('CRC disabled','.VERIFY_DATA_CRC(1)','.VERIFY_DATA_CRC(0)'),
                ('cache disabled','.FAT_SECTOR_CACHE(1)','.FAT_SECTOR_CACHE(0)'),
                ('common reset disabled','.SEPARATE_COMMON_RESET(1)','.SEPARATE_COMMON_RESET(0)')):
                top.write_text(original.replace(before,after,1))
                try:
                    with self.subTest(case=label),self.assertRaises(ValueError):
                        storage.prepared_selection(ROOT,stage,self.config)
                finally:top.write_text(original)
                self.mutations.append(dict(case=label,rejected=True))
            project=stage/'Prj1.gprj';xml=project.read_text()
            checker='rtl/tf_audio/storage/workstation_tf_sd_crc16_v1.sv'
            cache='rtl/tf_audio/storage/workstation_tf_fat_sector_cache_v1.sv'
            cases=[('checker unselected',xml.replace('path="'+checker+'" enable="1"','path="'+checker+'" enable="0"')),
                ('cache unselected',xml.replace('path="'+cache+'" enable="1"','path="'+cache+'" enable="0"')),
                ('W CNN compiled',xml.replace('</FileList>','<File path="'+direct.UNSELECTED_WORKER_SOURCES[0]+'" enable="1" /></FileList>')),
                ('another provider compiled',xml.replace('</FileList>','<File path="'+profiles.specification(profiles.M_DEMO_NAME)['provider']+'" enable="1" /></FileList>'))]
            for label,changed in cases:
                project.write_text(changed)
                try:
                    with self.subTest(case=label),self.assertRaises(ValueError):
                        storage.prepared_selection(ROOT,stage,self.config)
                finally:project.write_text(xml)
                self.mutations.append(dict(case=label,rejected=True))
            reference=stage/storage.REFERENCE;raw=reference.read_bytes()
            reference.write_bytes(raw+b'\n')
            with self.assertRaises(ValueError):storage.prepared_selection(ROOT,stage,self.config)
            self.mutations.append(dict(case='new inverse reference drift',rejected=True))

if __name__=='__main__':unittest.main()
