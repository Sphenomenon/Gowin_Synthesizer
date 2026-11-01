#!/usr/bin/env python3
"""Actual DIRECT tail positive/negative probes; no mocked positive VG."""
from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
import os
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_runtime_pcm_cdc import Graph
from tools.workstation_task3_root_reset_audit import audit_root_startup
from tools.workstation_task3_tf_tail_cdc_audit import (
    audit_tf_tail_cdc,validate_tf_tail_sdc,SCOPE,SOURCE)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class ActualTail(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        vg,stage=(os.environ.get(k) for k in ('GW138K_TASK3_TAIL_VG','GW138K_TASK3_TAIL_STAGE'))
        if not vg or not stage:
            raise unittest.SkipTest('explicit matching actual VG/stage required; no fallback or mocked positive')
        cls.path,cls.stage=Path(vg),Path(stage)
        cls.metadata_path=cls.stage.parents[1]/'integration_inputs.json'
        metadata=json.loads(cls.metadata_path.read_text())
        cls.constraint_revision=metadata['task3_tf_direct_cdc'].get('constraint_revision',1)
        if cls.constraint_revision not in (1,2,3):
            raise ValueError('unsupported explicit TF constraint revision')
        cls.sdc=(cls.stage/'constraints/custom_138k.sdc').read_text()
        cls.n=protocol_netlist(cls.path.read_text(),mapping='synthesis')
        cls.root=audit_root_startup(cls.n,stage=cls.stage)
        cls.before={str(p):sha(p) for p in (cls.path,cls.metadata_path,cls.stage/'Prj1.gprj',cls.stage/SOURCE,
                    cls.stage/'constraints/custom_138k.sdc',ROOT/'tools/workstation_task3_tf_tail_cdc_audit.py')}
        cls.positive,cls.mutations,cls.sdc_rejection,cls.failed=None,[],None,False
        cls.proposed_sdc_test=None
        cls.installed_sdc_validation=None

    def tearDown(self):
        r=self._outcome.result
        self.__class__.failed |= bool(r.failures or r.errors)

    @classmethod
    def tearDownClass(cls):
        unchanged=cls.before=={p:sha(p) for p in cls.before}
        selected=os.environ.get('GW138K_TASK3_TAIL_EVIDENCE')
        if selected:
            Path(selected).write_text(json.dumps(dict(
                status='PARTIAL_LOCAL_PASS' if unchanged and cls.positive and not cls.failed else 'FAIL',
                selected_stage=str(cls.stage),actual_input_sha256=cls.before,original_inputs_unchanged=unchanged,
                explicit_constraint_revision=cls.constraint_revision,
                selected_revision_metadata=str(cls.metadata_path),
                actual_tail=cls.positive,actual_installed_sdc_rejection=cls.sdc_rejection,
                actual_installed_sdc_validation=cls.installed_sdc_validation,
                corrected_text_only_sdc_test=cls.proposed_sdc_test,
                mutations=cls.mutations,mutation_count=len(cls.mutations),
                audit_source_sha256={p:sha(ROOT/p) for p in (
                    'tools/workstation_task3_tf_tail_cdc_audit.py','sim/test_workstation_task3_tf_tail_cdc.py')},
                full_tf_cdc_accepted=False,routed_timing_verified=False,hardware_tested=False),indent=2)+'\n')
        assert unchanged,'actual candidate inputs drifted'

    def audit(self):
        return audit_tf_tail_cdc(self.n,root=self.root,stage=self.stage)

    @contextmanager
    def changed(self,path,part,key,value):
        row=self.n.cells[path][part]
        absent=object();old=row.get(key,absent);row[key]=value
        try:
            yield
        finally:
            if old is absent:
                del row[key]
            else:
                row[key]=old

    def test_01_actual_local_request_capture_and_real_closure(self):
        r=self.audit()
        self.assertEqual(r['register_count'],698)
        self.assertEqual(len(r['next_q']),395)
        self.assertEqual(len(r['held_request_capture_pins']),162)
        self.assertEqual(len(r['held_reply_compute_capture_pins']),68)
        self.assertEqual(sum(p.endswith('/CE') for p in r['held_reply_compute_capture_pins']),36)
        self.assertTrue(r['request_busy_no_overwrite_proven'])
        self.assertEqual(r['serial_capture_no_earlier_than_receiving_edge'],3)
        self.assertFalse(r['reply_retirement_next_q_proven'])
        self.assertFalse(r['compute_reply_business_next_q_proven'])
        self.assertFalse(r['full_tf_cdc_proven'])
        self.__class__.positive=r

    def test_02_actual_installed_sdc_matches_explicit_revision(self):
        r=self.audit()
        if self.constraint_revision==3:
            result=validate_tf_tail_sdc(self.sdc,self.n,tail=r)
            self.assertEqual(result['exact_held_reply_D_and_CE_pin_count'],68)
            reply=[row for row in result['installed_constraints']
                   if set(row['source_pins'])==set(r['held_reply_source_pins'])]
            self.assertEqual(len(reply),2)
            for row in reply:
                self.assertEqual(sum(p.endswith('/D') for p in row['capture_pins']),32)
                self.assertEqual(sum(p.endswith('/CE') for p in row['capture_pins']),36)
            self.assertFalse(result['full_tf_cdc_proven'])
            self.assertFalse(result['routed_timing_verified'])
            self.__class__.installed_sdc_validation=dict(proposal_only=False,actual_sdc_changed=False,
                exact_installed_sdc_accepted=True,full_tf_cdc_accepted=False,result=result)
        else:
            with self.assertRaisesRegex(ValueError,'complete SDC source/target inventory changed: .*held_reply') as e:
                validate_tf_tail_sdc(self.sdc,self.n,tail=r)
            self.__class__.sdc_rejection=dict(expected=True,error=str(e.exception),missing_real_CE_pins=36,
                bounded_actual_D_pins=32,required_real_D_and_CE_pins=68,actual_sdc_accepted=False)

    def test_03_destructive_netlist_controls(self):
        r=self.audit();g=Graph(self.n);s=SCOPE;n=self.n
        group=lambda name,width:g.group(s,name,width)
        reg=lambda name,bit=None:g.register(s,name,bit)
        request,token,reply=group('held_request',162),group('serial_token',162),group('held_reply',229)
        req=reg('request_toggle');rep=reg('reply_toggle');seen=reg('serial_request_seen');consumed=reg('reply_consumed')
        extra=reg('tail_pending_o')
        cases=[
            ('request D stops toggling',req,'ports','D',"1'b0"),
            ('request CE commits while busy',req,'ports','CE',"1'b1"),
            ('request clock changes',req,'ports','CLK','dac_mclk_d'),
            ('request INIT changes',req,'parameters','INIT',"1'b1"),
            ('held request bit 0 cannot hold',request[0],'ports','D',"1'b0"),
            ('held request bit 161 cannot hold',request[161],'ports','D',"1'b1"),
            ('held request missing root CLEAR',request[80],'ports','CLEAR',"1'b0"),
            ('held request wrong clock',request[61],'ports','CLK','dac_mclk_d'),
            ('held request extra compute consumer',extra,'ports','D',n.cells[request[21]]['ports']['Q']),
            ('token bit mapping changes',token[60],'ports','D',n.cells[request[61]]['ports']['Q']),
            ('token capture always enabled',token[0],'ports','CE',"1'b1"),
            ('token capture disabled',token[161],'ports','CE',"1'b0"),
            ('token root CLEAR removed',token[70],'ports','CLEAR',"1'b0"),
            ('token INIT changes',token[90],'parameters','INIT',"1'b1"),
            ('token wrong clock',token[9],'ports','CLK','audio_clk'),
            ('reply source root CLEAR removed',reply[201],'ports','CLEAR',"1'b0"),
            ('reply source wrong clock',reply[222],'ports','CLK','audio_clk'),
            ('reply source INIT changes',reply[24],'parameters','INIT',"1'b1"),
            ('reply gains unreviewed consumer',extra,'ports','D',n.cells[reply[17]]['ports']['Q']),
            ('reply loses reviewed baseline D',reg('baseline_drops_o',0),'ports','D',"1'b0"),
            ('reply loses reviewed baseline CE',reg('baseline_drops_o',16),'ports','CE',"1'b1"),
            ('reply loses reviewed arm_pending CE',reg('arm_pending'),'ports','CE',"1'b1"),
            ('seen D changed',seen,'ports','D',"1'b1"),
            ('seen CE changed',seen,'ports','CE',"1'b1"),
            ('consumed D changed',consumed,'ports','D',"1'b0"),
            ('consumed CE changed',consumed,'ports','CE',"1'b0"),
        ]
        for c in r['chains']:
            first,second=(p.rsplit('/',1)[0] for p in (c['first'],c['second']))
            cases += [
                (c['id']+' first direct D changed',first,'ports','D',"1'b1"),
                (c['id']+' second D bypasses first',second,'ports','D',n.cells[req if c['id']=='request' else rep]['ports']['Q']),
                (c['id']+' first CE disabled',first,'ports','CE',"1'b0"),
                (c['id']+' first has extra local consumer',seen,'ports','D',n.cells[first]['ports']['Q']),
            ]
        fm,fs=group('fence_meta',32),group('fence_sync',32)
        cases += [
            ('fence bit mapping changed',fm[31],'ports','D',n.cells[reg('fence_gray',30)]['ports']['Q']),
            ('fence second D changed',fs[8],'ports','D',"1'b0"),
            ('fence first CE disabled',fm[0],'ports','CE',"1'b0"),
            ('fence second CLEAR removed',fs[24],'ports','CLEAR',"1'b0"),
            ('fence first has extra consumer',seen,'ports','D',n.cells[fm[0]]['ports']['Q']),
            ('fence Gray has extra remote consumer',seen,'ports','D',n.cells[reg('fence_gray',0)]['ports']['Q']),
        ]
        for label,path,part,key,value in cases:
            with self.subTest(case=label),self.changed(path,part,key,value):
                with self.assertRaises(ValueError) as e:
                    self.audit()
            self.mutations.append(dict(case=label,rejected=True,error=str(e.exception)))
        self.assertEqual(len(cases),40)

    def test_04_revision_selected_exact_SDC_and_destructive_controls(self):
        # r1/r2 exercise a corrected string only; r3 exercises installed SDC.
        # All destructive probes remain in memory and never change the stage.
        r=self.audit();s=SCOPE
        old=' '.join(s+'/'+stem+suffix+'/D' for stem,suffix in (
            ('arm_pending','_s*'),('armed_o','_s*'),('baseline_drops_o','_*_s*'),
            ('failed_o','_s*'),('tail_receipted','_s*')))
        new=' '.join([s+'/baseline_drops_o_*_s*/D',s+'/baseline_drops_o_*_s*/CE']+
                     [s+'/'+stem+'_s*/CE' for stem in ('arm_pending','armed_o','failed_o','tail_receipted')])
        if self.constraint_revision==3:
            self.assertEqual(self.sdc.count(old),0)
            self.assertEqual(self.sdc.count(new),2)
            proposal=self.sdc
        else:
            self.assertEqual(self.sdc.count(old),2)
            proposal=self.sdc.replace(old,new)
        result=validate_tf_tail_sdc(proposal,self.n,tail=r)
        self.assertEqual(result['exact_held_reply_D_and_CE_pin_count'],68)
        if self.constraint_revision!=3:
            self.__class__.proposed_sdc_test=dict(proposal_only=True,actual_sdc_changed=False,
                installed_sdc_accepted=False,result=result)
        replyline=next(l for l in proposal.splitlines() if l.startswith('set_max_delay 13.020 ')
                       and s+'/held_reply_' in l)
        cases=[
            ('remove exact finite bound',proposal.replace(replyline+'\n','')),
            ('weaken setup budget',proposal.replace(replyline,replyline.replace('13.020','50.000'))),
            ('remove baseline CE target',proposal.replace(' '+s+'/baseline_drops_o_*_s*/CE','')),
            ('keep phantom scalar D target',proposal.replace(s+'/armed_o_s*/CE',s+'/armed_o_s*/D')),
            ('add whole later-state setup cut',proposal+'set_false_path -to [get_pins {'+s+'/serial_token_*_s*/D}]\n'),
            ('add held-reply source-only setup cut',proposal+'set_false_path -from [get_pins {'+s+'/held_reply_*_s*/Q}]\n'),
            ('duplicate finite bound',proposal+replyline+'\n'),
            ('unreviewed clock-wide setup cut',proposal+'set_false_path -from [get_clocks {audio_76m8}] -to [get_clocks {serial_48}]\n'),
            ('unreviewed clock groups waive setup',proposal+'set_clock_groups -asynchronous -group [get_clocks {audio_76m8}] -group [get_clocks {serial_48}]\n'),
            ('unreviewed through setup cut',proposal+'set_false_path -through [get_pins {'+s+'/held_reply_*_s*/Q}]\n'),
            ('source-only register setup cut',proposal+'set_false_path -from [get_regs {'+s+'/held_reply_*_s*}]\n'),
        ]
        for label,text in cases:
            with self.subTest(case=label),self.assertRaises(ValueError) as e:
                validate_tf_tail_sdc(text,self.n,tail=r)
            self.mutations.append(dict(case=label,rejected=True,error=str(e.exception),
                text_only_sdc_mutation=self.constraint_revision!=3,
                installed_sdc_string_mutation=self.constraint_revision==3))
        self.assertEqual(len(cases),11)


if __name__=='__main__':
    unittest.main()
