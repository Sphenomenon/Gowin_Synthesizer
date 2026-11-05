#!/usr/bin/env python3
"""Escaped aliases, primitive semantics and immutable actual W negative controls."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.workstation_task3_w_consumer_nextq import (
    VectorNetlist, Circuit, Expressions, compare)


def value(e, node, assignment):
    kind, *args = e.nodes[node]
    if kind == 'constant':
        return args[0]
    if kind == 'state':
        return assignment[args[0]]
    return value(e,args[1] if value(e,args[0],assignment) else args[2],assignment)


class Aliases(unittest.TestCase):
    def fixture(self,binding='payload[7:0]'):
        return VectorNetlist('''module child ();
input [7:0] \\header[4] ;
output out;
INV inv_s0 (
 .I(\\header[4] [0]),
 .O(out)
);
endmodule
module top ();
input [7:0] payload;
output out;
child c (
 .\\header[4] ('''+binding+'''),
 .out(out)
);
endmodule
''','top')

    def test_declared_escaped_vector_aliases(self):
        n = self.fixture()
        self.assertEqual(n.pin('c/inv_s0','I'),'payload[0]')
        self.assertEqual(n.canonical('c','\\header[4] [7]'),'payload[7]')
        self.assertEqual(n.concatenation_bits('c','{\\header[4] [7:6],\\header[4] [0]}'),
                         ['\\header[4] [0]','\\header[4] [6]','\\header[4] [7]'])
        self.assertEqual(self.fixture('{payload[0],payload[1],payload[2],payload[3],payload[4],payload[5],payload[6],payload[7]}')
                         .pin('c/inv_s0','I'),'payload[7]')
        # A scalar escaped name is not a bit select without terminating space.
        self.assertEqual(n.canonical('c','\\header[4][0]'),'c/\\header[4][0]')
        with self.assertRaises(ValueError):
            n.canonical('c','\\header[4] [8]')
        with self.assertRaises(ValueError):
            self.fixture('payload[6:0]').pin('c/inv_s0','I')

    def test_alias_cycles_are_rejected(self):
        n = self.fixture()
        n.frames['c']['ports']['header[4]'] = 'payload[7:0]'
        # A repeated (scope,net) must reject rather than recurse or invent a leaf.
        with self.assertRaises(ValueError):
            n.canonical('c','\\header[4] [0]',(('c','\\header[4] [0]'),))


class TinyNetlist:
    modules = {}
    def __init__(self,kind='DFFCE'):
        self.cells = {}
        self.scopes = {}
        for name in ('data','enable','assertion','target'):
            pin = 'PRESET' if name == 'target' and kind == 'DFFPE' else 'RESET' if name == 'target' and kind == 'DFFRE' else 'CLEAR'
            self.cells[name+'_s0'] = dict(kind=kind if name=='target' else 'DFFCE',
                ports=dict(Q=name,D='data',CLK='clk',CE='enable',**{pin:'assertion'}),parameters={})
            self.scopes[name+'_s0'] = ''
    def pin(self,path,pin):
        return self.cells[path]['ports'][pin]


class PrimitiveSemantics(unittest.TestCase):
    def test_ALU_against_installed_vendor_primitive(self):
        selected=os.environ.get('GW138K_TASK3_W_NEXTQ_PRIMITIVES')
        if not selected:
            self.skipTest('explicit Gowin primitive library required')
        source=Path(selected).read_text()
        match=re.search(r'^module ALU\b.*?^endmodule[^\n]*',source,re.M|re.S)
        self.assertIsNotNone(match)
        modes=(0,1,3,4,5)
        bench='module tb; reg [3:0] bits; integer i;\n'
        for mode in modes:
            bench+=f'wire s{mode},c{mode}; ALU #(.ALU_MODE({mode})) a{mode}(s{mode},c{mode},bits[0],bits[1],bits[2],bits[3]);\n'
        bench+='initial begin for(i=0;i<16;i=i+1) begin bits=i; #1;\n'
        for mode in modes:
            bench+=f'$display("{mode} %0d %b %b",i,s{mode},c{mode});\n'
        bench+='end $finish; end endmodule\n'
        with tempfile.TemporaryDirectory(prefix='task3-W-ALU-') as folder:
            folder=Path(folder);(folder/'test.v').write_text(match[0]+'\n'+bench)
            subprocess.run(['iverilog','-s','tb','-o',str(folder/'a.out'),str(folder/'test.v')],check=True,capture_output=True)
            output=subprocess.run(['vvp',str(folder/'a.out')],check=True,capture_output=True,text=True).stdout
        lines=[line for line in output.splitlines() if re.fullmatch(r'[01345] \d+ [01] [01]',line)]
        for line in lines:
            mode,bits,s,c=map(int,line.split());e=Expressions();n=TinyNetlist()
            n.cells['alu_s0']=dict(kind='ALU',parameters={'ALU_MODE':str(mode)},
                ports=dict(I0='data',I1='enable',I3='assertion',CIN='target',SUM='sum',COUT='carry'))
            n.scopes['alu_s0']='';circuit=Circuit(n,e)
            assignment={name:(bits>>i)&1 for i,name in enumerate(('data','enable','assertion','target'))}
            self.assertEqual(value(e,circuit.net('sum'),assignment),s)
            self.assertEqual(value(e,circuit.net('carry'),assignment),c)
        self.assertEqual(len(lines),80)

    def test_default_INIT_and_reset_before_CE(self):
        for kind,default in [('DFFCE',0),('DFFRE',0),('DFFPE',1)]:
            e = Expressions();c = Circuit(TinyNetlist(kind),e)
            root,init,clock = c.next_q('target_s0')
            self.assertEqual(init,"1'b"+str(default));self.assertEqual(clock,'clk')
            for bits in range(16):
                a = {name:(bits>>i)&1 for i,name in enumerate(('data','enable','assertion','target'))}
                expected = default if a['assertion'] else a['data'] if a['enable'] else a['target']
                self.assertEqual(value(e,root,a),expected)

    def test_unknown_primitive_parameters_and_state_are_not_admitted(self):
        for section,key,new in [('parameters','UNKNOWN','1'),('ports','UNKNOWN','data')]:
            n=TinyNetlist();n.cells['target_s0'][section][key]=new
            with self.assertRaises(ValueError):Circuit(n,Expressions()).next_q('target_s0')
        n=TinyNetlist();n.cells['target_s0']['kind']='DFFSE'
        with self.assertRaises(ValueError):Circuit(n,Expressions()).next_q('target_s0')
        n=TinyNetlist();n.cells['target_s1']=deepcopy(n.cells['target_s0']);n.scopes['target_s1']=''
        with self.assertRaises(ValueError):Circuit(n,Expressions()).net('target')


class ActualW(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        old,new=os.environ.get('GW138K_TASK3_W_NEXTQ_OLD'),os.environ.get('GW138K_TASK3_W_NEXTQ_NEW')
        if not old or not new:
            raise unittest.SkipTest('explicit old/new immutable W candidates required')
        cls.before={};cls.circuits={};cls.e=Expressions();cls.rows=[]
        for label,folder in [('old',old),('new',new)]:
            vg=Path(folder)/'workstation/Prj1/impl/gwsynthesis/custom_138k_integration.vg'
            cls.before[str(vg)]=hashlib.sha256(vg.read_bytes()).hexdigest()
            cls.circuits[label]=Circuit(VectorNetlist(vg.read_text(),'workstation_custom_138k_top'),cls.e)

    @classmethod
    def tearDownClass(cls):
        assert cls.before=={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in cls.before}
        target=os.environ.get('GW138K_TASK3_W_NEXTQ_TEST_EVIDENCE')
        if target:
            Path(target).write_text(json.dumps(dict(inputs_sha256=cls.before,
                actual_inputs_unchanged=True,checks=cls.rows,full_CDC_accepted=False),indent=2)+'\n')

    def test_actual_twelve_conditional_transition_proofs(self):
        names=['u_bluetooth/u_core/application/command_endpoint/cpu_mailbox/'+name
               for name in ('admitted_count_0','age_31','next_ticket_0','rejected_count_0')]
        names += ['u_task3_media/raw_store/generation_'+str(bit) for bit in (8,9,11,14,20,22,25,27)]
        for name in names:
            proof=compare(self.circuits['old'],self.circuits['new'],name)
            self.assertTrue(proof['conditional_next_Q_equal']);self.rows.append(proof)
        proof=next(p for p in self.rows if p.get('register','').endswith('next_ticket_0'))
        self.assertEqual(proof['INIT'],"1'b1")

    def test_actual_mutants_and_missing_correspondence_reject(self):
        old,new=self.circuits['old'],self.circuits['new']
        mailbox='u_bluetooth/u_core/application/command_endpoint/cpu_mailbox/'
        cases=[(mailbox+'admitted_count_0','ports','D',"1'b0"),
               (mailbox+'admitted_count_0','ports','CE',"1'b0"),
               (mailbox+'admitted_count_0','ports','CLEAR',"1'b0"),
               (mailbox+'next_ticket_0','ports','PRESET',"1'b0"),
               (mailbox+'next_ticket_0','parameters','INIT',"1'b0"),
               ('u_task3_media/raw_store/generation_8','ports','CLK','audio_clk')]
        for name,section,key,data in cases:
            path=new.state[name];saved=deepcopy(new.n.cells[path])
            try:
                new.n.cells[path][section][key]=data
                with self.assertRaises(ValueError):
                    compare(old,Circuit(new.n,self.e),name)
                self.rows.append(dict(mutation=name+'/'+key,rejected=True))
            finally:
                new.n.cells[path]=saved
        with self.assertRaises(ValueError):
            compare(old,new,'u_bluetooth/u_core/application/command_endpoint/fragment_error_2')
        self.rows.append(dict(missing_old_fragment_error_correspondence_rejected=True))


if __name__=='__main__':
    unittest.main()
