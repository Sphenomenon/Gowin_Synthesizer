#!/usr/bin/env python3
"""Explicit chorus source gates and optional immutable actual-VG negatives."""
from pathlib import Path
import copy
import json
import os
import sys
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_ble_ddr_chorus_cdc_scope import (
    SCOPE, CANDIDATE, CANDIDATE_INPUT_SHA256, PROFILE, PROFILE_SOURCE, validate_profile,
    validate_compiled_inputs, validate_staged_inputs, SERIAL_METADATA_HELPER_SHA256,
)
from tools.workstation_ble_ddr_cdc_scope import validate_profile as serial_profile
from tools.workstation_ble_ddr_prefix_cdc_scope import (validate_profile as c7_profile,
    CANDIDATE as C7_CANDIDATE, CANDIDATE_INPUT_SHA256 as C7_INPUT_SHA256)
from tools.workstation_ble_ddr_chorus_cdc_scope import SOURCE_SHA256
from tools.workstation_chorus_provenance import source_bundle as chorus_metadata
from tools.workstation_ble_ddr_chorus_cdc_endpoints import validate_synthesis_binding as chorus_VG
from tools.workstation_ble_ddr_prefix_cdc_endpoints import validate_synthesis_binding as c7_VG
from tools.workstation_ble_recording_policy import metadata as ble_metadata
from tools.workstation_recording_policy import metadata as recording_metadata
from tools.workstation_runtime_counter import metadata as counter_metadata, selection_evidence, LEGACY, NATIVE
from tools.workstation_runtime_shared_cdc import validate_precision_profile, audit_selected_shared
from tools.workstation_usb2_owner_reset import validate_profile as usb_profile, OwnerResetNetlist
from tools.workstation_recording_phase1_cdc import audit_netlist as phase1, D
from tools.workstation_ble_ddr_cdc_inventory import audit_netlist as inventory, B, F, A
from tools.workstation_runtime_pcm_cdc import Graph, TOP
from tools.workstation_runtime_clock_audit import VG_RELATIVE, verify_synthesis_identity, file_sha


class ChorusMetadataGate(unittest.TestCase):
    def setUp(self):
        self.profile = dict(schema=1, profile=PROFILE, revision=2, profile_source=PROFILE_SOURCE,
            profile_sha256='0'*64, candidate_identity=CANDIDATE, candidate_input_sha256=CANDIDATE_INPUT_SHA256,
            configuration=json.loads((ROOT/PROFILE_SOURCE).read_text())['configuration'],
            recording=dict(recording_metadata(ble_raw_ddr=True), address_map={}),
            ble_recording_storage=dict(ble_metadata(), adaptation={}),
            runtime_audio=dict(counter_cdc=counter_metadata(ROOT),chorus_source=chorus_metadata(ROOT)),
            recognition=dict(policy='disabled_cnn_and_follow_v1', music_analysis_enabled=False,
                cnn_score_follow_enabled=False, constraints=dict(enabled=False)))

    def test_explicit_chorus_metadata_and_unchanged_serial_helper(self):
        self.assertEqual(file_sha(ROOT/'tools/workstation_ble_ddr_cdc_scope.py'), SERIAL_METADATA_HELPER_SHA256)
        self.assertEqual(validate_profile(ROOT,self.profile)['scope'],SCOPE)
        validate_precision_profile(ROOT,self.profile,SCOPE)
        usb_profile(ROOT,self.profile,PROFILE,scope=SCOPE)
        with self.assertRaises(ValueError):
            validate_precision_profile(ROOT,self.profile,'runtime-r00-no-local-panel-v1')
        with self.assertRaises(ValueError):
            usb_profile(ROOT,self.profile,PROFILE)

    def test_wrong_candidate_and_counter_policy_rejected(self):
        changes=[
            ('old candidate',lambda p:p.update(candidate_identity='serial277')),
            ('wrong input identity',lambda p:p.update(candidate_input_sha256='0'*64)),
            ('revision1',lambda p:p.update(revision=1)),
            ('configuration addition',lambda p:p['configuration'].update(extra_policy=True)),
            ('missing native policy',lambda p:p['runtime_audio'].pop('counter_cdc')),
            ('wrong source',lambda p:p['runtime_audio']['counter_cdc'].update(source=LEGACY)),
            ('wrong source hash',lambda p:p['runtime_audio']['counter_cdc'].update(source_sha256='0'*64)),
            ('false physical acceptance',lambda p:p['runtime_audio']['counter_cdc'].update(physical_timing_verified=True)),
            ('missing BLE',lambda p:p.pop('ble_recording_storage')),
            ('c7 candidate',lambda p:p.update(candidate_identity=C7_CANDIDATE,candidate_input_sha256=C7_INPUT_SHA256)),
            ('missing Chorus provenance',lambda p:p['runtime_audio'].pop('chorus_source')),
            ('wrong Chorus policy',lambda p:p['runtime_audio']['chorus_source'].update(policy='unreviewed')),
            ('wrong Chorus RTL hash',lambda p:p['runtime_audio']['chorus_source'].update(current_source_sha256='0'*64)),
            ('Chorus false hardware inheritance',lambda p:p['runtime_audio']['chorus_source'].update(hardware_acceptance_inherited=True)),
        ]
        for label,change in changes:
            p=copy.deepcopy(self.profile);change(p)
            with self.subTest(case=label),self.assertRaises(ValueError):validate_profile(ROOT,p)


    def test_c7_modules_unchanged_and_cross_candidate_rejected(self):
        for path,expected in {
            'tools/workstation_ble_ddr_prefix_cdc_scope.py':'e1f4b0421c2e567cea8c18841e33793593482472d8315709245ae9c32a9004c6',
            'tools/workstation_ble_ddr_prefix_cdc_endpoints.py':'252762edbf544f44c570f1967a5d6a81e8ec95b18c883d62fdc5d2f4a5d282da',
        }.items():
            self.assertEqual(file_sha(ROOT/path),expected,path)
        with self.assertRaisesRegex(ValueError,'exact prefix candidate'):
            c7_profile(ROOT,self.profile)
        old=copy.deepcopy(self.profile);old.update(candidate_identity=C7_CANDIDATE,candidate_input_sha256=C7_INPUT_SHA256)
        with self.assertRaisesRegex(ValueError,'exact Chorus prefix candidate'):
            validate_profile(ROOT,old)

    def test_every_maintained_source_hash_fail_closed(self):
        from tools import workstation_ble_ddr_chorus_cdc_scope as module
        original=module.file_sha
        for source in SOURCE_SHA256:
            def mutant(path):
                return '0'*64 if Path(path)==ROOT/source else original(path)
            with self.subTest(source=source),mock.patch.object(module,'file_sha',side_effect=mutant),self.assertRaises(ValueError):
                validate_profile(ROOT,self.profile)


class PreparedChorusGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        value=os.environ.get('GW138K_CHORUS_CDC_STAGE')
        if not value:raise unittest.SkipTest('explicit fixed chorus stage required; no prepare/EDA fallback')
        cls.stage=Path(value)
        cls.profile=json.loads((cls.stage.parents[1]/'workstation_profile.json').read_text())
        cls.integration=json.loads((cls.stage.parents[1]/'integration_inputs.json').read_text())
        cls.enabled=[e.get('path') for e in ET.parse(cls.stage/'Prj1.gprj').find('FileList') if e.get('enable')=='1']
        cls.original={str(cls.stage/p):file_sha(cls.stage/p) for p in cls.profile['staged_input_sha256']}

    @classmethod
    def tearDownClass(cls):
        if cls.original!={p:file_sha(p) for p in cls.original}:raise AssertionError('original596stage bytes changed')

    def test_new_stage_passes_and_old_serial_gate_rejects(self):
        result=validate_profile(ROOT,self.profile,stage=self.stage)
        self.assertEqual(result['staged_input_selection']['staged_input_count'],596)
        self.assertEqual(result['compilation_selection']['enabled_input_count'],269)
        with self.assertRaisesRegex(ValueError,'serial-counter compilation selection changed'):
            serial_profile(ROOT,self.profile,stage=self.stage)
        with self.assertRaisesRegex(ValueError,'exact prefix candidate'):
            c7_profile(ROOT,self.profile,stage=self.stage)
        with self.assertRaisesRegex(ValueError,'actual reviewed VG identity required'):
            c7_VG(self.stage)
        chorus_VG(self.stage)

    def test_compiled_identity_order_and_bytes_mutants(self):
        p,e=self.profile,self.enabled
        actual={path:p['enabled_inputs'][path]['sha256'] for path in e}
        validate_compiled_inputs(p,e,actual)
        changes=[
            ('serial enabled instead',lambda q,x,a:(x.__setitem__(x.index(NATIVE),LEGACY),q['enabled_inputs'].__setitem__(LEGACY,q['enabled_inputs'].pop(NATIVE)))),
            ('both enabled',lambda q,x,a:(x.append(LEGACY),q['enabled_inputs'].__setitem__(LEGACY,{}))),
            ('duplicate enabled',lambda q,x,a:x.append(NATIVE)),
            ('enabled order',lambda q,x,a:x.reverse()),
            ('compiled provenance',lambda q,x,a:q['enabled_inputs'][NATIVE].update(sha256='0'*64)),
            ('actual compiled bytes',lambda q,x,a:a.update({NATIVE:'0'*64})),
        ]
        for label,change in changes:
            q,x,a=copy.deepcopy(p),e.copy(),actual.copy();change(q,x,a)
            with self.subTest(case=label),self.assertRaises(ValueError):validate_compiled_inputs(q,x,a)

    def test_all_staged_map_and_uncompiled_bytes_mutants(self):
        p,i=self.profile,self.integration
        actual=p['staged_input_sha256'].copy()
        validate_staged_inputs(p,i,actual)
        for label,change in [
            ('profile596map',lambda q,j,a:q['staged_input_sha256'].update({LEGACY:'0'*64})),
            ('integration596map',lambda q,j,a:j['staged_input_sha256'].update({LEGACY:'0'*64})),
            ('disabled serial actual bytes',lambda q,j,a:a.update({LEGACY:'0'*64})),
            ('missing staged file',lambda q,j,a:a.pop(LEGACY)),
        ]:
            q,j,a=copy.deepcopy(p),copy.deepcopy(i),actual.copy();change(q,j,a)
            with self.subTest(case=label),self.assertRaises(ValueError):validate_staged_inputs(q,j,a)

    def test_counter_binding_mutants(self):
        selection_evidence(self.stage,self.integration)
        for label,change in [
            ('native metadata missing',lambda i:i['runtime_audio'].pop('counter_cdc')),
            ('wrong disabled parent replacement',lambda i:i['replaced_compilation_inputs'][LEGACY].update(replacement=LEGACY)),
            ('wrong copied source identity',lambda i:i['copied_sources_sha256'].update({NATIVE:'0'*64})),
            ('native absent from integration compilation',lambda i:i['enabled_inputs'].remove(NATIVE)),
            ('staged serial bytes',lambda i:i['staged_input_sha256'].update({LEGACY:'0'*64})),
        ]:
            i=copy.deepcopy(self.integration);change(i)
            with self.subTest(case=label),self.assertRaises(ValueError):selection_evidence(self.stage,i)

    def test_integration_and_staged_chorus_provenance_not_inherited(self):
        from tools import workstation_ble_ddr_chorus_cdc_scope as module
        original=module.chorus_metadata
        def wrong_staged(path):
            result=original(path)
            if Path(path)==self.stage:result=dict(result,policy='unreviewed')
            return result
        with mock.patch.object(module,'chorus_metadata',side_effect=wrong_staged),self.assertRaisesRegex(ValueError,'integration/staged explicit Chorus provenance'):
            validate_profile(ROOT,self.profile,stage=self.stage)

    def test_duplicate_or_wrong_owner_declarations(self):
        for label,change in [
            ('duplicate disabled serial',lambda files:files.append(copy.deepcopy(next(e for e in files if e.get('path')==LEGACY)))),
            ('duplicate native',lambda files:files.append(copy.deepcopy(next(e for e in files if e.get('path')==NATIVE)))),
            ('both enabled',lambda files:next(e for e in files if e.get('path')==LEGACY).set('enable','1')),
            ('native disabled',lambda files:next(e for e in files if e.get('path')==NATIVE).set('enable','0')),
        ]:
            project=ET.parse(self.stage/'Prj1.gprj');change(project.find('FileList'))
            with self.subTest(case=label),mock.patch('tools.workstation_ble_ddr_chorus_cdc_scope.ET.parse',return_value=project),self.assertRaises(ValueError):
                validate_profile(ROOT,self.profile,stage=self.stage)


class ActualChorus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stage,evidence=os.environ.get('GW138K_CHORUS_CDC_STAGE'),os.environ.get('GW138K_CHORUS_CDC_PROCESS')
        if not stage or not evidence:raise unittest.SkipTest('completed sealed chorus VG required; no EDA fallback')
        cls.stage,cls.evidence=Path(stage),Path(evidence)
        cls.before=verify_synthesis_identity(cls.stage,cls.evidence)
        cls.n=OwnerResetNetlist((cls.stage/VG_RELATIVE).read_text(),TOP)
        cls.baseline=inventory(cls.n,scope=SCOPE)
        cls.phase1_baseline=phase1(cls.n,scope=SCOPE)
        cls.mutations=[]

    @classmethod
    def tearDownClass(cls):
        if cls.before!=verify_synthesis_identity(cls.stage,cls.evidence):raise AssertionError('original synthesis inputs changed')
        output=os.environ.get('GW138K_CHORUS_CDC_TEST_EVIDENCE')
        if output:Path(output).write_text(json.dumps(dict(schema=1,synthesis=cls.before,mutations=cls.mutations,
            mutation_count=len(cls.mutations),original_VG_rewritten=False,original_SDC_rewritten=False,
            eda_invoked=False,hardware_operated=False,physical_cdc_accepted=False,deployment_allowed=False),indent=2,sort_keys=True)+'\n')

    def test_inventory_and_nonacceptance(self):
        r=self.baseline
        self.assertEqual((r['ordinary_pair_count'],r['gray_bits'],r['raw_payload_logical_bits'],r['raw_payload_mapped_source_FFs']),(13,50,528,524))
        self.assertEqual(len(r['complete_source_fanout']),42)
        self.assertEqual((self.phase1_baseline['complete_reviewed_FF_count'],self.phase1_baseline['gray_first_stage_bits'],self.phase1_baseline['payload_bits']),(425,42,82))
        self.assertEqual(self.phase1_baseline['scope'],SCOPE)
        for key in ('recording_cdc_complete','full_reset_accepted','physical_cdc_accepted','constraints_complete',
                    'routed_timing_verified','deployment_allowed','release_ready'):
            self.assertFalse(r[key],key)

    def test_actual_register_and_complete_closure_mutants(self):
        n=self.n;g=Graph(n);reg=lambda s,t,b=None:g.register(s,t,b)
        cases=[
            ('raw first D disconnected',reg(B,'command_req_meta'),'D',"1'b0"),
            ('raw first clock changed',reg(B,'command_req_meta'),'CLK','clk_50m'),
            ('raw first CE conditional',reg(B,'command_req_meta'),'CE',"1'b0"),
            ('raw second D bypass',reg(B,'command_req_sync'),'D',"1'b0"),
            ('Gray MSB source changed',reg(F,'read_gray_meta',8),'D',n.cells[reg(F,'read_gray',7)]['ports']['Q']),
            ('Gray first extra CE consumer',reg(F,'write_binary',0),'CE',n.cells[reg(F,'read_gray_meta',0)]['ports']['Q']),
            ('payload source clock changed',reg(B,'command_generation',0),'CLK','memory_clk'),
            ('held payload extra consumer',reg(B,'cancel_seen'),'CE',n.cells[reg(B,'command_generation',0)]['ports']['Q']),
            ('seal ready bypass',reg('u_recording/seal_cdc','ready_meta'),'D',"1'b1"),
            ('authority heartbeat source swap',reg(A,'gray_meta',0),'D',n.cells[reg(A,'memory_gray',1)]['ports']['Q']),
            ('raw control release CE changed',reg('u_usb_pll/u_pll_init','enable_r',0),'CE',"1'b0"),
        ]
        for label,path,pin,value in cases:
            old=n.cells[path]['ports'][pin];n.cells[path]['ports'][pin]=value
            try:
                with self.subTest(case=label),self.assertRaises(ValueError) as raised:inventory(n,scope=SCOPE)
                self.mutations.append(dict(case=label,rejected=hasattr(raised,'exception'),error=str(getattr(raised,'exception','not rejected'))))
            finally:n.cells[path]['ports'][pin]=old
        path=reg(D,'sync_value',0);old=n.cells[path]['ports']['CE']
        n.cells[path]['ports']['CE']=n.cells[reg(D,'destination_release',1)]['ports']['Q']
        try:
            with self.assertRaisesRegex(ValueError,'seal/reset alias complete closure') as raised:phase1(n,scope=SCOPE)
            self.mutations.append(dict(case='shared seal reset extra CE consumer',rejected=True,error=str(raised.exception)))
        finally:n.cells[path]['ports']['CE']=old
        inventory(n,scope=SCOPE);phase1(n,scope=SCOPE)

    def test_new_video_alias_unique_producer_and_mutants(self):
        n=self.n;g=Graph(n)
        profile=json.loads((self.stage.parents[1]/'workstation_profile.json').read_text())
        sdc=(self.stage/'constraints/custom_138k.sdc').read_text()
        run=lambda:audit_selected_shared(ROOT,self.stage,n,Graph(n),sdc,profile,precision_profile=SCOPE)
        self.assertEqual(run()['installed_shared_constraint_count'],88)
        first=g.register('u_video','flags_meta',3)
        source=g.register('u_video/u_scanout','front_valid')
        for label,path,pin,value in [
            ('new front-valid first D disconnect',first,'D',"1'b0"),
            ('new front-valid declared source clock changed',source,'CLK','clk_50m'),
        ]:
            old=n.cells[path]['ports'][pin];n.cells[path]['ports'][pin]=value
            try:
                with self.subTest(case=label),self.assertRaises(ValueError) as raised:run()
                self.mutations.append(dict(case=label,rejected=hasattr(raised,'exception'),error=str(getattr(raised,'exception','not rejected'))))
            finally:n.cells[path]['ports'][pin]=old

    def test_phase1_receivers_and_complete_closure_mutants(self):
        from tools.workstation_recording_phase1_cdc import F as PCM_F, A as APB_A
        n=self.n;g=Graph(n);reg=lambda s,t,b=None:g.register(s,t,b)
        cases=[
            ('phase1 Gray first D disconnected',reg(PCM_F,'read_gray_meta',0),'D',"1'b0"),
            ('phase1 Gray first CE conditional',reg(PCM_F,'read_gray_meta',0),'CE',"1'b0"),
            ('phase1 Gray first clock changed',reg(PCM_F,'read_gray_meta',0),'CLK','memory_clk'),
            ('phase1 APB declared source clock changed',reg(APB_A,'request_held',0),'CLK','memory_clk'),
            ('phase1 payload extra CE consumer',reg(APB_A,'state',0),'CE',n.cells[reg(APB_A,'request_held',0)]['ports']['Q']),
        ]
        for label,path,pin,value in cases:
            old=n.cells[path]['ports'][pin];n.cells[path]['ports'][pin]=value
            try:
                if label=='phase1 payload extra CE consumer':
                    self.assertEqual(n.pin(path,pin),n.pin(reg(APB_A,'request_held',0),'Q'))
                with self.subTest(case=label),self.assertRaises(ValueError) as raised:phase1(n,scope=SCOPE)
                self.mutations.append(dict(case=label,rejected=hasattr(raised,'exception'),error=str(getattr(raised,'exception','not rejected'))))
            finally:n.cells[path]['ports'][pin]=old
        phase1(n,scope=SCOPE)


if __name__=='__main__':unittest.main()
