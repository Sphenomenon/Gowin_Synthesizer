"""Bind the full32 equality experiment to its one original owner consumer."""
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import workstation_task3_capture_compare as ordering
from tools import workstation_task3_capture_identity_experiment as identity

class CaptureIdentityExperiment(unittest.TestCase):
    def parent(self):
        native=(ROOT/identity.SOURCE).read_text()
        return native.replace(ordering.PARAMETER,ordering.SELECTED,1)

    def test_exact_parent_inverse_and_only_existing_LAST_CAPTURE_ID_consumer_changes(self):
        parent=self.parent()
        selected=identity.apply(parent)
        self.assertEqual(identity.restore(selected),parent)
        self.assertEqual(identity.digest(parent),identity.PARENT_SHA256)
        evidence=identity.evidence(selected)
        self.assertEqual((evidence['compared_bits'],evidence['groups'],evidence['group_bits']),(32,4,8))
        self.assertEqual((evidence['extra_cycles'],evidence['new_state_bits']),(0,0))
        self.assertIn('snapshot[17]==capture_id',selected)
        self.assertIn('command_response_data_i==0 || capture_not_newer',selected)

    def test_direct_default_or_unknown_parent_or_duplicate_application_rejected(self):
        native=(ROOT/identity.SOURCE).read_text()
        for text in (native,self.parent()+'\n',identity.apply(self.parent())):
            with self.subTest(length=len(text)),self.assertRaises(ValueError):identity.apply(text)

    def test_changed_operand_consumer_and_unrelated_state_rejected(self):
        selected=identity.apply(self.parent())
        for before,after in [('.capture_i(capture_id)','.capture_i(last_capture_id)'),
            ('.response_i(command_response_data_i)','.response_i(32\'d0)'),
            (identity.AFTER,identity.AFTER.replace('!capture_identity_matches','capture_identity_matches')),
            ('last_capture_id<=0','last_capture_id<=1')]:
            with self.subTest(before=before),self.assertRaises(ValueError):
                identity.restore(selected.replace(before,after,1))

    def test_actual_RTL_preserves_all32_bits_and_four_state_equality(self):
        bench='''module tb;
reg [31:0] a,b; wire equal_result;
workstation_task3_capture_identity32 dut(.response_i(a),.capture_i(b),.matches_o(equal_result));
integer bit_index,i,seed=32'h138032,checks=0;
task check;begin
  #1;if(equal_result !== (a==b))$fatal(1,"full32 four-state equality differs a=%h b=%h",a,b);
  checks=checks+1;
end endtask
initial begin
  a=0;b=0;check();a=32'hffffffff;b=a;check();
  for(bit_index=0;bit_index<32;bit_index=bit_index+1)begin
    a=0;b=32'd1<<bit_index;check();
    a=b;b=0;check();
    a=0;b=0;a[bit_index]=1'bx;check();
    a=0;b=0;b[bit_index]=1'bz;check();
    a=0;b=32'd1<<((bit_index+8)%32);a[bit_index]=1'bx;check();
    a=0;b=32'd1<<((bit_index+8)%32);b[bit_index]=1'bz;check();
  end
  for(i=0;i<1024;i=i+1)begin
    a=$random(seed);b=$random(seed);check();b=a;check();
    a[i%32]=1'bx;check();b[(i+8)%32]=~b[(i+8)%32];check();
  end
  $display("PASS capture_identity four_state checks=%0d",checks);$finish;
end
endmodule
'''
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);source=out/'bench.sv';source.write_text(bench);binary=out/'bench.vvp'
            compiled=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(binary),str(source),str(ROOT/identity.COMPARATOR)],
                capture_output=True,text=True,timeout=30)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            ran=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=30)
            self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)
            self.assertIn('PASS capture_identity four_state checks=4290',ran.stdout)

if __name__=='__main__':unittest.main()
