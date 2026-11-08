"""Actual CANCEL predicates: four-state comparisons and omitted-bit controls."""
from pathlib import Path
import sys,tempfile,subprocess,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools import workstation_record_cancel_compare as repair
PREAMBLE='`include "rtl/workstation/task3_paired_channels.vh"\nmodule compare;\nreg [255:0] rx_payload_i;reg [95:0] record_active_common;\nwire [95:0] record_wire_common=rx_payload_i[193:98];\nwire record_packet=1;\n'
ENDING='\nwire old_cancel=rx_payload_i[195:194]==`TASK3_PAIR_KIND_CANCEL && rx_payload_i[97:0]==0;\nwire old_active=record_wire_common==record_active_common;\ninteger i,j,checks=0;\ntask check;begin #1;if(record_cancel!==old_cancel || record_active_matches!==old_active)$fatal(1,"compare %d",checks);checks=checks+1;end endtask\ninitial begin\nrx_payload_i=0;record_active_common=0;rx_payload_i[195:194]=`TASK3_PAIR_KIND_CANCEL;check;\nfor(i=0;i<256;i=i+1)begin rx_payload_i[i]=1;check;rx_payload_i[i]=1\'bx;check;rx_payload_i[i]=1\'bz;check;rx_payload_i[i]=0;end\nfor(i=0;i<96;i=i+1)begin record_active_common[i]=1;check;record_active_common[i]=1\'bx;check;record_active_common[i]=1\'bz;check;record_active_common[i]=0;end\nfor(j=0;j<16384;j=j+1)begin\nfor(i=0;i<256;i=i+1)case($urandom_range(0,7))0:rx_payload_i[i]=1\'bx;1:rx_payload_i[i]=1\'bz;default:rx_payload_i[i]=$urandom_range(0,1);endcase\nfor(i=0;i<96;i=i+1)case($urandom_range(0,7))0:record_active_common[i]=1\'bx;1:record_active_common[i]=1\'bz;default:record_active_common[i]=$urandom_range(0,1);endcase\ncheck;end\n$display("PASS actual record comparator four-state checks=%0d",checks);$finish;end\nendmodule\n'

class CancelCompare(unittest.TestCase):
    def test_actual_comparators_and_missing_bits(self):
        source=(ROOT/repair.SOURCE).read_text();repair.normalize(source.encode())
        start=source.index('    (* syn_keep=1 *) wire [12:0] record_cancel_zero_bytes;')
        end=source.index('    reg record_ack_pending',start);block=source[start:end]
        for label,a,b in [('actual',None,None),('omitted-padding-bit','[97:96]','[96:96]'),
            ('omitted-key-bit','record_active_common[record_byte*8+:8]',"{1'b0,record_active_common[record_byte*8+:7]}")]:
            with self.subTest(label=label),tempfile.TemporaryDirectory()as directory:
                directory=Path(directory);tb=directory/'compare.sv';selected=block
                if a:
                    self.assertEqual(selected.count(a),1);selected=selected.replace(a,b,1)
                tb.write_text(PREAMBLE+selected+ENDING);binary=directory/'compare.vvp'
                p=subprocess.run(['iverilog','-g2012','-I'+str(ROOT),'-s','compare','-o',str(binary),str(tb)],capture_output=True,text=True)
                self.assertEqual(p.returncode,0,p.stdout+p.stderr)
                p=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=30)
                if a:self.assertNotEqual(p.returncode,0,p.stdout+p.stderr)
                else:
                    self.assertEqual(p.returncode,0,p.stdout+p.stderr)
                    self.assertIn('checks=17441',p.stdout)

if __name__=='__main__':unittest.main(verbosity=2)
