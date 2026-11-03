#!/usr/bin/env python3
"""Actual batch PC release aliases, exact early fanout, and strict later gates."""
from pathlib import Path
import copy
import hashlib
import json
import os
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.workstation_native_protocol_audit import protocol_netlist,audit_native_protocol
from tools.workstation_runtime_pcm_cdc import Graph
from tools.workstation_task3_root_reset_audit import audit_root_startup
from tools.workstation_task3_native_held import audit_direct_held_boundaries,release_from_clear
from tools.workstation_task3_peripheral_releases_audit import (
    audit_peripheral_releases,PAIRED_CPU_SOURCE_CLOSURE,PAIRED_CPU_DESTINATION_CLOSURE)
from tools.workstation_task3_m_paired_releases_audit import audit_paired_release_sdc,CHAINS


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ActualBatchPcReleases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.actual={};cls.before={}
        for label in ('BATCH','OLD'):
            selected=os.environ.get('GW138K_TASK3_PC_RELEASE_'+label+'_STAGE')
            if not selected:
                raise unittest.SkipTest('explicit actual batch and old M stages required; no cache fallback')
            stage=Path(selected).resolve();vg=stage/'impl/gwsynthesis/custom_138k_integration.vg'
            n=protocol_netlist(vg.read_text(),mapping='synthesis')
            root=audit_root_startup(n,stage=stage)
            native=audit_native_protocol(n,profile='m-task3-direct',mapping='synthesis')
            held=audit_direct_held_boundaries(n,native,root=root)
            cls.actual[label]=dict(n=n,stage=stage,root=root,native=native,held=held)
            cls.before.update({str(p):sha(p) for p in (vg,stage/'constraints/custom_138k.sdc',
                *(stage/p for p in root['source_sha256']))})
        for p in (Path(__file__),*(ROOT/'tools'/name for name in (
            'workstation_task3_native_held.py','workstation_task3_root_reset_audit.py',
            'workstation_task3_phone_batch_mapped_m.py',
            'workstation_task3_peripheral_releases_audit.py',
            'workstation_task3_m_paired_releases_audit.py'))):
            cls.before[str(p)]=sha(p)
        cls.evidence=dict(positive={label:row['held'] for label,row in cls.actual.items()},
            rejections=[],batch_full_held_CDC_accepted=False,full_TF_CDC_accepted=False,
            historical_consumer_seals_changed=None,physical_CDC_accepted=False,
            routed_timing_verified=False,hardware_tested=False)

    def setUp(self):type(self).result=self._outcome.result

    @classmethod
    def tearDownClass(cls):
        unchanged=cls.before=={p:sha(p) for p in cls.before}
        target=os.environ.get('GW138K_TASK3_PC_RELEASE_EVIDENCE')
        if target:Path(target).write_text(json.dumps(dict(cls.evidence,
            passed=cls.result.wasSuccessful() and unchanged,input_sha256=cls.before,
            inputs_unchanged=unchanged,negative_control_count=len(cls.evidence['rejections'])),indent=2)+'\n')
        assert unchanged,'actual candidate or auditor changed during checks'

    def rejected(self,label,call,pattern=None):
        with self.assertRaises(ValueError) as error:call()
        if pattern:self.assertIn(pattern,str(error.exception))
        self.evidence['rejections'].append(dict(case=label,rejected=True,error=str(error.exception)))

    def test_01_actual_distinct_root_and_observer_chains(self):
        b=self.actual['BATCH'];o=self.actual['OLD']
        src=b['held']['pc_actual_reset']['releases']['source']
        dst=b['held']['pc_actual_reset']['releases']['destination']
        self.assertEqual(src['stages'][-1],'u_task3_m_final_tap/destination_release_2_s0')
        self.assertEqual(dst['stages'],[f'u_task3_m_panic_epoch/source_release_{i}_s0' for i in range(3)])
        self.assertTrue(src['reviewed_pll_initializer_and_tf_first_edge_merge'])
        self.assertEqual(o['held']['pc_actual_reset']['releases']['source']['stages'][-1],
            'u_task3_m_pcm_commands/p_release_2_s0')
        self.assertNotEqual(src['stages'][-1],Graph(b['n']).group('u_task3_m_pcm_commands','p_release',3)[2])
        for index in (0,1):
            new=src['exact_early_consumer_closures'][index]
            old=o['held']['pc_actual_reset']['releases']['source']['exact_early_consumer_closures'][index]
            new_ends=dict(new['ff_endpoints']);old_ends=dict(old['ff_endpoints'])
            if index==1:
                del new_ends[src['stages'][2]+'/D']
                del old_ends[o['held']['pc_actual_reset']['releases']['source']['stages'][2]+'/D']
            self.assertEqual(new_ends,old_ends)
            self.assertEqual(new['primitive_endpoints'],old['primitive_endpoints'])
            self.assertEqual(new['top_output_endpoints'],old['top_output_endpoints'])

    def test_02_release_equations_and_exact_early_consumers(self):
        row=self.actual['BATCH'];n=row['n'];r=row['root'];native=row['native']
        sources=row['held']['pc_actual_reset']['releases']
        cases=[]
        for side in ('source','destination'):
            regs=sources[side]['stages'];owners=sources[side]['owners']
            cases.extend((side+' '+label,p,part,key,value) for label,p,part,key,value in (
                ('first CE',regs[0],'ports','CE',"1'b0"),
                ('middle bypass',regs[1],'ports','D',"1'b1"),
                ('last clock',regs[2],'ports','CLK',"1'b0"),
                ('first INIT',regs[0],'parameters','INIT',"1'b1"),
                ('common assertion removed',regs[2],'ports','CLEAR',"1'b0"),
                ('functional reset bypass',owners[0],'ports','CLEAR',"1'b0")))
        cases.extend([
            ('TF first-edge consumer removed','u_tf_audio/frames/source_alive_sync_0_s0','ports','D',"1'b0"),
            ('PLL control consumer removed','u_cpu_pll/pll_control_9_s0','ports','D',"1'b0")])
        for label,p,part,key,value in cases:
            original=copy.deepcopy(n.cells[p])
            try:
                n.cells[p][part][key]=value
                self.rejected(label,lambda:audit_direct_held_boundaries(n,native,root=r))
            finally:n.cells[p]=original
        for index in (0,1):
            for domain in ('clk_50m','audio_clk'):
                p='audit_extra_consumer'
                n.cells[p]=dict(kind='DFFCE',parameters={'INIT':"1'b0"},ports=dict(
                    Q='audit_extra_q',D=n.pin(sources['source']['stages'][index],'Q'),
                    CLK=domain,CLEAR="1'b0",CE="1'b1"))
                n.scopes[p]=''
                try:self.rejected('stage '+str(index)+' extra consumer '+domain,
                    lambda:audit_direct_held_boundaries(n,native,root=r),'extra consumer/bypass')
                finally:del n.cells[p];del n.scopes[p]

    def test_03_only_exact_new_mapping_and_batch_proof(self):
        for label,row in self.actual.items():
            n=row['n'];g=Graph(n)
            src=row['held']['pc_actual_reset']['releases']['source']
            clear=n.pin(src['owners'][0],'CLEAR')
            self.rejected(label+' cannot borrow opposite alias policy',lambda:release_from_clear(
                n,g,clear,row['root']['root_q'],'clk_50m',paired=True,batch=label!='BATCH'),
                'extra consumer/bypass')
        row=self.actual['BATCH'];n=row['n'];r=row['root']
        for proof in ({},dict(mapped_structure_verified=False),
                      dict(mapped_structure_verified=True,policy='unreviewed')):
            forged=dict(r,batch_mapped_structure=proof)
            for name,call in (
                ('held',lambda:audit_direct_held_boundaries(n,row['native'],root=forged)),
                ('peripheral',lambda:audit_peripheral_releases(n,root=forged)),
                ('release_SDC',lambda:audit_paired_release_sdc(n,
                    (row['stage']/'constraints/custom_138k.sdc').read_text(),root=forged))):
                self.rejected(name+' missing/invalid batch mapped proof',call,'batch mapped boundary required')

    def test_04_old_complete_consumer_seals_still_reject(self):
        # Freeze the historical policy independently of its continued
        # rejection. A refreshed hash must not quietly satisfy this check.
        expected=(
            'a4847d89534677bb0aab55b1bd2ee7cf0ef49b06a8b78f90b2f460d6ff6756d1',
            'cbe5c18b92d425f53154665980cd894e3d58f10fb7a2b9ec220a606cb60b66c3',
            '495453ad101e7567b95feca4b879a69a045f3b3fe0e743bd64fe4147be66d8ab',
            '401f63730ad5f2c0b9be436d56a108982f2db213ca9211b85b50264fbaabe052')
        self.assertEqual(tuple(row[-1] for row in CHAINS),expected)
        self.assertEqual((PAIRED_CPU_SOURCE_CLOSURE,PAIRED_CPU_DESTINATION_CLOSURE),expected[:2])
        self.evidence['historical_consumer_seals_changed']=False
        for label,row in self.actual.items():
            n=row['n'];r=row['root']
            self.rejected(label+' paired final source consumer seal',lambda:audit_paired_release_sdc(
                n,(row['stage']/'constraints/custom_138k.sdc').read_text(),root=r),
                'complete consumer inventory changed: cpu-source')
            self.rejected(label+' peripheral final consumer seal',
                lambda:audit_peripheral_releases(n,root=r),'paired final release complete endpoint inventory changed')


if __name__=='__main__':unittest.main()
