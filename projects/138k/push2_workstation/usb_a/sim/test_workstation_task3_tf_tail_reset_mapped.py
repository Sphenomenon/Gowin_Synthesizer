"""Actual full-VG reset proof and destructive controls, with no positive fixture."""
from pathlib import Path
import hashlib
import json
import os
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_task3_tf_tail_reset import audit_mapped


class ActualTailReset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected=os.environ.get('GW138K_TASK3_TAIL_RESET_STAGE')
        if not selected:raise unittest.SkipTest('explicit matching actual v19 M stage required')
        cls.stage=Path(selected);cls.path=cls.stage/'impl/gwsynthesis/custom_138k_integration.vg'
        cls.hash=hashlib.sha256(cls.path.read_bytes()).hexdigest()
        cls.n=protocol_netlist(cls.path.read_text(),mapping='synthesis')
        cls.positive=audit_mapped(cls.n,stage=cls.stage)
        cls.controls=[]

    @classmethod
    def tearDownClass(cls):
        unchanged=hashlib.sha256(cls.path.read_bytes()).hexdigest()==cls.hash
        target=os.environ.get('GW138K_TASK3_TAIL_RESET_EVIDENCE')
        if target:
            Path(target).write_text(json.dumps(dict(positive=cls.positive,
                negative_controls=cls.controls,VG_sha256=cls.hash,inputs_unchanged=unchanged,
                hardware_tested=False,routed_timing_verified=False),indent=2)+'\n')
        assert unchanged

    def test_actual_all_tail_reset_pins_and_local_chains(self):
        p=self.positive
        self.assertTrue(p['all_selected_tail_reset_pins_proven'])
        self.assertTrue(p['raw_root_absent_from_tail_data_and_enable'])
        self.assertFalse(p['full_tf_cdc_proven'])
        self.assertEqual(sum(len(c['registers']) for c in p['chains'].values()),10)
        self.assertEqual(p['register_count'],len(p['registers']))

    def test_actual_reset_bypass_clock_enable_and_shift_mutants_rejected(self):
        n=self.n;p=self.positive
        for role in ('compute','serial'):
            target=next(r['register'] for r in p['registers'] if r['domain']==role)
            release=p['chains'][role]['registers'][-1]['register']
            cases=[(target,'CLEAR',n.cells[release]['ports']['CLEAR'],'raw common reset bypass'),
                   (target,'CLK',"1'b0",'stopped/incorrect clock'),
                   (target,'CE',p['root']['root_q'],'raw root business enable'),
                   (release,'CE',"1'b0",'release shift disabled'),
                   (release,'D',"1'b1",'release shift bypass')]
            for path,pin,value,label in cases:
                original=n.cells[path]['ports'][pin]
                self.assertNotEqual(value,original)
                aliases=[]
                if label=='raw root business enable':
                    # Route an actual root connection through each parent
                    # frame. A top canonical name placed in a child binding
                    # would create an unrelated undriven child-local net.
                    scope=n.scopes[path];formal='__audit_raw_root'
                    while scope:
                        ports=n.frames[scope]['ports']
                        self.assertNotIn(formal,ports)
                        parent=n.scopes[scope]
                        ports[formal]=p['root']['root_q'] if not parent else formal
                        aliases.append(ports);scope=parent
                    value=formal
                n.cells[path]['ports'][pin]=value
                try:
                    if aliases:self.assertEqual(n.pin(path,pin),p['root']['root_q'])
                    with self.subTest(role=role,case=label):
                        with self.assertRaises(ValueError) as caught:
                            audit_mapped(n,stage=self.stage)
                        self.controls.append(dict(domain=role,case=label,rejected=True,error=str(caught.exception)))
                finally:
                    n.cells[path]['ports'][pin]=original
                    for ports in aliases:del ports['__audit_raw_root']


if __name__=='__main__':unittest.main()
