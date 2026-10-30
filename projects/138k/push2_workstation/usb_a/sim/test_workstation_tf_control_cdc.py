#!/usr/bin/env python3
"""Explicit c7 TF scope, exact vendor ALU truth and actual-VG fault controls.

Set GW138K_TF_CDC_STAGE/PROCESS for sealed synthesis inputs. No prepare/EDA,
original-netlist edits, SDC installation or hardware fallback is permitted.
"""
from pathlib import Path
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace
from collections import defaultdict

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import workstation_tf_control_cdc as tf
from tools.workstation_ble_ddr_prefix_cdc_endpoints import validate_synthesis_binding
from tools.workstation_ble_ddr_prefix_cdc_scope import validate_profile


class SourceAndPrimitive(unittest.TestCase):
    def test_maintained_sources_and_manifest(self):
        self.assertEqual(tf.source_bundle(ROOT)['direct_registered_pairs'],7)
        self.assertEqual(tf.sha(ROOT/tf.ENDPOINTS),tf.ENDPOINTS_SHA256)
        manifest=json.loads((ROOT/tf.ENDPOINTS).read_text())
        self.assertEqual((manifest['scope'],manifest['candidate']),(tf.SCOPE,tf.CANDIDATE))
        self.assertEqual(len(manifest['endpoint_closures']),9)
        with tempfile.TemporaryDirectory() as work:
            root=Path(work)
            for rel in tf.SOURCE_SHA256:
                (root/rel).parent.mkdir(parents=True,exist_ok=True)
                (root/rel).write_bytes((ROOT/rel).read_bytes())
            tf.source_bundle(root)
            p=root/next(iter(tf.SOURCE_SHA256));p.write_bytes(p.read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError,'maintained TF source identity'):tf.source_bundle(root)

    def test_scope_is_explicit_and_never_old_default(self):
        run=subprocess.run([sys.executable,str(ROOT/'tools/workstation_tf_control_cdc.py'),
            '--scope','runtime-r00-no-local-panel-v1','--stage','missing','--process','missing','--output','missing'],
            capture_output=True,text=True)
        self.assertEqual(run.returncode,2)
        self.assertIn('invalid choice',run.stderr)

    def test_observed_ALU3_truth_matches_unmodified_vendor_module(self):
        vendor=Path(os.environ.get('GW138K_TF_CDC_VENDOR_SIM',
            '/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/simlib/gw5a/prim_sim.v'))
        if not vendor.is_file():self.skipTest('exact installed vendor simulation source required')
        original=tf.sha(vendor);text=vendor.read_text()
        match=re.search(r'^module ALU \(.*?^endmodule[^\n]*',text,re.M|re.S)
        self.assertIsNotNone(match)
        # An audit-only extraction; vendor bytes are never rewritten.
        source=match.group(0)+'\n'
        tb='''`timescale 1ns/1ps
module alu_truth;
reg i0,i1,cin,i3;
wire sum,cout;
ALU #(.ALU_MODE(3)) dut(sum,cout,i0,i1,i3,cin);
integer k;
initial begin
for(k=0;k<16;k=k+1)begin {i3,cin,i1,i0}=k;#1;$display("V %0d %0d %0d",k,sum,cout);end
$finish;end
endmodule
'''
        with tempfile.TemporaryDirectory() as work:
            p=Path(work);(p/'alu.v').write_text(source);(p/'tb.sv').write_text(tb)
            c=subprocess.run(['iverilog','-g2012','-s','alu_truth','-o',str(p/'sim'),str(p/'alu.v'),str(p/'tb.sv')],capture_output=True,text=True)
            self.assertEqual(c.returncode,0,c.stdout+c.stderr)
            r=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        values=[tuple(map(int,m)) for m in re.findall(r'^V (\d+) ([01]) ([01])$',r.stdout,re.M)]
        self.assertEqual(len(values),16)
        class Net:
            cells={'alu':dict(kind='ALU',parameters=dict(ALU_MODE='3'),ports={})}
            def pin(self,p,pin):return dict(I0='a',I1='b',CIN='c',I3="1'b0")[pin]
        n=Net();g=SimpleNamespace(n=n,high={"1'b1"},low={"1'b0"},drivers=defaultdict(list,{'s':[('alu','SUM')],'o':[('alu','COUT')]}))
        b=tf.ExactTFDiagram(['a','b','c']);outputs=[b.net(g,k) for k in ('s','o')]
        def evaluate(node,bits):
            while node>1:
                index,low,high=b.nodes[node];node=high if bits[index] else low
            return node
        for k,s,o in values:
            bits=[(k>>i)&1 for i in range(3)]
            self.assertEqual(tuple(evaluate(node,bits) for node in outputs),(s,o))
        n.cells=copy.deepcopy(n.cells);n.cells['alu']['parameters']['ALU_MODE']='0'
        with self.assertRaisesRegex(ValueError,'unreviewed ALU'):tf.ExactTFDiagram(['a','b','c']).net(g,'o')
        self.assertEqual(original,tf.sha(vendor))
        output=os.environ.get('GW138K_TF_CDC_ALU_EVIDENCE')
        if output:Path(output).write_text(json.dumps(dict(vendor=str(vendor),vendor_sha256=original,
            extracted_module_sha256=hashlib.sha256(source.encode()).hexdigest(),vectors=values,BDD_outputs_match_all16=True,
            I3_both_levels_vendor_tested=True,production_audit_requires_I3_tied0=True,vendor_modified=False),indent=2)+'\n')


class ActualTF(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stage,process=os.environ.get('GW138K_TF_CDC_STAGE'),os.environ.get('GW138K_TF_CDC_PROCESS')
        if not stage or not process:raise unittest.SkipTest('explicit sealed c7 TF stage/process required')
        cls.stage,cls.process=Path(stage),Path(process)
        cls.before=tf.verify_synthesis_identity(cls.stage,cls.process)
        validate_synthesis_binding(cls.stage)
        cls.profile=json.loads((cls.stage.parents[1]/'workstation_profile.json').read_text())
        validate_profile(ROOT,cls.profile,stage=cls.stage)
        tf.source_bundle(ROOT,cls.stage)
        cls.n=tf.OwnerResetNetlist((cls.stage/tf.VG_RELATIVE).read_text(),tf.TOP)
        cls.baseline=tf.audit_netlist(ROOT,cls.n);cls.mutations=[]

    @classmethod
    def tearDownClass(cls):
        if cls.before!=tf.verify_synthesis_identity(cls.stage,cls.process):raise AssertionError('original synthesis inputs changed')
        tf.audit_netlist(ROOT,cls.n)
        output=os.environ.get('GW138K_TF_CDC_TEST_EVIDENCE')
        if output:Path(output).write_text(json.dumps(dict(schema=1,synthesis=cls.before,mutations=cls.mutations,
            mutation_count=len(cls.mutations),all_mutations_rejected=all(x['rejected'] for x in cls.mutations),
            original_VG_rewritten=False,original_SDC_rewritten=False,eda_invoked=False,hardware_operated=False,
            physical_CDC_accepted=False,deployment_allowed=False),indent=2,sort_keys=True)+'\n')

    def fault(self,label,path,pin,value,check=None,canonical=None,parameter=False):
        n=self.n;bindings=n.cells[path]['parameters' if parameter else 'ports'];before=bindings.get(pin)
        bindings[pin]=value
        try:
            if canonical is not None:self.assertEqual(n.pin(path,pin),canonical,'fault must bind the intended real net')
            with self.assertRaises(ValueError) as rejected:
                (check or (lambda a:tf.audit_netlist(ROOT,n)))(tf.Audit(n))
            self.mutations.append(dict(case=label,path=path,port_or_parameter=pin,rejected=True,error=str(rejected.exception)))
        finally:
            if before is None:bindings.pop(pin)
            else:bindings[pin]=before

    def test_nominal_complete_inventory_and_nonacceptance(self):
        r=self.baseline
        self.assertEqual(len(r['pairs']),8)
        self.assertEqual(len(r['held_control']['source']),36)
        self.assertTrue(r['held_control']['mapped_cancellation_gate']['universally_verified'])
        self.assertFalse(r['source']['source_seen_edge_alias_accepted'])
        for key in ('physical_CDC_accepted','complete_CDC_accepted','routed_timing_verified','hardware_tested',
                    'constraints_installed','source_or_netlist_modified','deployment_allowed'):self.assertFalse(r[key],key)

    def test_each_declared_pair_structure_and_first_Q_fanout_faults(self):
        n=self.n;g=tf.Graph(n)
        rows=list(tf.PAIRS)+[('memory-open-complement',tf.T,'memory_gate_sync',1,tf.T,'memory_open_sync','memory_clk','clk_50m')]
        for row in rows:
            key,s,stem,bit,ds,dstem,sc,dc=row
            p,x,y=g.register(s,stem,bit),g.register(ds,dstem,0),g.register(ds,dstem,1)
            check=lambda a,row=row:a.pair(row,inverted=row[0]=='memory-open-complement')
            source_clock=n.cells[p]['ports']['CLK'];dest_clock=n.cells[x]['ports']['CLK']
            first_q=n.cells[x]['ports']['Q']
            cases=[
                ('producer clock',p,'CLK',dest_clock,dc),
                ('first clock',x,'CLK',source_clock,sc),
                ('first D bypass',x,'D',"1'b0","1'b0"),
                ('first conditional CE',x,'CE',"1'b0","1'b0"),
                ('first Q extra D',p,'D',first_q,n.pin(x,'Q')),
                ('first Q extra CE',p,'CE',first_q,n.pin(x,'Q')),
                ('second D bypass',y,'D',"1'b0","1'b0"),
                ('second CLEAR mismatch',y,'CLEAR',"1'b0","1'b0"),
            ]
            for label,path,pin,value,canonical in cases:
                with self.subTest(pair=key,fault=label):self.fault(key+' '+label,path,pin,value,check,canonical)
            with self.subTest(pair=key,fault='first INIT'):self.fault(key+' first INIT',x,'INIT',"1'b1",check,parameter=True)

    def test_complete_local_closure_additions_fail(self):
        n=self.n;g=tf.Graph(n)
        excluded={x['path'] for r in self.baseline['pairs'].values() for x in (r['declared_producer'],r['first'],r['second'])}
        for label,record,closure in (
            ('publisher local consumer',self.baseline['pairs']['control-request']['declared_producer'],self.baseline['pairs']['control-request']['source_Q_complete']),
            ('second local consumer',self.baseline['pairs']['control-ACK']['second'],self.baseline['pairs']['control-ACK']['second_Q_complete'])):
            p=record['path'];raw=n.cells[p]['ports']['Q'];scope=n.scopes[p]
            target=next(x for x in g.regs if x not in excluded and n.scopes[x]==scope and n.pin(x,'CLK')==record['clock']
                        and x+'/CE' not in closure['ff_endpoints'] and n.pin(x,'CE')!=record['q'])
            self.fault(label,target,'CE',raw,canonical=record['q'])

    def test_publisher_frontier_cannot_read_foreign_state(self):
        n=self.n;g=tf.Graph(n)
        for key in ('quiet-publication','memory-stop','memory-quiet'):
            row=next(r for r in tf.PAIRS if r[0]==key)
            r=self.baseline['pairs'][key];p=r['declared_producer']['path'];scope=n.scopes[p]
            excluded={z['path'] for z in (r['declared_producer'],r['first'],r['second'])}
            foreign=next(x for x in g.regs if x not in excluded and n.scopes[x]==scope and n.pin(x,'CLK')!=r['declared_producer']['clock'])
            for pin in ('D','CE'):
                self.fault(key+' publisher '+pin+' reads foreign Q',p,pin,n.cells[foreign]['ports']['Q'],lambda a,row=row:a.pair(row),canonical=n.pin(foreign,'Q'))

    def test_held_payload_capture_toggle_and_gate_faults(self):
        n=self.n;g=tf.Graph(n);reg=lambda name,bit=None:g.register(tf.T,name,bit)
        h,c=reg('held_control',0),reg('compute_control',0)
        for label,path,pin,value in (
            ('held source unconditional overwrite',h,'CE',"1'b1"),
            ('request toggle removed',reg('control_request'),'D',"1'b0"),
            ('compute capture disabled',c,'CE',"1'b0"),
            ('held payload wrong bit',c,'D',n.cells[reg('held_control',1)]['ports']['Q']),
            ('ACK disabled',reg('control_ack'),'CE',"1'b0"),
            ('capture delay removed',reg('control_capture'),'D',"1'b0"),
        ):self.fault(label,path,pin,value,lambda a:a.held())
        source_update=g.drivers[n.pin(h,'CE')][0][0]
        self.assertTrue(n.cells[source_update]['kind'].startswith('LUT'))
        for label,path in (('source update LUT',source_update),('mapped cancellation gate LUT','u_managed/n1033_s1')):
            init=n.cells[path]['parameters']['INIT'];width=re.match(r'(\d+)\x27h',init)[1]
            self.fault(label,path,'INIT',width+"'h0",lambda a:a.held(),parameter=True)
        self.fault('observed NE ALU mode','u_tf_audio/n2649_s0','ALU_MODE','0',lambda a:a.held(),parameter=True)
        self.fault('observed NE ALU I3','u_tf_audio/n2649_s0','I3',"1'b1",lambda a:a.held())

    def test_associated_primitive_clocks_preserve_port_roles(self):
        n=self.n
        row=next(p for p in tf.PAIRS if p[0]=='memory-stop')
        for ep in self.baseline['pairs']['memory-stop']['second_Q_complete']['primitive_endpoints']:
            p=ep.rsplit('/',1)[0]
            self.assertEqual(n.pin(p,'CLKA'),'memory_clk');self.assertEqual(n.pin(p,'CLKB'),'clk_50m')
            self.fault('SDPB CEA associated CLKA',p,'CLKA',n.cells[p]['ports']['CLKB'],lambda a:a.pair(row),canonical='clk_50m')
        for ep in self.baseline['held_control']['destination_Q_complete']['primitive_endpoints']:
            self.fault('MULTALU audio CLK removed',ep.rsplit('/',1)[0],'CLK',"{1'b0,1'b0}",lambda a:a.held())

    def test_candidate_manifest_and_compiled_source_drifts(self):
        for label,key,value in (('candidate','candidate_identity','new-Chorus-identity'),('input','candidate_input_sha256','0'*64)):
            p=copy.deepcopy(self.profile);p[key]=value
            with self.assertRaises(ValueError):validate_profile(ROOT,p)
        with tempfile.TemporaryDirectory() as work:
            root=Path(work)
            for rel in (*tf.SOURCE_SHA256,tf.ENDPOINTS):
                (root/rel).parent.mkdir(parents=True,exist_ok=True);(root/rel).write_bytes((ROOT/rel).read_bytes())
            manifest=root/tf.ENDPOINTS;manifest.write_bytes(manifest.read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError,'manifest bytes changed'):tf.audit_netlist(root,self.n)
            contents=json.loads(manifest.read_text());contents['candidate']='different-candidate'
            manifest.write_text(json.dumps(contents))
            with mock.patch.object(tf,'ENDPOINTS_SHA256',tf.sha(manifest)),self.assertRaisesRegex(ValueError,'consumer closure changed'):
                tf.audit_netlist(root,self.n)
            source=root/next(iter(tf.SOURCE_SHA256));source.write_bytes(source.read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError,'compiled TF source identity'):tf.source_bundle(ROOT,root)
            vg=root/tf.VG_RELATIVE;vg.parent.mkdir(parents=True);vg.write_text('unreviewed mapped topology')
            with self.assertRaises(ValueError):validate_synthesis_binding(root)


if __name__=='__main__':unittest.main()
