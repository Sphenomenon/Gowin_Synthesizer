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
        from tools.workstation_ble_completion_publication import configured
        publication=configured(json.loads((self.stage.parents[1]/'workstation_profile.json').read_text())['configuration'])
        from tools.workstation_ble_terminal_cofactor import configured as terminal_configured
        terminal=terminal_configured(json.loads((self.stage.parents[1]/'workstation_profile.json').read_text())['configuration'])
        from tools.workstation_ble_terminal_tuple import configured as tuple_configured
        tuple_cofactor=tuple_configured(json.loads((self.stage.parents[1]/'workstation_profile.json').read_text())['configuration'])
        from tools.workstation_ble_pack_cofactor import configured as pack_configured
        pack_cofactor=pack_configured(json.loads((self.stage.parents[1]/'workstation_profile.json').read_text())['configuration'])
        from tools.workstation_native_fault_cofactor import configured as native_configured
        native_fault=native_configured(json.loads((self.stage.parents[1]/'workstation_profile.json').read_text())['configuration'])
        place=lambda cst,n:w_native_placement(cst,n,publication=publication,terminal=terminal,tuple_cofactor=tuple_cofactor,pack_cofactor=pack_cofactor,native_fault_cofactor=native_fault)
        selected,e=place(cst,n);total=741 if native_fault else 740 if pack_cofactor else 739 if publication else 741
        self.assertEqual(e['primitive_count'],total)
        self.assertEqual(e['historical_broad_primitive_review_count'],9347 if native_fault else 9331 if pack_cofactor else 9298 if tuple_cofactor else 9175 if terminal else 9144 if publication else 9130)
        self.assertEqual(len(e['tag_return_cone']['source']),128)
        self.assertEqual(len(e['tag_return_cone']['capture']),257)
        self.assertEqual(len(e['tag_return_cone']['combinational_cells']),75 if pack_cofactor else 74 if publication else 76)
        self.assertEqual(e['pack_cofactor_layout'],pack_cofactor)
        if native_fault:
            shared='u_managed/runtime/delay_dma/n420_s2'
            self.assertEqual(e['causal_cells_excluded_from_placement_only'],[shared])
            self.assertIn(shared,e['tag_return_cone']['combinational_cells'])
            self.assertNotIn(('"'+shared+'"').encode(),selected)
            self.assertEqual(len(e['observed_status_hold_separation']),2)
            old=copy.deepcopy(n.cells[shared]);n.cells[shared]['parameters']['INIT']="16'h0000"
            try:
                with self.assertRaises(ValueError):place(cst,n)
            finally:n.cells[shared]=old
        if pack_cofactor:
            with self.assertRaises(ValueError):
                w_native_placement(cst,n,publication=publication,terminal=terminal,tuple_cofactor=tuple_cofactor)
            with self.assertRaises(ValueError):
                w_native_placement(cst,n,pack_cofactor=True)
        self.assertEqual(len(e['placement_groups']),5)
        self.assertEqual(sum(x['primitive_count']for x in e['placement_groups']),total)
        self.assertEqual(selected.count(b'GRP_LOC task3_w_native_'),5)
        statements=[line for line in selected.splitlines()if line.startswith(b'GROUP task3_w_native_')]
        self.assertEqual(len(statements),5)
        self.assertTrue(all(line.endswith(b' };')for line in statements))
        self.assertEqual(sum(line.count(b'"')//2 for line in statements),total)
        self.assertTrue(e['broad_region_constraints_removed'])
        for p,c in n.cells.items():
            if c['kind']=='INV':self.assertNotIn(('"'+p+'"').encode(),selected)
        self.assertEqual(e['held_register_count'],280)
        self.assertTrue(e['payload_hold_checks_retained'])
        path=e['tag_return_cone']['source'][0];old=copy.deepcopy(n.cells[path])
        n.cells[path]['ports']['CLK']='clk_50m'
        try:
            with self.assertRaises(ValueError):place(cst,n)
        finally:n.cells[path]=old
        with self.assertRaises(ValueError):place(selected,n)
        path=g.register('u_task3_media/raw_store','command_kind',1)
        old=copy.deepcopy(n.cells[path]);n.cells[path]['ports']['CLK']='GND'
        try:
            with self.assertRaises(ValueError):place(cst,n)
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
        print(f'B7 {total} exact causal/held primitives from {e["historical_broad_primitive_review_count"]} reviewed; clock, duplicate, release and observer corruptions rejected')

    def test_status_to_fetch_fault_hold_limit(self):
        from tools.workstation_task3_w_raw_command_capture import audit as raw_audit
        from tools.workstation_ble_completion_publication import configured
        configuration=json.loads((self.stage.parents[1]/'workstation_profile.json').read_text())['configuration']
        proof,sdc=raw_audit(self.n,publication=configured(configuration))
        hold=proof['status_fetch_fault_hold']
        self.assertTrue(hold['normal_setup_retained'] and hold['hold_check_retained'])
        self.assertFalse(hold['timing_exception_added'])
        self.assertIn('set_min_delay 1.800 -from [get_pins {'+hold['source']+'}] -to [get_pins {'+hold['capture']+'}]',sdc)
        self.assertNotIn('set_false_path',sdc)
        cell=hold['source'].removesuffix('/Q');old=copy.deepcopy(self.n.cells[cell])
        try:
            self.n.cells[cell]['ports']['CLK']='clk_50m'
            with self.assertRaises(ValueError):raw_audit(self.n,publication=configured(configuration))
        finally:self.n.cells[cell]=old
        cell=hold['capture'].removesuffix('/D');old=copy.deepcopy(self.n.cells[cell])
        try:
            self.n.cells[cell]['ports']['D']="1'b0"
            with self.assertRaises(ValueError):raw_audit(self.n,publication=configured(configuration))
        finally:self.n.cells[cell]=old


class MClockPriority(unittest.TestCase):
    def test_A9_PANIC_and_PCM_payload_hold_placement(self):
        selected=os.environ.get('GW138K_PREBOARD_M_STAGE')
        if not selected:self.skipTest('explicit actual M synthesis stage required')
        stage=Path(selected)
        n=protocol_netlist((stage/'impl/gwsynthesis/custom_138k_integration.vg').read_text(),mapping='synthesis')
        r,sdc=audit(n,role='M');cst=(stage/'constraints/custom_138k.cst').read_bytes()
        selected,e=placement(cst,r)
        self.assertEqual(len(e['registers']),348)
        from collections import Counter
        self.assertEqual(max(Counter(x['region']for x in e['registers']).values()),92)
        self.assertEqual({x['region'] for x in e['registers'] if x['mailbox']=='PANIC_epoch' and x['side']=='source'},
                         {'R[15:25]C[140:155]'})
        def region(mailbox,side):
            return {x['region']for x in e['registers']if x['mailbox']==mailbox and x['side']==side}
        self.assertEqual(region('M_PCM_request','source'),region('M_PCM_response','capture'))
        self.assertEqual(region('M_PCM_request','capture'),region('M_PCM_response','source'))
        self.assertTrue(region('M_PCM_request','source').isdisjoint(region('F808_request','source')))
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
        from tools.workstation_delay_watchdog_retime import configured
        retimed=configured(json.loads((stage.parents[1]/'workstation_profile.json').read_text())['configuration'])
        def check(cst,vg):return m_preboard_clock_priority(cst,vg,watchdog_retime=retimed)
        cst=(stage/'constraints/custom_138k.cst').read_bytes();result,e=check(cst,vg)
        self.assertTrue(result.startswith(cst));self.assertEqual(len(e['clock_inputs']),3)
        self.assertEqual(len(e['reset_distribution_nets']),3)
        reset=e['memory_reset']
        self.assertEqual(len(reset['reset_loads']),897+int(retimed))
        self.assertIn(('CLOCK_LOC "'+reset['net']+'" BUFG[11] = SR;').encode(),result)
        self.assertNotIn(b'memory_release[2]" BUFG[11] = CLK;',result)
        self.assertNotIn(b'CLOCK_LOC "u_managed/runtime/memory_release[2]" LOCAL_CLOCK;',result)
        self.assertEqual(result.count(b'LOCAL_CLOCK;')-cst.count(b'LOCAL_CLOCK;'),2)
        with self.assertRaises(ValueError):check(result,vg)
        for port in ('usb2_ulpi_clk','clk_12m288','clk_16m9344'):
            changed,count=re.subn(r'(IBUF\s+(?:\\)?'+re.escape(port+'_ibuf')+r'\s*\(.*?\.I\()'+re.escape(port)+r'(\))',
                r'\g<1>GND\g<2>',vg,count=1,flags=re.S)
            self.assertEqual(count,1)
            with self.assertRaises(ValueError):check(cst,changed)
        from tools.workstation_synthesis_netlist import SynthesisNetlist
        from unittest.mock import patch
        n=SynthesisNetlist(vg,'workstation_custom_138k_top')
        for path,pin in [(reset['inverter'],'I'),reset['reset_loads'][0]]+([('u_managed/runtime/delay_dma/watchdog_reset_delay_s0','PRESET')]if retimed else []):
            old=copy.deepcopy(n.cells[path]);n.cells[path]['ports'][pin]='GND'
            try:
                with patch('tools.workstation_custom_board_implementation.SynthesisNetlist',return_value=n):
                    with self.assertRaises(ValueError):check(cst,vg)
            finally:n.cells[path]=old
        if retimed:
            with self.assertRaises(ValueError):m_preboard_clock_priority(cst,vg,watchdog_retime=False)
        print('M three actual clocks retain inputs and reserve LW8..10; duplicate and three disconnected input mutations rejected')


    def test_actual_A11_PLL_control_limits_and_mutations(self):
        from tools.workstation_custom_board_implementation import m_preboard_pll_control_limits
        selected=os.environ.get('GW138K_PREBOARD_M_STAGE')
        if not selected:self.skipTest('explicit actual M synthesis stage required')
        stage=Path(selected);vg=(stage/'impl/gwsynthesis/custom_138k_integration.vg').read_text()
        sdc=(stage/'constraints/custom_138k.sdc').read_bytes()
        result,e=m_preboard_pll_control_limits(sdc,vg)
        self.assertTrue(result.startswith(sdc));self.assertEqual(len(e['paths']),15)
        self.assertEqual(e['full_routed_propagation_budget_ns'],10)
        self.assertEqual(result.count(b'set_max_delay 4.500')-sdc.count(b'set_max_delay 4.500'),15)
        self.assertEqual({row['maximum_ns'] for row in e['paths']},{4.5})
        with self.assertRaises(ValueError):m_preboard_pll_control_limits(result,vg)
        n=protocol_netlist(vg,mapping='synthesis')
        from unittest.mock import patch
        for row in (e['paths'][0],e['paths'][-1]):
            path=row['source'].rsplit('/',1)[0];old=copy.deepcopy(n.cells[path])
            n.cells[path]['ports']['CLK']='GND'
            try:
                with patch('tools.workstation_native_protocol_audit.protocol_netlist',return_value=n):
                    with self.assertRaises(ValueError):m_preboard_pll_control_limits(sdc,vg)
            finally:n.cells[path]=old
        print('M fifteen exact PLL control routes tightened to4.5ns; duplicate and publisher clock mutations rejected; full10ns routed gate retained')


class MPhysicalComposition(unittest.TestCase):
    def test_actual_DIRECT_startup_and_corruptions(self):
        selected=os.environ.get('GW138K_PREBOARD_M_PHYSICAL')
        if not selected:self.skipTest('explicit M routed VO/SDF required')
        from tools.workstation_serializer_startup_audit import inspect_serializer_startup
        p=Path(selected);base=p/'impl/pnr/custom_138k_integration'
        vo=base.with_suffix('.vo').read_text();sdf=base.with_suffix('.sdf').read_text();sdc=(p/'physical.sdc').read_text()
        parent=json.loads((p/'parent_synthesis_audit.json').read_text())
        root=parent['gates']['M_paired_release_CDC']['evidence']['actual_root_startup']
        def check(text,sdf_text=sdf):
            return inspect_serializer_startup(sdf_text,text,{'source_bound_by_parent':True},sdc,
                startup_grant_role='M',paired_direct_root=root)
        errors,e=check(vo);self.assertEqual(errors,[])
        self.assertEqual(e['paired_DIRECT_TF_startup']['register_count'],10)
        self.assertEqual(len(e['paired_DIRECT_TF_startup']['routed_early_stage_paths']),12)
        for path,pin in [('u_managed/runtime/startup_memory_0_s0','CLEAR'),
                         ('u_tf_audio/startup_compute_1_s0','D'),
                         ('u_runtime/g_usb_cdc_reset.usb_ready_0_s0','D'),
                         ('output_safe_sync_1_s0','CE')]:
            changed,count=re.subn(r'(DFFCE\s+(?:\\)?'+re.escape(path)+r'\s*\(.*?\.'+pin+r'\()([^)]*)',
                r'\g<1>GND',vo,count=1,flags=re.S)
            self.assertEqual(count,1,path);self.assertNotEqual(changed,vo)
            self.assertTrue(check(changed)[0],path)
        errors,unused=inspect_serializer_startup(sdf,vo,{'source_bound_by_parent':True},sdc,startup_grant_role='M')
        self.assertTrue(errors,'DIRECT mode must never be inferred from convenient primitive names')
        print('M exact ten DIRECT TF FFs and twelve early paths, local startup and readiness covered; four corruptions and implicit mode rejected')


    def test_actual_M_retained_mailboxes_and_corruptions(self):
        selected=os.environ.get('GW138K_PREBOARD_M_PHYSICAL')
        if not selected:self.skipTest('explicit M routed VO/SDF required')
        sys.path.insert(0,str(ROOT/'tools'))
        from tools.workstation_physical_pll_audit import routed_m_retained
        p=Path(selected);vo=(p/'impl/pnr/custom_138k_integration.vo').read_text()
        meta=json.loads((p/'parent_integration_inputs.json').read_text())
        audit=json.loads((p/'parent_synthesis_audit.json').read_text())
        stage=Path(json.loads((p/'physical_inputs.json').read_text())['parent_candidate'])/'workstation/Prj1'
        e=routed_m_retained(vo,meta,audit,stage)
        self.assertTrue(e['gate_applied']);self.assertTrue(e['full_peripheral_and_TF_FIFO_tail_routed_CDC_required'])
        for path in ('u_managed/pc_bytes/destination_data_0_s0','u_managed/pc_bytes/req_sync_s0'):
            changed,count=re.subn(r'(DFFCE\s+\\'+re.escape(path)+r'\s*\(.*?\.D\()([^)]*)',
                r'\g<1>GND',vo,count=1,flags=re.S)
            self.assertEqual(count,1,path)
            with self.assertRaises(ValueError):routed_m_retained(changed,meta,audit,stage)
        print('M retained routed payload/reset/first-stage equations pass; capture and receiving-stage bypass rejected; full physical CDC separate')


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
