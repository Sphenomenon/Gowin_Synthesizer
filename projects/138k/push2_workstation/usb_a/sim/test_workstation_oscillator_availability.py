#!/usr/bin/env python3
from pathlib import Path
from copy import deepcopy
import json,os,sys,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools import workstation_oscillator_availability as available

class Source(unittest.TestCase):
    def test_exact_inverse_and_four_state_reduction(self):
        source=(ROOT/available.SOURCE).read_bytes();d=json.loads((ROOT/available.MANIFEST).read_text())
        parent=available.restore(available.SOURCE,source)
        self.assertEqual(available.digest(parent),d['parent_sha256'])
        mutant=source.replace(b'allocation_candidates[allocation_group*4+:4]',b'allocation_candidates[allocation_group*4+:3]',1)
        with self.assertRaises(ValueError):available.restore(available.SOURCE,mutant)
        block=d['edits'][0]['after']
        tb='''module tb;reg[31:0]allocation_candidates;wire allocation_found;
wire expected=|allocation_candidates;
'''+block+'''
integer i,j;reg[1:0]sym[0:3];
task check;begin #1;if(allocation_found!==expected)$fatal(1,"availability changed");end endtask
initial begin sym[0]=0;sym[1]=1;sym[2]=2'bxx;sym[3]=2'bzz;
allocation_candidates=0;check();allocation_candidates='1;check();
for(i=0;i<32;i=i+1)for(j=0;j<4;j=j+1)begin
allocation_candidates=0;allocation_candidates[i]=sym[j][0];check();
allocation_candidates='1;allocation_candidates[i]=sym[j][0];check();end
for(i=0;i<4000;i=i+1)begin allocation_candidates=$random;check();end
$display("PASS all32 positions four-state availability and random words");$finish;end endmodule
'''
        with tempfile.TemporaryDirectory()as directory:
            p=Path(directory);(p/'tb.sv').write_text(tb)
            r=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'tb.vvp'),str(p/'tb.sv')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            r=subprocess.run(['vvp',str(p/'tb.vvp')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('PASS all32',r.stdout)

class Actual(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stage=os.environ.get('GW138K_PREBOARD_M_STAGE')
        if not stage:raise unittest.SkipTest('explicit complete M synthesis stage required')
        from tools.workstation_native_protocol_audit import protocol_netlist
        cls.vg=Path(stage)/'impl/gwsynthesis/custom_138k_integration.vg'
        cls.before=available.digest(cls.vg.read_bytes());cls.n=protocol_netlist(cls.vg.read_text(),mapping='synthesis')
    @classmethod
    def tearDownClass(cls):assert available.digest(cls.vg.read_bytes())==cls.before
    def test_actual_groups_and_corruptions(self):
        from tools.workstation_runtime_pcm_cdc import Graph
        n=self.n;g=Graph(n);r=available.audit_mapped(n);self.assertEqual(len(r['preserved_groups']),8)
        for row in r['preserved_groups']:
            p,pin=g.drivers[row['net']][0];old=deepcopy(n.cells[p])
            n.cells[p]['ports']['I0']="1'b0"
            try:
                with self.subTest(group=row['group']),self.assertRaises(ValueError):available.audit_mapped(n)
            finally:n.cells[p]=old

if __name__=='__main__':unittest.main()
