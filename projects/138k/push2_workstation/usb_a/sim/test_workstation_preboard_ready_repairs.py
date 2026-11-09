"""Actual rebuilt netlists: TF capture isolation and W batch fault guards."""
from pathlib import Path
from copy import deepcopy
import hashlib,json,os,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_runtime_pcm_cdc import Graph,COMB
from tools.workstation_task3_w_consumer_nextq import logical


class ActualReadyRepairs(unittest.TestCase):
    def test_W_generation_successor_induction_and_mutations(self):
        selected=os.environ.get('GW138K_READY_REPAIR_W_STAGE')
        if not selected:self.skipTest('explicit complete W synthesis stage required')
        from tools import workstation_w_generation_successor as successor
        stage=Path(selected)
        configuration=json.loads((stage.parents[1]/'workstation_profile.json').read_text())['configuration']
        if not successor.configured(configuration):self.skipTest('successor policy not selected')
        path=stage/'impl/gwsynthesis/custom_138k_integration.vg';before=path.read_bytes()
        n=protocol_netlist(before.decode(),mapping='synthesis');g=Graph(n)
        proof=successor.audit(n)
        self.assertEqual(proof['invariant_induction']['solver_result'],'unsat')
        bit0=g.register('u_task3_media/raw_store','memory_generation_successor',0)
        bit7=g.register('u_task3_media/raw_store','memory_generation_successor',7)
        cases=[(bit7,'ports','D',"1'b0"),(bit7,'ports','CE',"1'b0"),
               (bit0,'ports','PRESET',"1'b0"),(bit0,'ports','CLK','audio_clk'),
               (bit0,'parameters','INIT',"1'b0")]
        for register,part,key,value in cases:
            old=deepcopy(n.cells[register]);n.cells[register][part][key]=value
            try:
                with self.subTest(pin=key),self.assertRaises(ValueError):successor.audit(n)
            finally:n.cells[register]=old
        self.assertEqual(path.read_bytes(),before)
        print('W actual reset-inclusive32-bit successor induction and five input/INIT mutations rejected')

    def test_W_registered_tx_placement_reconstruction(self):
        selected=os.environ.get('GW138K_READY_REPAIR_W_STAGE')
        if not selected:self.skipTest('explicit complete W synthesis stage required')
        from tools.workstation_task3_preboard_held_timing import w_native_placement
        from tools.workstation_task3_w_delay_locality import placement,reconstruct,arithmetic_layout
        stage=Path(selected);vg=stage/'impl/gwsynthesis/custom_138k_integration.vg'
        n=protocol_netlist(vg.read_text(),mapping='synthesis')
        from tools.workstation_fifo_full_compare import configured
        first=configured(json.loads((stage.parents[1]/'workstation_profile.json').read_text())['configuration'])
        metadata=json.loads((stage.parents[1]/'integration_inputs.json').read_text())
        arithmetic=arithmetic_layout(metadata)
        matches=bool(metadata.get('raw_generation_match'))
        cst=(stage/'constraints/custom_138k.cst').read_bytes()
        options=dict(publication=True,terminal=True,tuple_cofactor=True,
            pack_cofactor=True,native_fault_cofactor=True,identity_bytes=True,
            fetch_range=True,fetch_end_capture=True,registered_tx_class=True,fifo_compare_first=first,arithmetic_repair=arithmetic,generation_match=matches)
        bounded,receipt=w_native_placement(cst,n,**options)
        self.assertEqual(receipt['primitive_count'],787 if matches else 785)
        self.assertEqual(len(receipt['tag_return_cone']['combinational_cells']),75)
        result,proof=placement(bounded,n,registered_tx_class=True,fifo_compare_first=first,arithmetic_repair=arithmetic)
        self.assertEqual(proof['selected_count'],2211 if arithmetic else 2241 if first else 2240)
        self.assertEqual(reconstruct(bounded,n,proof,registered_tx_class=True,fifo_compare_first=first,arithmetic_repair=arithmetic),result)
        with self.assertRaises(ValueError):placement(bounded,n)
        with self.assertRaises(ValueError):reconstruct(bounded,n,proof)
        with self.assertRaises(ValueError):placement(result,n,registered_tx_class=True,fifo_compare_first=first,arithmetic_repair=arithmetic)
        with self.assertRaises(ValueError):arithmetic_layout({'w_watchdog_width':{'policy':'task3_W_bounded_saturating_wait_counter_v1'}})
        if arithmetic:
            with self.assertRaises(ValueError):w_native_placement(cst,n,**dict(options,arithmetic_repair=False))
        path='u_managed/runtime/delay_dma/'+('n387_s3' if arithmetic else 'n420_s3' if first else 'n420_s2');old=deepcopy(n.cells[path])
        try:
            n.cells[path]['parameters']['INIT']="16'hFFFF"
            with self.assertRaises(ValueError):w_native_placement(cst,n,**options)
        finally:n.cells[path]=old
        print('W exact',receipt['primitive_count'],'cell tag/held and',proof['selected_count'],'cell delay placement; old selection, duplicate and broken watchdog rejected')

    def test_M_capture_enable_has_no_final_router_state(self):
        selected=os.environ.get('GW138K_READY_REPAIR_M_STAGE')
        if not selected:self.skipTest('explicit complete M synthesis stage required')
        stage=Path(selected);vg=stage/'impl/gwsynthesis/custom_138k_integration.vg'
        before=hashlib.sha256(vg.read_bytes()).hexdigest()
        n=protocol_netlist(vg.read_text(),mapping='synthesis');g=Graph(n)
        regs=[p for p in g.regs if n.scopes[p]=='u_tf_audio/frames'and
              p.rsplit('/',1)[1].startswith('held_packet_')]
        self.assertEqual(len(regs),108)
        enables={n.pin(p,'CE')for p in regs};leaves=set();ram_outputs=set()
        for p,cell in n.cells.items():
            if p.startswith('u_tf_audio/frames/frames_0/')and cell['kind']=='RAM16SDP4':
                ram_outputs.update(n.canonical(n.scopes[p],bit)
                    for bit in g.binding_bits(n.scopes[p],cell['ports']['DO']))
        self.assertEqual(len(ram_outputs),108)
        pending=list(enables);seen=set()
        while pending:
            net=pending.pop()
            if net in seen or net in g.high|g.low|ram_outputs:continue
            seen.add(net);drivers=g.drivers[net];self.assertEqual(len(drivers),1,net)
            p,port=drivers[0]
            if p in g.regs:leaves.add(logical(p));continue
            cell=n.cells[p];self.assertIn(cell['kind'],COMB,p)
            pending.extend(n.pin(p,pin)for pin in cell['ports']if pin not in COMB[cell['kind']])
        self.assertTrue(leaves)
        self.assertFalse(any(p.startswith('u_managed/runtime/final_pcm/')for p in leaves),leaves)
        self.assertIn('u_tf_audio/frames/held_valid',leaves)
        print('TF actual payload CE:',len(regs),'registers;',len(leaves),'named state leaves; no final-router feedback')
        self.assertEqual(hashlib.sha256(vg.read_bytes()).hexdigest(),before)

    def test_W_full_active_and_flight_mutations(self):
        selected=os.environ.get('GW138K_READY_REPAIR_W_STAGE')
        if not selected:self.skipTest('explicit complete W synthesis stage required')
        from tools.workstation_task3_phone_batch_mapped_w import audit
        stage=Path(selected);vg=stage/'impl/gwsynthesis/custom_138k_integration.vg'
        before=hashlib.sha256(vg.read_bytes()).hexdigest()
        n=protocol_netlist(vg.read_text(),mapping='synthesis');g=Graph(n)
        result=audit(n,stage=stage);self.assertTrue(result)
        endpoint='u_task3_bus_endpoint';window=endpoint+'/g_phone_window.window_tx'
        from tools.workstation_fifo_full_compare import configured
        first=configured(json.loads((stage.parents[1]/'workstation_profile.json').read_text())['configuration'])
        from tools.workstation_w_generation_successor import configured as successor_configured
        config=json.loads((stage.parents[1]/'workstation_profile.json').read_text())['configuration']
        active=n.canonical(endpoint,'n10383_29' if successor_configured(config) else
                           'n10383_7' if first else 'n12043_16');active_cell=g.drivers[active][0][0]
        flight=g.register(window,'flight',0);flight_cell=g.drivers[n.pin(flight,'D')][0][0]
        active_zero=f"{1<<int(n.cells[active_cell]['kind'][3:])}'h0"
        cases=[(active_cell,'parameters','INIT',active_zero),
               (flight_cell,'parameters','INIT',"16'hFFFF"),
               (flight,'ports','CLEAR',"1'b0")]
        for path,part,key,value in cases:
            old=deepcopy(n.cells[path]);n.cells[path][part][key]=value
            try:
                with self.subTest(path=path),self.assertRaises(ValueError):audit(n,stage=stage)
            finally:n.cells[path]=old
        print('W complete actual batch/window proof and three broken guard/flight/reset controls rejected')
        self.assertEqual(hashlib.sha256(vg.read_bytes()).hexdigest(),before)


if __name__=='__main__':unittest.main()
