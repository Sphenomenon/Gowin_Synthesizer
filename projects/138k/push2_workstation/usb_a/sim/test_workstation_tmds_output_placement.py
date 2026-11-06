"""Protect the observed thirty-bit output boundary before changing locality."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_tmds_output_placement as placement


def fixture(routed=False):
    cells = {}
    for lane in range(3):
        stem = f'{placement.ROOT}/data_lanes[{lane}]'
        hard = dict(kind='OSER10', parameters={}, ports=dict(
            Q=f'out{lane}', PCLK='pixel', FCLK='serial', RESET='serializer_reset'))
        cells[stem+'.serializer/serializer'] = hard
        for bit in range(10):
            q, word = f'encoded{lane}_{bit}', f'word{lane}_{bit}'
            cells[f'{stem}.encoder/tmds_{bit}_s0'] = dict(kind='DFFRE',
                parameters={'INIT': "1'b0"}, ports=dict(
                    D=f'next{lane}_{bit}', Q=q, CLK='pixel', CE="1'b1", RESET='encoder_reset'))
            cells[f'{stem}.serializer/serial_word_{bit}_s2'] = dict(
                kind='LUT1' if routed else 'INV',
                parameters={'INIT': "2'h1"} if routed else {},
                ports={'I0':q,'F':word} if routed else {'I':q,'O':word})
            hard['ports']['D'+str(bit)] = word
    return SimpleNamespace(cells=cells, pin=lambda name, port: cells[name]['ports'][port])


class TmdsOutputPlacement(unittest.TestCase):
    def test_all_thirty_bits_and_polarity_bind_in_both_real_primitive_forms(self):
        self.assertEqual(placement.output_boundary(fixture(), routed=False),
                         placement.output_boundary(fixture(True), routed=True))

    def test_serializer_bit_permutations_and_cross_lane_aliases_rejected(self):
        for routed in (False, True):
            for bit in range(10):
                n=fixture(routed)
                path=f'{placement.ROOT}/data_lanes[2].serializer/serializer'
                n.cells[path]['ports']['D'+str(bit)] = 'word0_'+str((bit+1)%10)
                with self.subTest(routed=routed,bit=bit), self.assertRaisesRegex(ValueError,'bit order'):
                    placement.output_boundary(n, routed=routed)

    def test_missing_and_extra_output_registers_are_rejected(self):
        name=f'{placement.ROOT}/data_lanes[0].encoder/tmds_0_s0'
        for mode in ('missing','extra'):
            n=fixture()
            if mode=='missing': del n.cells[name]
            else: n.cells[name.replace('tmds_0','tmds_10')]=deepcopy(n.cells[name])
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError,'inventory'):
                placement.output_boundary(n,routed=False)

    def test_clock_reset_enable_and_polarity_corruption_rejected(self):
        ff=f'{placement.ROOT}/data_lanes[1].encoder/tmds_4_s0'
        gate=f'{placement.ROOT}/data_lanes[1].serializer/serial_word_4_s2'
        hard=f'{placement.ROOT}/data_lanes[1].serializer/serializer'
        for mode in ('clock','enable','ff_kind','ff_init','polarity','bit_source','hard_kind','hard_clock','hard_reset'):
            n=fixture(True)
            if mode=='clock': n.cells[ff]['ports']['CLK']='other'
            elif mode=='enable': n.cells[ff]['ports']['CE']="1'b0"
            elif mode=='ff_kind': n.cells[ff]['kind']='DFFCE'
            elif mode=='ff_init': n.cells[ff]['parameters']['INIT']="1'b1"
            elif mode=='polarity': n.cells[gate]['parameters']['INIT']="2'h2"
            elif mode=='bit_source': n.cells[gate]['ports']['I0']='encoded1_3'
            elif mode=='hard_kind': n.cells[hard]['kind']='OSER8'
            elif mode=='hard_clock': n.cells[hard]['ports']['FCLK']='pixel'
            else: n.cells[hard]['ports']['RESET']='pixel'
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                placement.output_boundary(n,routed=True)

    def test_CST_appends_only_sixty_logic_locations_and_preserves_all_parent_bytes(self):
        payload=('// retain complete parent constraints\n'+''.join(
            f'IO_LOC "{port}" '+','.join(balls)+';\n' for port,balls in placement.PIN_LOCATIONS.items())).encode()
        with patch.object(placement,'SynthesisNetlist',side_effect=[fixture(),fixture(True)]):
            after,evidence=placement.output_region_constraints(payload,'source','route')
        self.assertTrue(after.startswith(payload))
        self.assertEqual(after[len(payload):].hex(),evidence['exact_appended_bytes_hex'])
        self.assertEqual(len(evidence['constraints']),60)
        self.assertEqual(after[len(payload):].count(b'INS_LOC'),60)
        with patch.object(placement,'SynthesisNetlist',side_effect=[fixture(),fixture(True)]), \
                self.assertRaisesRegex(ValueError,'already has'):
            placement.output_region_constraints(after,'source','route')
        with self.assertRaisesRegex(ValueError,'pin pairs'):
            placement.output_region_constraints(payload.replace(b'J14,H14',b'J13,H13'),'source','route')


if __name__=='__main__':
    unittest.main()
