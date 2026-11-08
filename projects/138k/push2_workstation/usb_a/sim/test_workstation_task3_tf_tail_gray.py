#!/usr/bin/env python3
"""Actual mapped fence arithmetic and destructive controls; explicit VG only."""
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
from tools.workstation_task3_tf_tail_gray import audit,SCOPE


class ActualCancellationGray(unittest.TestCase):
    def test_actual_all_bits_and_mutations(self):
        vg=os.environ.get('GW138K_TASK3_TAIL_GRAY_VG')
        if not vg:self.skipTest('explicit actual VG required; no inferred candidate')
        path=Path(vg);before=hashlib.sha256(path.read_bytes()).hexdigest()
        n=protocol_netlist(path.read_text(),mapping='synthesis');g=Graph(n)
        release=n.pin(g.register('u_managed/runtime','compute_release',2),'Q')
        result=audit(n,local_release_q=release)
        self.assertEqual(result['binary_next_Q_equations'],32)
        self.assertEqual(result['Gray_next_Q_equations'],32)
        self.assertTrue(result['event_relation_preserved_in_all_next_Q'])
        if result['inverted_event_alias'] is not None:
            self.assertTrue(result['inverted_event_alias']['exact_inverse_proven'])
        else:
            self.assertEqual(result['event_mapping'],'expanded_two_input_OR')
            self.assertEqual(len(result['event_equation_inputs']),2)
        cases=[]
        for label,stem,bit,part,key,value in [
            ('counter D','fence_count',0,'ports','D',"1'b0"),
            ('counter CE','fence_count',15,'ports','CE',"1'b0"),
            ('counter clock','fence_count',30,'ports','CLK','clk_50m'),
            ('counter reset','fence_count',1,'ports','CLEAR',"1'b0"),
            ('Gray D','fence_gray',0,'ports','D',"1'b1"),
            ('Gray upper carry','fence_gray',31,'ports','D',n.pin(g.register(SCOPE,'fence_count',30),'Q')),
            ('Gray CE','fence_gray',30,'ports','CE',"1'b1"),
            ('Gray INIT','fence_gray',20,'parameters','INIT',"1'b1"),
        ]:
            p=g.register(SCOPE,stem,bit);target=n.cells[p][part]
            absent=object();old=target.get(key,absent);target[key]=value
            try:
                with self.subTest(case=label),self.assertRaises(ValueError) as error:
                    audit(n,local_release_q=release)
                cases.append(dict(case=label,rejected=True,error=str(error.exception)))
            finally:
                if old is absent:del target[key]
                else:target[key]=old
        # Change only the duplicated event's actual LUT, preserving the
        # counter and Gray connections. Independent-cut acceptance must fail.
        alias=(result['inverted_event_alias']['net'] if result['inverted_event_alias'] is not None
               else result['shared_event_enable']);p,_=g.drivers[alias][0]
        old=n.cells[p]['parameters']['INIT'];n.cells[p]['parameters']['INIT']="16'h0"
        try:
            with self.assertRaises(ValueError) as error:audit(n,local_release_q=release)
            cases.append(dict(case='event alias equation',rejected=True,error=str(error.exception)))
        finally:n.cells[p]['parameters']['INIT']=old
        self.assertEqual(len(cases),9)
        self.assertEqual(result,audit(n,local_release_q=release))
        self.assertEqual(before,hashlib.sha256(path.read_bytes()).hexdigest())
        evidence=os.environ.get('GW138K_TASK3_TAIL_GRAY_EVIDENCE')
        if evidence:
            tracked=[path,ROOT/'tools/workstation_task3_tf_tail_gray.py',Path(__file__)]
            Path(evidence).write_text(json.dumps(dict(status='PASS',actual_arithmetic=result,
                mutations=cases,actual_inputs_unchanged=True,hardware_tested=False,
                source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in tracked}),indent=2)+'\n')


if __name__=='__main__':unittest.main()
