#!/usr/bin/env python3
"""Old/new complete DMA outputs and deadline-edge tests for the W B13 failure."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,tempfile,unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools import workstation_delay_watchdog_retime as repair
TB=ROOT/'sim/audio/tb_workstation_delay_watchdog_retime.sv'

class DelayWatchdogRetiming(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected=os.environ.get('GW138K_DELAY_WATCHDOG_OUTPUT')
        cls.temp=None if selected else tempfile.TemporaryDirectory(prefix='delay-watchdog-')
        cls.out=Path(selected or cls.temp.name)
        if selected:cls.out.mkdir(parents=True,exist_ok=False)
        cls.source=(ROOT/repair.SOURCE).read_text()
        cls.original=repair.restore(cls.source)
        cls.snapshot={str(p.relative_to(ROOT)):repair.digest(p.read_bytes())for p in (
            ROOT/repair.SOURCE,ROOT/repair.MANIFEST,ROOT/repair.TOOL,TB,Path(__file__))}
        (cls.out/'original.sv').write_text(cls.original.replace(
            'module workstation_runtime_delay_ddr_dma #(', 'module delay_original #(',1))
        cls.runs=[]

    @classmethod
    def tearDownClass(cls):
        (cls.out/'verification.json').write_text(json.dumps(dict(
            scope='429 DMA output bits, counter relation, forced state and X/Z input diagnostics',
            source_sha256=cls.snapshot,runs=cls.runs,
            source_inputs_unchanged=cls.snapshot=={p:repair.digest((ROOT/p).read_bytes())for p in cls.snapshot},
            all_run_expectations_met=all((r['exit_code']==0)==r['expected_pass']for r in cls.runs),
            hardware_tested=False),indent=2)+'\n')
        if cls.temp:cls.temp.cleanup()

    def execute(self,label,source,timeout,expected_pass=True):
        p=self.out/(label+'.sv');p.write_text(source)
        binary=self.out/label
        cmd=['iverilog','-g2012','-s','tb',f'-Ptb.T={timeout}','-o',str(binary),
             str(self.out/'original.sv'),str(p),str(TB)]
        result=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        result=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=30)
        log=result.stdout+result.stderr
        (self.out/(label+'.log')).write_text(log)
        self.runs.append(dict(label=label,timeout=timeout,exit_code=result.returncode,expected_pass=expected_pass,
                              source_sha256=repair.digest(source),log_sha256=repair.digest(log)))
        if expected_pass:self.assertEqual(result.returncode,0,log)
        else:
            self.assertNotEqual(result.returncode,0,log)
            self.assertIn('mismatch',log)

    def test_identity_selection_and_rejections(self):
        info=json.loads((ROOT/repair.MANIFEST).read_text())
        self.assertEqual(repair.digest(self.original),info['parent_sha256'])
        self.assertEqual(repair.restore(self.source.replace(repair.DEFAULT,repair.SELECTED)),self.original)
        self.assertFalse(repair.configured({}))
        for role in ('M','W'):
            config={repair.KEY:repair.POLICY,'demo_role':role,
                    'effects_dispatch_policy':f'task3_{role}_reserved_effects_configuration_v1'}
            self.assertTrue(repair.configured(config))
        for config in ({repair.KEY:'unknown'},{repair.KEY:repair.POLICY},
                       {repair.KEY:repair.POLICY,'demo_role':'M'}):
            with self.assertRaises(ValueError):repair.configured(config)
        for changed in (self.source.replace('watchdog_reset_delay<=1','watchdog_reset_delay<=0',1),
                        self.source.replace(repair.DEFAULT,repair.DEFAULT+'; '+repair.SELECTED,1)):
            with self.assertRaises(ValueError):repair.restore(changed)

    def test_selected_full_outputs_and_counter_relation(self):
        selected=self.source.replace(repair.DEFAULT,repair.SELECTED,1)
        for timeout in (2,3,4,7,16,1048576):
            with self.subTest(timeout=timeout):self.execute('selected-'+str(timeout),selected,timeout)
        self.assertEqual(self.snapshot,{p:repair.digest((ROOT/p).read_bytes())for p in self.snapshot})

    def test_wrong_deadline_and_delayed_clear_rejected(self):
        selected=self.source.replace(repair.DEFAULT,repair.SELECTED,1)
        for name,old,new in (
            ('late_fault',"wait_cycles>=32'(TRANSACTION_TIMEOUT_CYCLES)-2",
                          "wait_cycles>=32'(TRANSACTION_TIMEOUT_CYCLES)-1"),
            ('missing_previous_clear',"!watchdog_reset_delay && wait_cycles>=",'wait_cycles>='),
            ('wrong_reset', 'wait_cycles<=0;watchdog_reset_delay<=1;',
                           'wait_cycles<=0;watchdog_reset_delay<=0;')):
            self.assertEqual(selected.count(old),1)
            self.execute(name,selected.replace(old,new,1),2,False)

if __name__=='__main__':
    unittest.main(verbosity=2)
