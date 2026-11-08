#!/usr/bin/env python3
"""Actual serial-tail retirement truth tables and destructive controls.

Explicit actual VG/stage only, with no synthetic netlist, source/constraint
mutation, EDA or board operation. This is independent of the TF tail CDC audit.
"""
from contextlib import contextmanager
from pathlib import Path
import copy
import hashlib
import json
import os
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_runtime_pcm_cdc import Graph
from tools.workstation_task3_root_reset_audit import audit_root_startup
from tools.workstation_task3_tf_tail_retirement_audit import audit_tf_tail_retirement,SCOPE,SOURCE


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ActualTask3TailRetirement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        vg=os.environ.get('GW138K_TASK3_TAIL_RETIREMENT_VG')
        stage=os.environ.get('GW138K_TASK3_TAIL_RETIREMENT_STAGE')
        if not vg or not stage:
            raise unittest.SkipTest('explicit actual VG/stage required; no fallback')
        cls.vg,cls.stage=Path(vg),Path(stage)
        cls.mapping=os.environ.get('GW138K_TASK3_TAIL_RETIREMENT_MAPPING','synthesis')
        cls.n=protocol_netlist(cls.vg.read_text(),mapping=cls.mapping)
        cls.root=audit_root_startup(cls.n,stage=cls.stage)
        cls.positive,cls.mutations,cls.failed=None,[],False
        cls.before={str(p):sha(p) for p in (cls.vg,cls.stage/SOURCE,
            *(cls.stage/path for path in cls.root['source_sha256']),
            ROOT/'tools/workstation_task3_root_reset_audit.py',
            ROOT/'tools/workstation_task3_tf_direct.py',
            ROOT/'tools/workstation_native_protocol_audit.py',
            ROOT/'tools/workstation_runtime_pcm_cdc.py',
            ROOT/'tools/workstation_synthesis_netlist.py',
            ROOT/'tools/workstation_task3_tf_tail_retirement_audit.py',
            Path(__file__))}

    def tearDown(self):
        result=self._outcome.result
        self.__class__.failed |= bool(result.failures or result.errors)

    @classmethod
    def tearDownClass(cls):
        unchanged=cls.before=={p:sha(p) for p in cls.before}
        target=os.environ.get('GW138K_TASK3_TAIL_RETIREMENT_EVIDENCE')
        if target:
            Path(target).write_text(json.dumps(dict(
                status='PARTIAL_SERIAL_NEXT_Q_PASS' if unchanged and cls.positive and not cls.failed else 'FAIL',
                mapping=cls.mapping,selected_stage=str(cls.stage),selected_vg=str(cls.vg),
                actual_input_and_audit_sha256=cls.before,
                actual_root_startup=cls.root,actual_serial_retirement=cls.positive,
                mutations=cls.mutations,mutation_count=len(cls.mutations),
                original_inputs_unchanged=unchanged,
                all_mutations_in_memory_and_restored=True,
                complete_tf_cdc_accepted=False,physical_tail_hardware_semantics_accepted=False,
                routed_timing_verified=False,hardware_tested=False,
                release_ready=False,deployment_allowed=False),indent=2)+'\n')
        assert unchanged,'actual candidate, source, test or frozen helper drifted'

    @contextmanager
    def changed(self,path,part,key,value):
        target=self.n.cells[path][part]
        absent=object();old=target.get(key,absent)
        target[key]=value
        try:yield
        finally:
            if old is absent:del target[key]
            else:target[key]=old

    def audit(self,root=None):
        return audit_tf_tail_retirement(self.n,root=self.root if root is None else root,stage=self.stage)

    def rejected(self,cases):
        for label,path,part,key,value in cases:
            with self.subTest(case=label),self.changed(path,part,key,value):
                with self.assertRaises(ValueError) as error:self.audit()
            self.mutations.append(dict(case=label,rejected=True,error=str(error.exception)))

    def test_01_actual_serial_next_q(self):
        actual=self.audit()
        self.assertEqual(actual['comparison_count'],7)
        self.assertEqual(actual['comparison_operand_pairs'],224)
        self.assertEqual(actual['proof_register_count'],233)
        self.assertEqual(actual['held_reply_next_q_bits'],229)
        self.assertEqual(sum(row.get('no_overwrite_outside_retirement_or_root_clear_proven',False)
                             for row in actual['next_q']),229)
        self.assertTrue(all(row['reset_inclusive_next_q_exact'] for row in actual['next_q']))
        self.assertTrue(actual['reply_retirement_next_q_proven'])
        self.assertFalse(actual['source_data_expression_cuts_used'])
        self.assertFalse(actual['serial_context_register_transition_logic_proven'])
        self.assertFalse(actual['compute_reply_business_next_q_proven'])
        self.assertFalse(actual['cancellation_gray_arithmetic_proven'])
        self.assertFalse(actual['upstream_physical_and_observation_counter_authenticity_proven'])
        self.assertFalse(actual['full_tf_cdc_proven'])
        self.assertFalse(actual['release_ready'])
        self.__class__.positive=actual

    def test_02_exact_actual_comparison_destructive_controls(self):
        actual=self.audit();n,g=self.n,Graph(self.n)
        cases=[]
        for name,record in actual['comparisons'].items():
            net=record['output'];chain=[]
            while net not in g.low:
                path,port=g.drivers[net][0];chain.append(path)
                if n.cells[path]['kind']=='LUT2':break
                net=n.pin(path,'CIN')
            top=chain[0]
            self.assertEqual(n.cells[top]['kind'],'ALU')
            cases.extend((
                (name+' duplicated operand',top,'ports','I0',n.cells[top]['ports']['I1']),
                (name+' missing lower 31 pairs',top,'ports','CIN',"1'b0"),
                (name+' unreviewed ALU mode',top,'parameters','ALU_MODE','0'),
                (name+' NE I3 not ground',top,'ports','I3',"1'b1"),
            ))
            seed=chain[-1]
            if n.cells[seed]['kind']=='LUT2':
                cases.append((name+' non-XOR seed',seed,'parameters','INIT',"4'h8"))
            else:
                cases.append((name+' nonzero carry seed',seed,'ports','CIN',"1'b1"))
            # Preserve two distinct operands but substitute a wrong same-side bit.
            neighbor=chain[1]
            cases.append((name+' wrong operand bit',top,'ports','I0',n.cells[neighbor]['ports']['I0']))
        self.rejected(cases)
        self.assertEqual(len(cases),42)

    def test_03_actual_state_retirement_and_payload_destructive_controls(self):
        n,g=self.n,Graph(self.n);cases=[]
        state=g.group(SCOPE,'serial_state',2)
        reply=g.register(SCOPE,'reply_toggle')
        error=g.register(SCOPE,'serial_frame_error')
        seen=g.register(SCOPE,'serial_request_seen')
        sync=g.group(SCOPE,'request_sync',2)
        held=g.group(SCOPE,'held_reply',229)
        token=g.group(SCOPE,'serial_token',162)
        for bit,path in enumerate(state):
            cases.extend((
                ('state %d D cleared'%bit,path,'ports','D',"1'b0"),
                ('state %d CE disabled'%bit,path,'ports','CE',"1'b0"),
                ('state %d wrong clock'%bit,path,'ports','CLK','audio_clk'),
                ('state %d wrong INIT'%bit,path,'parameters','INIT',"1'b1"),
                ('state %d missing root CLEAR'%bit,path,'ports','CLEAR',"1'b0"),
            ))
        cases.extend((
            ('reply retires every edge',reply,'ports','CE',"1'b1"),
            ('reply never retires',reply,'ports','CE',"1'b0"),
            ('reply D cleared instead of seen',reply,'ports','D',"1'b0"),
            ('reply D live synchronizer instead of captured seen',reply,'ports','D',n.cells[sync[1]]['ports']['Q']),
            ('reply wrong root CLEAR',reply,'ports','CLEAR',"1'b1"),
            ('frame error latch always enabled',error,'ports','CE',"1'b1"),
            ('frame error latch disabled',error,'ports','CE',"1'b0"),
            ('frame error D cleared',error,'ports','D',"1'b0"),
            ('frame error wrong clock',error,'ports','CLK','audio_clk'),
            ('frame error nonzero INIT',error,'parameters','INIT',"1'b1"),
        ))
        for bit in (0,1,32,33,64,65,66,67,227,228):
            cases.append(('held reply bit %d payload cleared'%bit,held[bit],'ports','D',"1'b0"))
        cases.extend((
            ('held token bypasses retire hold',held[67],'ports','D',n.cells[token[0]]['ports']['Q']),
            ('held status never updates',held[65],'ports','D',n.cells[held[65]]['ports']['Q']),
            ('held baseline never updates',held[33],'ports','D',n.cells[held[33]]['ports']['Q']),
            ('held prefix never updates',held[1],'ports','D',n.cells[held[1]]['ports']['Q']),
            ('held error never updates',held[0],'ports','D',n.cells[held[0]]['ports']['Q']),
            ('held reply CE removed',held[0],'ports','CE',"1'b0"),
            ('held reply wrong clock',held[67],'ports','CLK','audio_clk'),
            ('held reply nonzero INIT',held[228],'parameters','INIT',"1'b1"),
            ('held reply root CLEAR removed',held[32],'ports','CLEAR',"1'b0"),
            ('context storage wrong serial clock',g.register(SCOPE,'serial_context_valid'),'ports','CLK','audio_clk'),
        ))
        self.rejected(cases)
        self.assertEqual(len(cases),40)

    def test_04_actual_root_and_hierarchy_identity_destructive_controls(self):
        cases=[('unverified root',dict(all_state_assignments_proven=False)),
               ('wrong root policy',dict(policy='invented-root')),
               ('wrong root publisher',dict(root_register='u_reset/startup_count_0_s0')),
               ('constant root proof Q',dict(root_q="1'b1"))]
        for label,change in cases:
            root=copy.deepcopy(self.root);root.update(change)
            with self.subTest(case=label),self.assertRaises(ValueError) as error:self.audit(root)
            self.mutations.append(dict(case=label,rejected=True,error=str(error.exception)))
        old=self.n.frames[SCOPE]['kind']
        try:
            self.n.frames[SCOPE]['kind']='invented_tail'
            with self.assertRaises(ValueError) as error:self.audit()
        finally:self.n.frames[SCOPE]['kind']=old
        self.mutations.append(dict(case='wrong actual tail module',rejected=True,error=str(error.exception)))
        for label,attribute,value in (
            ('reviewed source hash mismatch','SOURCE_SHA256','0'*64),
            ('reviewed source not selected','SOURCE','rtl/not_selected_tail.sv'),
        ):
            with self.subTest(case=label),patch('tools.workstation_task3_tf_tail_retirement_audit.'+attribute,value):
                with self.assertRaises(ValueError) as error:self.audit()
            self.mutations.append(dict(case=label,rejected=True,error=str(error.exception)))


if __name__=='__main__':
    unittest.main()
