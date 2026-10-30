#!/usr/bin/env python3
"""Optional sealed actual-VG PCM pointer/APB review and in-memory negatives."""
from pathlib import Path
import copy
import inspect
import json
import os
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.workstation_recording_phase1_cdc import (
    A,P,F,D,Graph,TOP,OwnerResetNetlist,audit_netlist,audit_proposal_queries,
    constraint_proposal,validate_sources,
)
from tools.workstation_runtime_clock_audit import verify_synthesis_identity,VG_RELATIVE,file_sha


class ActualRecordingPhase1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stage=os.environ.get('GW138K_RECORDING_PHASE1_STAGE')
        evidence=os.environ.get('GW138K_RECORDING_PHASE1_PROCESS')
        if not stage or not evidence:
            raise unittest.SkipTest('select a completed sealed no-panel candidate; no EDA fallback')
        cls.stage,cls.evidence=Path(stage),Path(evidence)
        cls.before=verify_synthesis_identity(cls.stage,cls.evidence)
        cls.audit_paths=(Path(inspect.getsourcefile(audit_netlist)),Path(__file__))
        cls.audit_sha256={str(p):file_sha(p) for p in cls.audit_paths}
        cls.profile=json.loads((cls.stage.parents[1]/'workstation_profile.json').read_text())
        cls.n=OwnerResetNetlist((cls.stage/VG_RELATIVE).read_text(),TOP)
        cls.mutations=[]
        cls.baseline=cls.actual()
        cls.proposal=constraint_proposal(cls.baseline)

    @classmethod
    def actual(cls):
        return audit_netlist(cls.n)

    @classmethod
    def tearDownClass(cls):
        if cls.before!=verify_synthesis_identity(cls.stage,cls.evidence):
            raise AssertionError('original recording synthesis inputs changed')
        if cls.audit_sha256!={str(p):file_sha(p) for p in cls.audit_paths}:
            raise AssertionError('recording audit/test sources changed')
        output=os.environ.get('GW138K_RECORDING_PHASE1_TEST_EVIDENCE')
        if output:
            Path(output).write_text(json.dumps(dict(schema=1,synthesis=cls.before,audit_source_sha256=cls.audit_sha256,mutations=cls.mutations,
                mutation_count=len(cls.mutations),actual_sealed_VG_objects=True,original_VG_rewritten=False,
                original_SDC_rewritten=False,source_seal_before_and_after=True,eda_invoked=False,
                hardware_operated=False,recording_cdc_complete=False,physical_cdc_accepted=False,
                deployment_allowed=False),indent=2,sort_keys=True)+'\n')

    def test_actual_complete_phase1_inventory_and_proposal_scope(self):
        r=self.baseline
        self.assertEqual((r['complete_reviewed_FF_count'],r['gray_first_stage_bits'],r['payload_bits']),
                         (425,42,82))
        self.assertEqual(r['clock_domains'],dict(selected='dac_mclk_d',apb='ram_clk',memory='memory_clk'))
        self.assertEqual(len(r['ordinary_first_stage_pairs']),2)
        self.assertEqual(len(r['reset_receiving_chains']),6)
        self.assertEqual(self.proposal['constraint_count'],35)
        queries=audit_proposal_queries(self.n,r,self.proposal)
        self.assertEqual(len(queries['receiving_CLEAR_pins']),18)
        self.assertTrue(all(len(x)==1 for x in queries['source_netlist_selectors'].values()))
        for key in ('recording_cdc_complete','constraints_complete','physical_cdc_accepted',
                    'full_reset_accepted','seal_cdc_accepted','native_commit_and_owner8_accepted',
                    'pcm_RAM_data_ownership_or_data_arcs_accepted','hardware_tested','deployment_allowed','release_ready'):
            self.assertFalse(r[key],key)
        self.assertFalse(queries['tool_query_resolution_verified'])
        self.assertFalse(queries['proposal_installed'])

    def test_declared_profile_and_sealed_source_contracts(self):
        validate_sources(ROOT,self.stage,self.profile)
        for field,value in [('profile','custom138k-workstation-r00-v1'),
                            ('profile_source','boards/custom_138k/workstation_profile_r00_v1.json'),
                            ('profile_sha256','invalid')]:
            p=copy.deepcopy(self.profile);p[field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'explicit supported'):
                validate_sources(ROOT,self.stage,p)
        p=copy.deepcopy(self.profile);p['configuration']['high_speed_allowed']=1
        with self.assertRaisesRegex(ValueError,'explicit supported'):
            validate_sources(ROOT,self.stage,p)
        p=copy.deepcopy(self.profile);p['recording']['source_cdc_complete']=True
        with self.assertRaisesRegex(ValueError,'exact owner8'):
            validate_sources(ROOT,self.stage,p)

    def test_actual_CDC_and_reset_mutations_fail_closed(self):
        g=Graph(self.n)
        reg=lambda s,t,b=None:g.register(s,t,b)
        cases=[
          ('request first D disconnected',reg(A,'req_meta'),'D',"1'b0",'declared producer/shift'),
          ('request first clock changed',reg(A,'req_meta'),'CLK','ram_clk','FF primitive/clock/reset'),
          ('request first CE conditional',reg(A,'req_meta'),'CE',"1'b0",'conditional enable'),
          ('request first reset bypasses local release',reg(A,'req_meta'),'CLEAR',self.n.cells[reg(A,'p_release',0)]['ports']['CLEAR'],'FF primitive/clock/reset'),
          ('request third stage bypassed',reg(A,'req_settled'),'D',self.n.cells[reg(A,'request_toggle')]['ports']['Q'],'third settling'),
          ('ack third stage bypassed',reg(A,'ack_settled'),'D',self.n.cells[reg(A,'acknowledge_toggle')]['ports']['Q'],'third settling'),
          ('request payload bit swapped',reg(A,'request_local',0),'D',self.n.cells[reg(A,'request_held',1)]['ports']['Q'],'payload bit mapping'),
          ('response payload bit swapped',reg(A,'response_local',0),'D',self.n.cells[reg(A,'response_held',1)]['ports']['Q'],'payload bit mapping'),
          ('request payload early capture',reg(A,'request_local',0),'CE',"1'b1",'payload capture CE differs'),
          ('response payload early capture',reg(A,'response_local',0),'CE',"1'b1",'payload capture CE differs'),
          ('request launch lost common CE',reg(A,'request_held',0),'CE',"1'b0",'common launch enable'),
          ('response launch lost common CE',reg(A,'response_held',0),'CE',"1'b0",'common launch enable'),
          ('ack identity changed',reg(A,'acknowledge_toggle'),'D',"1'b0",'acknowledge identity'),
          ('write Gray bit swapped',reg(F,'write_gray_meta',0),'D',self.n.cells[reg(F,'write_gray',1)]['ports']['Q'],'declared producer/shift'),
          ('read Gray MSB alias changed',reg(F,'read_gray_meta',4),'D',self.n.cells[reg(F,'read_gray',0)]['ports']['Q'],'declared producer/shift'),
          ('drop Gray bit swapped',reg(D,'meta',0),'D',self.n.cells[reg(D,'gray',1)]['ports']['Q'],'declared producer/shift'),
          ('drop second stage disconnected',reg(D,'sync_value',0),'D',"1'b0",'declared producer/shift'),
          ('Gray first-Q extra CE consumer',reg(F,'write_binary',0),'CE',self.n.cells[reg(F,'read_gray_meta',0)]['ports']['Q'],'first-Q complete fanout'),
          ('reset receiving stage CE conditional',reg(P,'source_release',0),'CE',"1'b0",'receiving reset release shift/CE'),
          ('reset receiving stage shift changed',reg(P,'source_release',2),'D',"1'b1",'reset intermediate Q complete fanout'),
          ('reset intermediate Q extra CE consumer',reg(P,'source_drop_count_o',0),'CE',self.n.cells[reg(P,'source_release',0)]['ports']['Q'],'reset intermediate Q complete fanout'),
          ('functional CLEAR bypasses release',reg(P,'source_drop_count_o',0),'CLEAR',self.n.cells[reg(P,'source_release',0)]['ports']['CLEAR'],'FF primitive/clock/reset'),
          ('held payload extra control consumer',reg(A,'request_decoded'),'CE',self.n.cells[reg(A,'request_held',0)]['ports']['Q'],'complete source endpoint shape'),
        ]
        for label,path,pin,value,expected in cases:
            old=self.n.cells[path]['ports'][pin]
            self.n.cells[path]['ports'][pin]=value
            try:
                with self.subTest(case=label),self.assertRaisesRegex(ValueError,expected) as error:
                    self.actual()
                self.mutations.append(dict(case=label,rejected=hasattr(error,'exception'),
                    error=str(getattr(error,'exception','mutation was not rejected'))))
            finally:
                self.n.cells[path]['ports'][pin]=old
        self.actual()

    def test_proposal_cannot_cut_functional_CLEAR_or_empty_selector(self):
        for label,line,expected in [
            ('functional CLEAR falsely cut','set_false_path -to [get_pins {u_recording/commands/request_held_0_s*/CLEAR}]\n','raw CLEAR cut scope'),
            ('invented selector','set_false_path -to [get_pins {u_recording/commands/missing_0_s*/CLEAR}]\n','not one exact pin'),
            ('whole domain cut','set_false_path -from [get_clocks {cpu_ram50}] -to [get_clocks {ddr_ui100}]\n','whole-domain query')]:
            p=copy.deepcopy(self.proposal);p['sdc']+=line
            with self.subTest(case=label),self.assertRaisesRegex(ValueError,expected) as error:
                audit_proposal_queries(self.n,self.baseline,p)
            self.mutations.append(dict(case=label,rejected=True,error=str(error.exception)))
        original='u_recording/commands/request_held_0_s0'
        for suffix in ('_sBAD','_s1_extra_s2'):
            added=original.rsplit('_s',1)[0]+suffix
            self.n.cells[added]=copy.deepcopy(self.n.cells[original])
            try:
                with self.subTest(suffix=suffix),self.assertRaisesRegex(ValueError,'not one exact pin') as error:
                    audit_proposal_queries(self.n,self.baseline,self.proposal)
                self.mutations.append(dict(case='suffix overmatch '+suffix,rejected=True,error=str(error.exception)))
            finally:
                del self.n.cells[added]


if __name__=='__main__':
    unittest.main()
