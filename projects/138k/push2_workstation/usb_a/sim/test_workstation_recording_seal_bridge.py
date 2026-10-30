#!/usr/bin/env python3
"""Local reset release, registered ready and real seal-terminal regression.

No EDA, physical CDC, board operation or historical product modification.
Set GW138K_RECORDING_SEAL_TEST_EVIDENCE to preserve hashed offline results.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'rtl/services/workstation_recording_seal_bridge.sv'
FIXTURE=ROOT/'sim/services/tb_workstation_recording_seal_bridge.sv'
CASES=(
 'common_reset_phase_sweep', 'same_edge_hold_request_and_real_done',
 'failure_retention_and_rearm', 'simultaneous_done_failed_priority',
 'destination_ready_race_reports_11', 'ready_pulse_must_be_memory_registered',
 'common_reset_while_memory_clock_stopped', 'common_reset_while_source_clock_stopped',
 'exact_edge_reset_release_held_request', 'delivery_edge_stale_terminal_ignored',
 'pending_request_ignored_without_result_loss',
)

def sha(data):return hashlib.sha256(data).hexdigest()

class RecordingSealBridge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original={str(p.relative_to(ROOT)):p.read_bytes() for p in (RTL,FIXTURE,Path(__file__))}
        cls.results=[]

    @classmethod
    def tearDownClass(cls):
        unchanged=all((ROOT/p).read_bytes()==b for p,b in cls.original.items())
        if not unchanged:raise AssertionError('recording seal test inputs changed during run')
        target=os.environ.get('GW138K_RECORDING_SEAL_TEST_EVIDENCE')
        if target:
            result=dict(schema=1,source_sha256={p:sha(b) for p,b in cls.original.items()},
                source_seal_before_and_after=unchanged,cases=sorted(cls.results,key=lambda x:x['label']),
                positive_count=sum(not x['mutant'] for x in cls.results),
                rejected_negative_count=sum(x['mutant'] and x['passed'] for x in cls.results),
                passed=all(x['passed'] for x in cls.results),eda_invoked=False,
                physical_cdc_accepted=False,reset_physical_accepted=False,hardware_operated=False,
                sram_programmed=False,flash_written=False,deployment_allowed=False)
            Path(target).write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')

    def simulate(self,label,case,source,expected=None):
        with tempfile.TemporaryDirectory(prefix='recording-seal-bridge-') as directory:
            rtl=Path(directory)/'bridge.sv';rtl.write_text(source)
            executable=Path(directory)/'test.vvp'
            command=['iverilog','-g2012','-Wall','-s','tb_workstation_recording_seal_bridge',
                '-Ptb_workstation_recording_seal_bridge.CASE='+str(case),'-o',str(executable),str(FIXTURE),str(rtl)]
            compiled=subprocess.run(command,capture_output=True,text=True,timeout=30)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            ran=subprocess.run(['vvp',str(executable)],capture_output=True,text=True,timeout=30)
            log=ran.stdout+ran.stderr
            passed=(ran.returncode!=0 and expected in log) if expected else (ran.returncode==0 and 'PASS seal bridge' in log)
            row=dict(label=label,case=case,description=CASES[case],mutant=expected is not None,
                expected_failure=expected,passed=passed,compile_returncode=compiled.returncode,
                run_returncode=ran.returncode,source_sha256=sha(source.encode()),log=log,
                compile_log=compiled.stdout+compiled.stderr)
            print(('PASS ' if passed else 'FAIL ')+label,flush=True)
            return row

    def execute(self,jobs):
        with ThreadPoolExecutor(max_workers=3) as pool:
            rows=list(pool.map(lambda job:self.simulate(*job),jobs))
        self.results.extend(rows)
        for row in rows:
            with self.subTest(case=row['label']):self.assertTrue(row['passed'],row['log'])

    def test_reset_handshake_ready_and_terminal_cases(self):
        source=RTL.read_text()
        self.execute([(name,i,source,None) for i,name in enumerate(CASES)])

    def test_reset_ready_hold_result_and_bundle_negatives(self):
        source=RTL.read_text()
        changes=(
         ('source_raw_release',0,'wire source_reset_n=source_release_sync;','wire source_reset_n=reset_ni;',
          'source functional FF escaped local release'),
         ('destination_raw_release',0,'wire destination_reset_n=destination_release_sync;','wire destination_reset_n=reset_ni;',
          'destination functional FF escaped local release'),
         ('source_one_stage_release',0,'wire source_reset_n=source_release_sync;','wire source_reset_n=source_release_meta;',
          'source functional FF escaped local release'),
         ('destination_one_stage_release',0,'wire destination_reset_n=destination_release_sync;','wire destination_reset_n=destination_release_meta;',
          'destination functional FF escaped local release'),
         ('ready_raw_combinational_crossing',5,'ready_meta<=destination_ready;',
          'ready_meta<=destination_ready_i && !destination_pending && !hold_sync;',
          'unregistered destination ready pulse crossed domains'),
         ('hold_caller_can_abandon',1,'source_hold<=hold_i || source_pending;','source_hold<=hold_i;',
          'accepted seal lost backend hold before real terminal'),
         ('same_edge_hold_drops_request',1,'request_i && !source_pending && ready_sync','request_i && ready_o',
          'same-edge hold request was not accepted'),
         ('fabricated_early_result',1,'source_pending && result_sync!=result_seen','source_pending',
          'pending seal completed before backend terminal'),
         ('failed_terminal_lost',3,'result_failed<=destination_failed_i;','result_failed<=0;',
          'seal terminal/failure mismatch'),
         ('failure_detail_not_retained',2,'ready_sync<=ready_meta;done_o<=0;failed_o<=0;',
          'ready_sync<=ready_meta;done_o<=0;failed_o<=0;failure_code_o<=0;',
          'seal failure was not retained under hold'),
         ('raw_failure_bundle',2,'failure_code_o<=result_code;','failure_code_o<=destination_failure_code_i;',
          'seal terminal/failure mismatch'),
         ('stale_delivery_terminal_consumed',9,'destination_pending && !destination_request_o &&',
          'destination_pending &&','stale delivery-edge terminal completed new seal'),
        )
        jobs=[]
        for name,case,old,new,expected in changes:
            self.assertEqual(source.count(old),1,'negative anchor drift: '+name)
            jobs.append((name,case,source.replace(old,new),expected))
        self.execute(jobs)

if __name__=='__main__':unittest.main()
