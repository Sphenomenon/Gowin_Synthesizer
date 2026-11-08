"""Actual peer/session comparator, X/Z equality and omitted-bit rejection."""
from pathlib import Path
from copy import deepcopy
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_record_peer_compare as repair
from tools import workstation_w_context_compare as context


class RecordPeerCompare(unittest.TestCase):
    def test_actual_mapped_all_peer_bits(self):
        selected = os.environ.get('GW138K_PREBOARD_W_STAGE')
        if not selected:
            self.skipTest('explicit actual W synthesis stage required')
        from tools.workstation_native_protocol_audit import protocol_netlist
        from tools.workstation_runtime_pcm_cdc import Graph
        n = protocol_netlist((Path(selected) / 'impl/gwsynthesis/custom_138k_integration.vg').read_text(),
                             mapping='synthesis')
        evidence = repair.audit_mapped(n)
        self.assertEqual(evidence['compared_peer_session_bits'], 64)
        g = Graph(n)
        for row in evidence['byte_equations']:
            # Remove one actual mapped input in each byte; the proof must reject
            # both the lost operand and any changed final byte truth table.
            frontier = g.carry_frontier(row['output'])
            carry = next(iter(frontier))
            path, _ = g.drivers[carry][0]
            old = deepcopy(n.cells[path])
            try:
                n.cells[path]['ports']['I0'] = "1'b0"
                with self.subTest(byte=row['byte']), self.assertRaises(ValueError):
                    repair.audit_mapped(n)
            finally:
                n.cells[path] = old

    def test_actual_four_state_comparison(self):
        source = (ROOT / repair.SOURCE).read_text()
        parent = repair.normalize(source.encode())
        self.assertEqual(context.normalize(source.encode()), context.normalize(parent))
        begin = source.index('    // The routed record CANCEL fence')
        end = source.index('    reg [95:0] record_active_common', begin)
        block = source[begin:end]
        tb = '''module compare;
reg [95:0] record_wire_common;
reg [31:0] peer_boot_i,session_i;
BLOCK
wire old_matches=record_wire_common[95:32]=={peer_boot_i,session_i} && record_wire_common[31:0]!=0;
integer i,j,checks=0;
task check;begin #1;if(record_matches!==old_matches)$fatal(1,"peer mismatch %d",checks);checks=checks+1;end endtask
initial begin
peer_boot_i=32'h13572468;session_i=32'h89abcdef;
record_wire_common={peer_boot_i,session_i,32'd1};check;
for(i=0;i<96;i=i+1)begin
record_wire_common={peer_boot_i,session_i,32'd1};
record_wire_common[i]=~record_wire_common[i];check;
record_wire_common[i]=1'bx;check;record_wire_common[i]=1'bz;check;
end
for(j=0;j<16384;j=j+1)begin
{peer_boot_i,session_i}={$urandom,$urandom};
record_wire_common={peer_boot_i,session_i,$urandom};
case(j%8)
0:record_wire_common[31:0]=0;
1:record_wire_common[31:0]=32'bx;
2:record_wire_common[31:0]=32'bz;
default:begin i=$urandom_range(32,95);
case(j%3)0:record_wire_common[i]=~record_wire_common[i];
1:record_wire_common[i]=1'bx;2:record_wire_common[i]=1'bz;endcase end
endcase
check;end
$display("PASS actual record peer four-state checks=%0d",checks);$finish;end
endmodule
'''
        controls = [('actual', None, None),
                    ('missing-byte', '&record_peer_equal_bytes', '&record_peer_equal_bytes[6:0]'),
                    ('wrong-offset', '32+record_peer_byte*8', '31+record_peer_byte*8'),
                    ('wrong-peer', '{peer_boot_i,session_i}', '{session_i,peer_boot_i}')]
        for name, before, after in controls:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as directory:
                path = Path(directory)
                selected = block
                if before:
                    self.assertEqual(selected.count(before), 1)
                    selected = selected.replace(before, after, 1)
                    with self.assertRaises(ValueError):
                        repair.normalize(source.replace(block, selected, 1).encode())
                (path / 'test.sv').write_text(tb.replace('BLOCK', selected))
                result = subprocess.run(['iverilog', '-g2012', '-s', 'compare', '-o',
                                         str(path / 'test.vvp'), str(path / 'test.sv')],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                result = subprocess.run(['vvp', str(path / 'test.vvp')],
                                        capture_output=True, text=True, timeout=30)
                if before:
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                else:
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('checks=16673', result.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
