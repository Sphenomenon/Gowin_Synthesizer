"""Full ACK identity, four-state equivalence and missing-bit rejection."""
from pathlib import Path
import sys,tempfile,subprocess,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools import workstation_phone_ack_compare as repair

class AckCompare(unittest.TestCase):
    def test_actual_full_identity_and_mutations(self):
        source=(ROOT/repair.SOURCE).read_text();repair.normalize(source.encode())
        start=source.index('    // The routed ACK fence');end=source.index('    wire phone_arm_ack',start)
        block=source[start:end]
        tb='''module compare;
reg [255:0] rx_payload_i;reg [31:0] phone_boot,phone_session,phone_generation;
BLOCK
wire old_matches=rx_payload_i[160:65]=={phone_boot,phone_session,phone_generation};
integer i,j,checks=0;
task check;begin #1;if(phone_ack_matches!==old_matches)$fatal(1,"ACK mismatch %d",checks);checks=checks+1;end endtask
initial begin
rx_payload_i=0;phone_boot=0;phone_session=0;phone_generation=0;check;
for(i=65;i<=160;i=i+1)begin
rx_payload_i[i]=1;check;rx_payload_i[i]=1'bx;check;rx_payload_i[i]=1'bz;check;rx_payload_i[i]=0;
end
for(j=0;j<16384;j=j+1)begin
{phone_boot,phone_session,phone_generation}={$urandom,$urandom,$urandom};
rx_payload_i[160:65]={phone_boot,phone_session,phone_generation};
if(j%2)begin
 i=$urandom_range(65,160);
 case(j%3)0:rx_payload_i[i]=~rx_payload_i[i];1:rx_payload_i[i]=1'bx;2:rx_payload_i[i]=1'bz;endcase
end
check;end
$display("PASS actual phone ACK four-state checks=%0d",checks);$finish;end
endmodule
'''
        for name,before,after in [('actual',None,None),
            ('missing-byte','&phone_ack_equal_bytes','&phone_ack_equal_bytes[10:0]'),
            ('wrong-offset','65+phone_ack_byte*8','64+phone_ack_byte*8')]:
            with self.subTest(case=name),tempfile.TemporaryDirectory()as directory:
                p=Path(directory);selected=block
                if before:
                    self.assertEqual(selected.count(before),1);selected=selected.replace(before,after,1)
                (p/'test.sv').write_text(tb.replace('BLOCK',selected))
                r=subprocess.run(['iverilog','-g2012','-s','compare','-o',str(p/'test.vvp'),str(p/'test.sv')],capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stderr)
                r=subprocess.run(['vvp',str(p/'test.vvp')],capture_output=True,text=True,timeout=30)
                if before:self.assertNotEqual(r.returncode,0,r.stdout+r.stderr)
                else:
                    self.assertEqual(r.returncode,0,r.stdout+r.stderr)
                    self.assertIn('checks=16673',r.stdout)
if __name__=='__main__':unittest.main(verbosity=2)
