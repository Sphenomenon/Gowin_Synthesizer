#!/usr/bin/env python3
"""Actual B6 repair mappings: tag bits, isolated first capture, held placement."""
from pathlib import Path
import copy,json,os,re,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_runtime_pcm_cdc import Graph,B,prove_reply_byte_headers
from tools.workstation_preboard_physical_boundaries import w_routed_first_captures,audit as boundary_audit
from tools.workstation_task3_preboard_held_timing import audit,placement,w_native_placement


class RoutedRepairs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected=os.environ.get('GW138K_PREBOARD_W_STAGE')
        if not selected:raise unittest.SkipTest('explicit actual byte-header W synthesis stage required')
        cls.stage=Path(selected)
        cls.n=protocol_netlist((cls.stage/'impl/gwsynthesis/custom_138k_integration.vg').read_text(),mapping='synthesis')

    def test_all_header_bytes_and_corrupt_predicates(self):
        n=self.n;g=Graph(n);source=g.group(B,'held_reply',98)
        cuts=prove_reply_byte_headers(n,g,source);self.assertEqual(len(cuts),8)
        for net in sorted(cuts):
            path,pin=g.drivers[net][0];old=copy.deepcopy(n.cells[path])
            with self.subTest(net=net):
                if old['kind']=='ALU':n.cells[path]['ports']['I0']="1'b0"
                else:n.cells[path]['parameters']['INIT']="4'h0"
                try:
                    with self.assertRaises(ValueError):prove_reply_byte_headers(n,Graph(n),source)
                finally:n.cells[path]=old
        print('HEADER eight exact byte predicates; eight corrupted predicates rejected')

    def test_routed_first_captures_and_corrupt_chains(self):
        n=self.n;g=Graph(n);r,sdc=w_routed_first_captures(n)
        self.assertEqual(len(r['chains']),6)
        self.assertEqual(r['fifo_binary_next_Q_equations'],3)
        self.assertEqual(sdc.count('set_false_path -hold '),1)
        for row in r['chains']:
            path=row['registers'][1];old=copy.deepcopy(n.cells[path])
            with self.subTest(path=path):
                n.cells[path]['ports']['D']="1'b0"
                try:
                    with self.assertRaises(ValueError):w_routed_first_captures(n)
                finally:n.cells[path]=old
        path=g.register('u_task3_media/cnn_stream/task_service/staging_requests','read_gray',0)
        old=copy.deepcopy(n.cells[path]);n.cells[path]['ports']['D']="1'b0"
        try:
            with self.assertRaises(ValueError):w_routed_first_captures(n)
        finally:n.cells[path]=old
        print('CDC six isolated chains and five exact binary/Gray next-Q equations; seven corruptions rejected')

    def test_F808_complete_finite_placement(self):
        r,sdc=audit(self.n,role='W');cst=(self.stage/'constraints/custom_138k.cst').read_bytes()
        selected,e=placement(cst,r)
        self.assertTrue(selected.startswith(cst));self.assertEqual(len(e['registers']),164)
        self.assertIn('set_min_delay 1.800',sdc);self.assertTrue(e['payload_hold_checks_retained'])
        with self.assertRaises(ValueError):placement(selected,r)
        missing=copy.deepcopy(r);missing['payloads'][0]['source'].pop()
        with self.assertRaises(ValueError):placement(cst,missing)
        print('F808 164 exact data FF placements; duplicate and incomplete inventory rejected')

    def test_B7_native_locality_and_remaining_first_capture(self):
        n=self.n;g=Graph(n);cst=(self.stage/'constraints/custom_138k.cst').read_bytes()
        selected,e=w_native_placement(cst,n)
        self.assertEqual(e['primitive_count'],9130)
        self.assertEqual(len(e['placement_groups']),5)
        self.assertEqual(sum(x['primitive_count']for x in e['placement_groups']),9130)
        self.assertEqual(selected.count(b'GRP_LOC task3_w_native_'),5)
        statements=[line for line in selected.splitlines()if line.startswith(b'GROUP task3_w_native_')]
        self.assertEqual(len(statements),5)
        self.assertTrue(all(line.endswith(b' };')for line in statements))
        self.assertEqual(sum(line.count(b'"')//2 for line in statements),9130)
        self.assertTrue(e['exact_region_mapping_preserved'])
        for p,c in n.cells.items():
            if c['kind']=='INV':self.assertNotIn(('"'+p+'"').encode(),selected)
        self.assertEqual(e['held_register_count'],280)
        self.assertTrue(e['payload_hold_checks_retained'])
        with self.assertRaises(ValueError):w_native_placement(selected,n)
        path=g.register('u_task3_media/raw_store','command_kind',1)
        old=copy.deepcopy(n.cells[path]);n.cells[path]['ports']['CLK']='GND'
        try:
            with self.assertRaises(ValueError):w_native_placement(cst,n)
        finally:n.cells[path]=old
        proof,sdc=boundary_audit(n,role='W',stage=self.stage)
        raw=proof['W_routed_first_captures']
        self.assertEqual(len(raw['raw_store_release']['registers']),2)
        self.assertEqual(len(raw['raw_store_memory_up']['registers']),2)
        self.assertIn('memory_up_meta_s0/D',sdc)
        for stem,pin in [('control_release_0','CE'),('memory_up_sync','D')]:
            path=g.register('u_task3_media/raw_store',stem);old=copy.deepcopy(n.cells[path])
            n.cells[path]['ports'][pin]='GND'
            try:
                with self.assertRaises(ValueError):boundary_audit(n,role='W',stage=self.stage)
            finally:n.cells[path]=old
        print('B7 9130 placeable native primitives, 280 separated held FFs; clock, duplicate, release and observer corruptions rejected')


class MClockPriority(unittest.TestCase):
    def test_A9_PANIC_and_PCM_payload_hold_placement(self):
        selected=os.environ.get('GW138K_PREBOARD_M_STAGE')
        if not selected:self.skipTest('explicit actual M synthesis stage required')
        stage=Path(selected)
        n=protocol_netlist((stage/'impl/gwsynthesis/custom_138k_integration.vg').read_text(),mapping='synthesis')
        r,sdc=audit(n,role='M');cst=(stage/'constraints/custom_138k.cst').read_bytes()
        selected,e=placement(cst,r)
        self.assertEqual(len(e['registers']),348)
        self.assertEqual({x['id']for x in r['payloads']},
            {'F808_request','F808_response','PANIC_epoch','M_PCM_response','M_PCM_request'})
        self.assertEqual(sdc.count('set_min_delay 1.800'),5)
        self.assertNotIn('set_false_path -hold',sdc)
        with self.assertRaises(ValueError):placement(selected,r)
        bad=copy.deepcopy(r);bad['payloads'][-1]['capture'].pop()
        with self.assertRaises(ValueError):placement(cst,bad)

    def test_actual_A8_clock_inputs_and_reset_owners(self):
        from tools.workstation_custom_board_implementation import m_preboard_clock_priority
        selected=os.environ.get('GW138K_PREBOARD_M_STAGE')
        if not selected:self.skipTest('explicit actual M synthesis stage required')
        stage=Path(selected);vg=(stage/'impl/gwsynthesis/custom_138k_integration.vg').read_text()
        cst=(stage/'constraints/custom_138k.cst').read_bytes();result,e=m_preboard_clock_priority(cst,vg)
        self.assertTrue(result.startswith(cst));self.assertEqual(len(e['clock_inputs']),3)
        self.assertEqual(len(e['reset_distribution_nets']),3)
        with self.assertRaises(ValueError):m_preboard_clock_priority(result,vg)
        for port in ('usb2_ulpi_clk','clk_12m288','clk_16m9344'):
            changed,count=re.subn(r'(IBUF\s+(?:\\)?'+re.escape(port+'_ibuf')+r'\s*\(.*?\.I\()'+re.escape(port)+r'(\))',
                r'\g<1>GND\g<2>',vg,count=1,flags=re.S)
            self.assertEqual(count,1)
            with self.assertRaises(ValueError):m_preboard_clock_priority(cst,changed)
        print('M three actual clocks retain inputs and reserve LW8..10; duplicate and three disconnected input mutations rejected')


class WPhysicalComposition(unittest.TestCase):
    def test_actual_headless_DDR_startup_and_retained_mailboxes(self):
        selected=os.environ.get('GW138K_PREBOARD_W_PHYSICAL')
        if not selected:self.skipTest('explicit W routed VO/SDF required')
        sys.path.insert(0,str(ROOT/'tools'))
        from workstation_physical_pll_audit import pll_inventory,routed_worker_retained
        from workstation_serializer_startup_audit import inspect_serializer_startup
        p=Path(selected);base=p/'impl/pnr/custom_138k_integration'
        vo=base.with_suffix('.vo').read_text();sdf=base.with_suffix('.sdf').read_text();sdc=(p/'physical.sdc').read_text()
        n=protocol_netlist(vo,mapping='routed');cells={p:(c['kind'],c['ports'])for p,c in n.cells.items()}
        plls=pll_inventory(cells,local_panel_enabled=False,worker_headless=True)
        self.assertEqual(len(plls),4)
        for name in plls:
            bad=dict(cells);bad.pop(name)
            with self.assertRaises(ValueError):pll_inventory(bad,local_panel_enabled=False,worker_headless=True)
        bad=dict(cells);bad['u_video/retired']=('OSER10',{})
        with self.assertRaises(ValueError):pll_inventory(bad,local_panel_enabled=False,worker_headless=True)
        metadata=json.loads((p/'parent_integration_inputs.json').read_text())
        audit=json.loads((p/'parent_synthesis_audit.json').read_text())
        held=routed_worker_retained(vo,metadata,audit);self.assertTrue(held['gate_applied'])
        errors,r=inspect_serializer_startup(sdf,vo,{'source_bound_by_parent':True},sdc,
            startup_grant_role='W',worker_headless=True)
        self.assertEqual(errors,[]);self.assertTrue(r['headless_W_video_absence_verified'])
        for name,pin in [('u_memory/u_ddr3/gw3_top/u_ddr_phy_top/ddr_rsti_reg_2_s0','CE'),
                         ('u_managed/runtime/startup_memory_1_s0','D')]:
            changed,count=re.subn(r'(DFFCE\s+\\'+re.escape(name)+r'\s*\(.*?\.'+pin+r'\()([^)]*)',
                r'\g<1>GND',vo,count=1,flags=re.S)
            self.assertEqual(count,1)
            errors,unused=inspect_serializer_startup(sdf,changed,{'source_bound_by_parent':True},sdc,
                startup_grant_role='W',worker_headless=True)
            self.assertTrue(errors)
        print('W four exact PLLs, retained routed mailboxes, DDR stop/reset and grant chains; missing PLL, video resurrection, DDR CE and stage bypass rejected')


if __name__=='__main__':unittest.main()
