#!/usr/bin/env python3
"""Same-edge status generation fencing, historical inverse and actual mapping."""
from pathlib import Path
from copy import deepcopy
import json,os,sys,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools import workstation_tf_status_compare as compare
from tools import workstation_tf_compute_local_release as reset
from tools import workstation_tf_native_head as head

class Selection(unittest.TestCase):
    def test_inverse_selection_and_four_state_fencing(self):
        text=(ROOT/compare.SOURCE).read_text();manifest=json.loads((ROOT/compare.MANIFEST).read_text())
        self.assertEqual(compare.digest(compare.restore(text)),manifest['parent_sha256'])
        config={compare.KEY:compare.POLICY,head.KEY:head.POLICY,reset.KEY:reset.POLICY,
                'demo_role':'M','tf_policy':'task3_m_native_direct_tf_v1'}
        with tempfile.TemporaryDirectory()as directory:
            stage=Path(directory)
            for relative in (reset.SERVICE,reset.BRIDGE):
                p=stage/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/relative).read_bytes())
            receipt=reset.select(stage,config)
            self.assertEqual(receipt['status_generation_compare']['extra_cycles'],0)
            selected=(stage/reset.SERVICE).read_text()
            self.assertEqual(reset.unselect(selected),text)
            self.assertEqual(reset.restore(reset.SERVICE,selected),reset.restore(reset.SERVICE,text))
            with self.assertRaises(ValueError):compare.configured(dict(config,demo_role='W'))
            corrupt=text.replace('36+status_byte*8+:8','35+status_byte*8+:8',1)
            with self.assertRaises(ValueError):compare.restore(corrupt)
            block=manifest['edits'][1]['after']
            tb='''module tb;
parameter bit PARALLEL_STATUS_COMPARE_ENABLE=1;
reg expected_valid;reg [67:0]compute_status;reg[31:0]expected_generation_o;
wire reference_current=expected_valid && compute_status[67:36]==expected_generation_o;
'''+block+'''
task check;begin #1;if(status_current!==reference_current)$fatal(1,"generation fence differs");end endtask
reg[1:0]symbols[0:3];integer i,j,k,t;
initial begin
symbols[0]=0;symbols[1]=1;symbols[2]=2'bxx;symbols[3]=2'bzz;
compute_status=0;expected_generation_o=0;expected_valid=1;check();
for(i=0;i<32;i=i+1)begin
 for(j=0;j<4;j=j+1)for(k=0;k<4;k=k+1)begin
  compute_status=0;expected_generation_o=0;
  compute_status[36+i]=symbols[j][0];expected_generation_o[i]=symbols[k][0];
  for(t=0;t<4;t=t+1)begin expected_valid=symbols[t][0];check();end
 end
end
for(i=0;i<2000;i=i+1)begin
compute_status[67:36]=$random;expected_generation_o=$random;expected_valid=$random;check();
expected_generation_o=compute_status[67:36];check();
end
$display("PASS all32 single-bit 4-state pairs, validity and random full words");$finish;
end endmodule
'''
            (stage/'tb.sv').write_text(tb)
            r=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(stage/'tb.vvp'),str(stage/'tb.sv')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            r=subprocess.run(['vvp',str(stage/'tb.vvp')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('PASS all32',r.stdout)

class Actual(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected=os.environ.get('GW138K_PREBOARD_M_STAGE')
        if not selected:raise unittest.SkipTest('explicit selected complete M stage required')
        from tools.workstation_native_protocol_audit import protocol_netlist
        cls.stage=Path(selected);cls.vg=cls.stage/'impl/gwsynthesis/custom_138k_integration.vg'
        cls.before=compare.digest(cls.vg.read_bytes());cls.n=protocol_netlist(cls.vg.read_text(),mapping='synthesis')
    @classmethod
    def tearDownClass(cls):assert compare.digest(cls.vg.read_bytes())==cls.before
    def test_actual_full32_and_corrupt_byte(self):
        from tools.workstation_runtime_pcm_cdc import Graph
        n=self.n;g=Graph(n);r=compare.audit_mapped(n,stage=self.stage)
        self.assertIsNotNone(r);self.assertEqual(r['compared_bits'],32)
        self.assertEqual(r['public_status_outputs_proven'],1)
        for row in r['byte_equations']:
            p,pin=g.drivers[row['net']][0];old=deepcopy(n.cells[p])
            n.cells[p]['parameters']['INIT']="8'hFF"
            try:
                with self.subTest(byte=row['byte']),self.assertRaises(ValueError):compare.audit_mapped(n,stage=self.stage)
            finally:n.cells[p]=old

if __name__=='__main__':unittest.main()
