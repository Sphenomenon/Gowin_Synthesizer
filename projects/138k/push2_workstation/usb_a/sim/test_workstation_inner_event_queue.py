"""M A14 ready path repair: queue ordering and real session cancellation."""
from pathlib import Path
import json,os,subprocess,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools import workstation_inner_event_queue as repair

class InnerQueue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected=os.environ.get('GW138K_INNER_QUEUE_OUTPUT')
        cls.temp=None if selected else tempfile.TemporaryDirectory(prefix='inner-event-queue-')
        cls.out=Path(selected or cls.temp.name)
        if selected:cls.out.mkdir(parents=True,exist_ok=False)
        cls.paths=[ROOT/p for p in (repair.SOURCE,repair.QUEUE,repair.MANIFEST,repair.TOOL,
            'rtl/control/workstation_session.sv','sim/control/tb_workstation_event_queue.sv',
            'sim/control/tb_workstation_queued_session.sv')]+[Path(__file__)]
        cls.hashes={str(p.relative_to(ROOT)):repair.digest(p.read_bytes())for p in cls.paths}
        cls.runs=[]

    @classmethod
    def tearDownClass(cls):
        unchanged=cls.hashes=={str(p.relative_to(ROOT)):repair.digest(p.read_bytes())for p in cls.paths}
        (cls.out/'verification.json').write_text(json.dumps(dict(inputs_sha256=cls.hashes,
            inputs_unchanged=unchanged,runs=cls.runs,
            scope='18-bit queue scoreboard and actual session lifecycle; full DSP scheduling requires integration regression',
            hardware_tested=False),indent=2)+'\n')
        if cls.temp:cls.temp.cleanup()
        assert unchanged,'source changed during test'

    def run_bench(self,name,top,bench,queue=None,expected=None):
        queue=queue or (ROOT/repair.QUEUE).read_text();p=self.out/(name+'.sv');p.write_text(queue)
        binary=self.out/(name+'.vvp')
        cmd=['iverilog','-g2012','-s',top,'-o',str(binary),str(p),
             str(ROOT/'rtl/control/workstation_session.sv'),str(ROOT/bench)]
        compiled=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
        self.assertEqual(compiled.returncode,0,compiled.stderr)
        self.assertFalse(compiled.stdout+compiled.stderr,compiled.stdout+compiled.stderr)
        run=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=30)
        log=run.stdout+run.stderr;(self.out/(name+'.log')).write_text(log)
        self.runs.append(dict(name=name,exit_code=run.returncode,expected_failure=expected,
                              queue_sha256=repair.digest(queue),log_sha256=repair.digest(log)))
        if expected:
            self.assertNotEqual(run.returncode,0,log);self.assertIn(expected,log)
        else:self.assertEqual(run.returncode,0,log);self.assertIn('PASS ',log)

    def test_queue_scoreboard_and_session(self):
        self.run_bench('queue','tb','sim/control/tb_workstation_event_queue.sv')
        self.run_bench('session','queued_session','sim/control/tb_workstation_queued_session.sv')

    def test_wrong_ready_and_lifecycle_rejected(self):
        source=(ROOT/repair.QUEUE).read_text()
        self.run_bench('ready-feedback','tb','sim/control/tb_workstation_event_queue.sv',
            source.replace('wire room=count<2 && !clear;','wire room=(count<2 || event_ready) && !clear;',1),
            'output ready feeds source readiness')
        self.run_bench('lost-lifecycle','queued_session','sim/control/tb_workstation_queued_session.sv',
            source.replace('else if(clear)begin count<=0;head<=0;tail<=0;end',
                           'else if(clear)begin end',1),'detach failed to atomically purge old words')

    def test_explicit_selection_and_parent_identity(self):
        source=(ROOT/repair.SOURCE).read_text()
        parent=repair.restore(repair.SOURCE,source.encode())
        self.assertEqual(repair.digest(parent),json.loads((ROOT/repair.MANIFEST).read_text())['parent_sha256'])
        config={repair.KEY:repair.POLICY,'demo_role':'M',
                'effects_dispatch_policy':'task3_M_reserved_effects_configuration_v1'}
        with tempfile.TemporaryDirectory()as directory:
            stage=Path(directory)
            for relative,destination in ((repair.SOURCE,repair.DESTINATION),(repair.QUEUE,repair.QUEUE)):
                p=stage/destination;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/relative).read_bytes())
            self.assertIsNone(repair.select(stage,{}))
            info=repair.select(stage,config);self.assertEqual(info['capacity_events'],2)
            selected=(stage/repair.DESTINATION).read_text()
            self.assertEqual(repair.unselect(selected),source)
            self.assertEqual(repair.restore(repair.SOURCE,selected.encode()),parent)
            with self.assertRaises(ValueError):repair.select(stage,config)
        with self.assertRaises(ValueError):repair.configured(dict(config,demo_role='W'))
        with self.assertRaises(ValueError):repair.restore(repair.SOURCE,source.replace('.clear(usb_lifecycle)',".clear(1'b0)",1).encode())

if __name__=='__main__':unittest.main(verbosity=2)
