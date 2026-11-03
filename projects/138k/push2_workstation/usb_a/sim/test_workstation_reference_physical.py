"""Historical physical references must bind the exact current signal inventory."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.workstation_custom_board_implementation import reference_constraints, implementation_script
from tools.workstation_resource_physical import CHECKERS, adapt, sha, fifo_head_domains, primitive_inventory

NETLIST = '''module workstation_custom_138k_top(clk_50m, ddr_ck, ddr_ck_n);
input clk_50m;
output ddr_ck;
output ddr_ck_n;
endmodule
'''
CST = b'IO_LOC "clk_50m" V22;\nIO_LOC "ddr_ck" L3,K3;\n'


class ReferencePhysical(unittest.TestCase):
    def test_inline_ram_does_not_hide_following_routed_primitives(self):
        class Design:
            cells = {'before': ('DFFR', {})}
            def add_driver(self, net, name, pin):
                if net in self.drivers:
                    raise ValueError('multiple drivers')
                self.drivers[net] = name, pin
        vo = '''module top(clk);
DFFR before (.CLK(clk), .D(d), .Q(q));
RAM16SDP4 \\head.ram (.CLK(clk), .DO({pad, r2, r1, r0}));
LUT4 \\after.lut (.I0(r0), .F(x));
ALU add (.I0(x), .CIN(c0), .SUM(s), .COUT(c1));
DFFR capture (.CLK(clk), .D(s), .Q(out));
endmodule
'''
        result = primitive_inventory(Design(), vo)
        self.assertEqual(set(result.cells), {'before', 'head.ram', 'after.lut', 'add', 'capture'})
        self.assertEqual(result.drivers, {'q': ('before', 'Q'), 'x': ('after.lut', 'F'),
                                        's': ('add', 'SUM'), 'c1': ('add', 'COUT'),
                                        'out': ('capture', 'Q')})
        with self.assertRaisesRegex(ValueError, 'duplicate routed primitive'):
            primitive_inventory(Design(), vo+'\nLUT1 capture (.I0(x), .F(y));')
        with self.assertRaisesRegex(ValueError, 'lost historical'):
            primitive_inventory(Design(), vo.replace('before', 'renamed'))

    def test_differential_complement_and_explicit_retired_port(self):
        actual, proof = reference_constraints(CST+b'IO_LOC "clk_16m9344" J19;\n', NETLIST, ['clk_16m9344'])
        self.assertEqual(actual, CST)
        self.assertEqual(proof['port_bits'], 3)
        self.assertEqual(proof['differential_complements'], {'ddr_ck_n': 'K3'})
        self.assertEqual(len(proof['omitted']), 1)

    def test_missing_extra_and_duplicate_package_assignments_fail(self):
        for payload in (b'IO_LOC "clk_50m" V22;\n', CST+b'IO_LOC "other" J19;\n',
                        CST.replace(b'L3,K3', b'V22,K3'), CST+b'INS_LOC "missing" PLL_R[0];\n',
                        CST+b'CLOCK_LOC "missing" BUFG = CLK;\n'):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                reference_constraints(payload, NETLIST)
        with self.assertRaises(ValueError):
            reference_constraints(CST, NETLIST, ['clk_50m'])

    def test_historical_checker_changes_only_evidence_schema(self):
        root = Path(__file__).resolve().parents[1]
        for kind, (filename, expected) in CHECKERS.items():
            path = root/'reports/workstation_physical_20261025'/filename
            self.assertEqual(sha(path), expected)
            original = path.read_text()
            adapted = adapt(kind, original)
            compile(adapted, filename, 'exec')
            if kind not in ('routes', 'cdc'):
                self.assertEqual(adapted, original)
            else:
                if kind == 'routes':
                    self.assertIn("if parent['identity'].startswith('custom138k-native-integration-20261102-'):", adapted)
                else:
                    self.assertIn('adapted = extend_resource_cdc(adapted)', adapted)
                # Every delay assertion remains byte-identical.
                self.assertEqual([line for line in original.splitlines() if 'assert' in line],
                                 [line for line in adapted.splitlines() if 'assert' in line])

    def test_async_fifo_head_uses_proven_read_address_domain(self):
        class Design:
            clock_net = 'write50'
            def __init__(self):
                scope = 'u_bluetooth/g_store.u_store/u_commands'
                self.cells, self.drivers = {}, {}
                for stem, clock in [('write_binary', 'write50'), ('read_binary', 'read100')]:
                    for bit in range(4):
                        name = scope+'/'+stem+'_'+str(bit)+'_s0'
                        net = stem+str(bit)
                        self.cells[name] = ('DFFR', dict(CLK=clock, Q=net))
                        self.drivers[net] = name, 'Q'
                for ram in range(12):
                    self.cells[scope+'/g_small_head.ram'+str(ram)] = ('RAM16SDP4', dict(
                        CLK='write50', WAD=','.join('write_binary'+str(i) for i in reversed(range(4))),
                        RAD=','.join('read_binary'+str(i) for i in reversed(range(4))),
                        DO=','.join('out'+str(ram*4+i) for i in range(4))))
            def bits(self, expression):
                return expression.split(',')
        design = Design()
        domains = fifo_head_domains(design, 'read100')
        self.assertEqual(len(domains), 48)
        self.assertTrue(all(domain == {'read100'} for domain in domains.values()))
        scope = 'u_bluetooth/g_store.u_store/u_commands'
        design.cells[scope+'/read_binary_2_s0'][1]['CLK'] = 'write50'
        with self.assertRaisesRegex(ValueError, 'address provenance'):
            fifo_head_domains(design, 'read100')
        design = Design()
        design.cells[scope+'/g_small_head.ram0'][1]['CLK'] = 'read100'
        with self.assertRaisesRegex(ValueError, 'write clock'):
            fifo_head_domains(design, 'read100')

    def test_explicit_physical_algorithm_and_identity(self):
        script = implementation_script('C21102A2', 4, 1)
        for option in ('-place_option 4', '-route_option 1', '-user_code C21102A2',
                       '-replicate_resources 0', '-correct_hold_violation 1'):
            self.assertIn(option, script)
        for code in ('', 'C21102A', 'not-code'):
            with self.assertRaises(ValueError):
                implementation_script(code)


if __name__ == '__main__':
    unittest.main()
