#!/usr/bin/env python3
"""Actual frame bridge partial CDC/RAM evidence and destructive controls.

Explicit candidate VG/SDC/stage only. No source/constraint/candidate mutation,
EDA, mocked netlist, physical tail proof, or board operation is performed.
"""
from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
import os
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_runtime_pcm_cdc import Graph
from tools.workstation_task3_tf_frame_cdc_audit import audit_tf_frame_cdc,B,F


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ActualTask3FrameCdc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        vg=os.environ.get('GW138K_TASK3_FRAME_VG')
        sdc=os.environ.get('GW138K_TASK3_FRAME_SDC')
        stage=os.environ.get('GW138K_TASK3_FRAME_STAGE')
        if not vg or not sdc or not stage:
            raise unittest.SkipTest('explicit actual VG/SDC/stage required; no fallback')
        cls.vg,cls.sdc_path,cls.stage=Path(vg),Path(sdc),Path(stage)
        cls.metadata_path=cls.stage.parents[1]/'integration_inputs.json'
        metadata=json.loads(cls.metadata_path.read_text())
        cls.constraint_revision=metadata['task3_tf_direct_cdc'].get('constraint_revision',1)
        if cls.constraint_revision not in (1,2,3):
            raise ValueError('unsupported explicit TF constraint revision')
        cls.mapping=os.environ.get('GW138K_TASK3_FRAME_MAPPING','synthesis')
        cls.n=protocol_netlist(cls.vg.read_text(),mapping=cls.mapping)
        cls.sdc=cls.sdc_path.read_text()
        cls.positive,cls.mutations,cls.failed=None,[],False
        cls.gap_detections=[]
        cls.before={str(p):sha(p) for p in (cls.vg,cls.sdc_path,cls.metadata_path,cls.stage/'Prj1.gprj',
            cls.stage/'rtl/tf_audio/workstation_tf_frame_bridge_v2.sv',
            cls.stage/'rtl/music/music_async_fifo.sv',
            ROOT/'tools/workstation_task3_root_reset_audit.py',
            ROOT/'tools/workstation_task3_peripheral_releases_audit.py',
            ROOT/'tools/workstation_task3_tf_startup_audit.py',
            ROOT/'tools/workstation_task3_receipt_audit.py',
            ROOT/'tools/workstation_task3_tf_frame_cdc_audit.py')}

    def tearDown(self):
        result=self._outcome.result
        self.__class__.failed |= bool(result.failures or result.errors)

    @classmethod
    def tearDownClass(cls):
        unchanged=cls.before=={p:sha(p) for p in cls.before}
        target=os.environ.get('GW138K_TASK3_FRAME_EVIDENCE')
        if target:
            Path(target).write_text(json.dumps(dict(
                status='PARTIAL_STRUCTURAL_PASS' if unchanged and cls.positive and not cls.failed else 'FAIL',
                mapping=cls.mapping,selected_stage=str(cls.stage),selected_vg=str(cls.vg),
                explicit_constraint_revision=cls.constraint_revision,
                selected_revision_metadata=str(cls.metadata_path),
                selected_sdc=str(cls.sdc_path),actual_input_sha256=cls.before,
                actual_frame_partial=cls.positive,mutations=cls.mutations,mutation_count=len(cls.mutations),
                optional_boundary_gap_detections=cls.gap_detections,
                optional_boundary_gap_detection_count=len(cls.gap_detections),
                original_inputs_unchanged=unchanged,
                audit_source_sha256={p:sha(ROOT/p) for p in (
                    'tools/workstation_task3_tf_frame_cdc_audit.py','sim/test_workstation_task3_tf_frame_cdc.py')},
                full_tf_cdc_accepted=False,physical_tail_proven=False,hardware_tested=False),indent=2)+'\n')
        assert unchanged,'actual candidate, SDC, source or frozen helper drifted'

    @contextmanager
    def changed(self,path,part,key,value):
        target=self.n.cells[path][part]
        absent=object();old=target.get(key,absent)
        target[key]=value
        try:yield
        finally:
            if old is absent:del target[key]
            else:target[key]=old

    def test_01_actual_structure_and_retained_ram_gaps(self):
        result=audit_tf_frame_cdc(self.n,sdc=self.sdc,stage=self.stage)
        self.assertEqual([b['width'] for b in result['gray_buses']],[32,32,5,5])
        self.assertEqual(sum(len(b['next_q']) for b in result['gray_buses']),148)
        self.assertEqual(len(result['single_bit_chains']),5)
        self.assertEqual(len(result['ram_instances']),27)
        self.assertEqual(len(result['ram_data_complete_closure']['ff_endpoints']),218)
        expected=[('fifo-async-RAM-data',27,218),('fifo-read-address-to-asynchronous-RAD',4,27)]
        inventory=lambda rows:[(g['id'],len(g['source_pins']),len(g['capture_pins'])) for g in rows]
        if self.constraint_revision==3:
            self.assertEqual(result['missing_finite_boundaries'],[])
            self.assertEqual(inventory([g for g in result['installed_frame_constraints']
                if g['id'] in {row[0] for row in expected}]),expected)
        else:
            self.assertEqual(inventory(result['missing_finite_boundaries']),expected)
        self.assertTrue(result['existing_gray_and_second_stage_sdc_exact'])
        self.assertTrue(result['source_only_and_through_exceptions_rejected'])
        self.assertFalse(result['constraints_complete'])
        self.assertFalse(result['complete_tf_cdc_accepted'])
        self.assertTrue(all(not b['producer_gray_encoding_and_one_step_transition_proven']
                            for b in result['gray_buses']))
        self.__class__.positive=result

    def test_02_actual_netlist_destructive_controls(self):
        actual=audit_tf_frame_cdc(self.n,sdc=self.sdc,stage=self.stage)
        n,g=self.n,Graph(self.n)
        cases=[]
        for bus in actual['gray_buses']:
            first=bus['first_pins'][0].rsplit('/',1)[0]
            second=bus['second_pins'][0].rsplit('/',1)[0]
            consumer=g.register(B,'held_valid') if bus['id'] in ('generation','ack') else g.register(F,'read_binary',0)
            cases.extend((
                (bus['id']+' first INIT',first,'parameters','INIT',"1'b1"),
                (bus['id']+' first CE',first,'ports','CE',"1'b0"),
                (bus['id']+' second clock',second,'ports','CLK',"1'b0"),
                (bus['id']+' second D bypass',second,'ports','D',"1'b1"),
                (bus['id']+' first extra consumer',consumer,'ports','D',n.cells[first]['ports']['Q']),
            ))
        ram=actual['ram_instances'][0]['instance']
        held=g.register(B,'held_packet',0)
        cases.extend((
            ('RAM write clock changed',ram,'ports','CLK','audio_clk'),
            ('RAM WRE forced on',ram,'ports','WRE',"1'b1"),
            ('RAM WAD disconnected',ram,'ports','WAD',"4'b0000"),
            ('RAM RAD disconnected',ram,'ports','RAD',"4'b0000"),
            ('RAM DO disconnected',ram,'ports','DO',"4'b0000"),
            ('held RAM data D disconnected',held,'ports','D',"1'b0"),
            ('held RAM control CE removed',held,'ports','CE',"1'b1"),
        ))
        for label,path,part,key,value in cases:
            with self.subTest(case=label),self.changed(path,part,key,value):
                with self.assertRaises(ValueError) as error:
                    audit_tf_frame_cdc(n,sdc=self.sdc,stage=self.stage)
            self.mutations.append(dict(case=label,rejected=True,error=str(error.exception)))
        self.assertEqual(len(cases),27)

    def test_03_actual_sdc_destructive_controls(self):
        actual=audit_tf_frame_cdc(self.n,sdc=self.sdc,stage=self.stage)
        g=Graph(self.n)
        records={r['id']:r for r in actual['installed_frame_constraints']}
        generation=records['generation-first']['constraint']
        ack=records['ack-first']['constraint']
        second=records['write-pointer-second']['constraint']
        boundaries={r['id']:r for r in [*actual['missing_finite_boundaries'],
                                      *actual['installed_frame_constraints']]}
        data=boundaries['fifo-async-RAM-data']
        address=boundaries['fifo-read-address-to-asynchronous-RAD']
        def query(pins):return '[get_pins {'+' '.join(pins)+'}]'
        data_path='-from '+query(data['source_pins'])+' -to '+query(data['capture_pins'])
        only_d=[pin for pin in data['capture_pins'] if pin.endswith('/D')]
        def ram_data_bound(line):
            if self.constraint_revision==3:
                self.assertEqual(self.sdc.count(data['constraint']),1)
                return self.sdc.replace(data['constraint'],line,1)
            return self.sdc+'\n'+line+'\n'
        alive='u_usb_pll/u_pll_init/enable_r_0_s[0-9]*/Q'
        self.assertIn(alive,self.sdc)
        cases=[
            ('generation finite removed',self.sdc.replace(generation+'\n','',1)),
            ('ACK launch bound weakened',self.sdc.replace(ack,ack.replace('13.020','50.000',1),1)),
            ('write pointer second bound removed',self.sdc.replace(second+'\n','',1)),
            ('alive source glob includes other PLL registers',self.sdc.replace(alive,'u_usb_pll/u_pll_init/enable_r_*_s*/Q',1)),
            ('RAM held CE setup cut',self.sdc+'\nset_false_path -to '+query([g.register(B,'held_packet',0)+'/CE'])+'\n'),
            ('RAM RAD setup cut',self.sdc+'\nset_false_path -to '+query(address['capture_pins'])+'\n'),
            ('RAM data weak optional bound',ram_data_bound('set_max_delay 20.000 '+data_path)),
            ('RAM data partial D-only bound',ram_data_bound('set_max_delay 13.020 -from '+query(data['source_pins'])+' -to '+query(only_d))),
            ('source-only generation setup cut',self.sdc+'\nset_false_path -from '+query(actual['gray_buses'][0]['source_pins'])+'\n'),
            ('source-only RAM DO setup cut',self.sdc+'\nset_false_path -from '+query(data['source_pins'])+'\n'),
            ('source-only read address get_regs setup cut',self.sdc+'\nset_false_path -from [get_regs {'+
                ' '.join(p.rsplit('/',1)[0] for p in address['source_pins'])+'}]\n'),
            ('RAM data through setup cut',self.sdc+'\nset_false_path -through '+query(data['source_pins'])+'\n'),
            ('generation through setup cut',self.sdc+'\nset_false_path -through '+query(actual['gray_buses'][0]['source_pins'])+'\n'),
            ('source-only RAM weak max bound',self.sdc+'\nset_max_delay 50.000 -from '+query(data['source_pins'])+'\n'),
            ('source-only meta Q setup cut',self.sdc+'\nset_false_path -from '+query(actual['gray_buses'][0]['meta_q_pins'])+'\n'),
            ('whitespace source-only RAM setup cut',self.sdc+'\n  set_false_path -from '+query(data['source_pins'])+'\n'),
        ]
        for label,modified in cases:
            with self.subTest(case=label),self.assertRaises(ValueError) as error:
                audit_tf_frame_cdc(self.n,sdc=modified,stage=self.stage)
            self.mutations.append(dict(case=label,rejected=True,error=str(error.exception)))
        self.assertEqual(len(cases),16)
        if self.constraint_revision==3:
            # The partial helper reports absent optional bounds as gaps. These
            # probes detect missing coverage; they are not fail-closed rejections.
            for removed in ((data,),(address,),(data,address)):
                modified=self.sdc
                for row in removed:
                    self.assertEqual(modified.count(row['constraint']),1)
                    modified=modified.replace(row['constraint']+'\n','',1)
                result=audit_tf_frame_cdc(self.n,sdc=modified,stage=self.stage)
                expected=[row['id'] for row in removed]
                self.assertEqual([row['id'] for row in result['missing_finite_boundaries']],expected)
                self.assertFalse(result['constraints_complete'])
                self.assertFalse(result['complete_tf_cdc_accepted'])
                self.gap_detections.append(dict(removed_optional_boundaries=expected,
                    missing_boundaries_detected=expected,global_fail_closed_rejection=False,
                    complete_tf_cdc_accepted=False))


if __name__=='__main__':
    unittest.main()
