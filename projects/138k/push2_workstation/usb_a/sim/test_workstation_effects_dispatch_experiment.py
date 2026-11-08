import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import workstation_effects_dispatch_experiment as experiment

BENCH='''`timescale 1ns/1ps
module tb;
reg clk=0,rst=0,config_request=0,history_request=0,rate=0,clear=0,fault=0;
reg config_ready=0,history_ready=0,quiet=1;
wire pending,config_fire,history_fire,held_rate;
integer dispatched=0;
always #5 clk=~clk;
workstation_effects_config_dispatch dut(.clk_i(clk),.rst_ni(rst),
 .reserve_config_i(config_request),.reserve_history_i(history_request),.rate_44100_i(rate),
 .clear_i(clear),.fault_i(fault),.all_config_ready_i(config_ready),
 .all_history_ready_i(history_ready),.all_quiet_i(quiet),.pending_o(pending),
 .config_valid_o(config_fire),.history_valid_o(history_fire),.rate_44100_o(held_rate));
always @(posedge clk)if(config_fire || history_fire)dispatched=dispatched+1;
initial begin
 repeat(2)@(negedge clk);rst=1;
 @(negedge clk);config_request=1;rate=1;
 @(negedge clk);config_request=0;rate=0;
 if(!pending || !held_rate || dispatched!=0)$fatal(1,"missing held reservation");
 clear=1;config_ready=1;repeat(3)@(negedge clk);
 if(!pending || dispatched!=0)$fatal(1,"PANIC lost or dispatched reservation");
 clear=0;fault=1;repeat(3)@(negedge clk);
 if(!pending || dispatched!=0)$fatal(1,"fault dispatched reservation");
 fault=0;quiet=0;repeat(3)@(negedge clk);
 if(!pending || dispatched!=0)$fatal(1,"busy child admitted command");
 quiet=1;@(negedge clk);
 if(pending || dispatched!=1 || !held_rate)$fatal(1,"configuration not dispatched exactly once");
 history_request=1;@(negedge clk);history_request=0;
 repeat(2)@(negedge clk);
 if(!pending || config_fire || dispatched!=1)$fatal(1,"history used config readiness");
 history_ready=1;@(negedge clk);
 if(pending || dispatched!=2)$fatal(1,"history not dispatched once");
 config_ready=0;config_request=1;@(negedge clk);config_request=0;
 if(!pending)$fatal(1,"missing reset test reservation");
 rst=0;#1;
 if(pending || config_fire || history_fire)$fatal(1,"reset retained stale command");
 $display("PASS held command PANIC fault readiness reset dispatched=%0d",dispatched);$finish;
end
initial begin #2000;$fatal(1,"timeout");end
endmodule
'''

class EffectsDispatchExperiment(unittest.TestCase):
    def setUp(self):
        from tools.workstation_effect_gain_path import normalize
        self.parent=normalize((ROOT/experiment.SOURCE).read_bytes()).decode()
        self.selected=experiment.apply(self.parent)

    def test_exact_inverse_and_unselected_scope(self):
        self.assertEqual(experiment.restore(self.selected),self.parent)
        e=experiment.evidence(self.selected)
        self.assertFalse(e['production_profile_selected'])
        self.assertTrue(e['normal_sample_datapath_unchanged'])

    def test_parent_and_each_anchor_drift_fail_closed(self):
        for before,_,_ in experiment.EDITS:
            with self.subTest(anchor=before),self.assertRaises(ValueError):
                experiment.apply(self.parent.replace(before,before+' ',1))
        with self.assertRaises(ValueError):experiment.apply(self.parent+'\n')

    def test_selected_and_each_inverse_anchor_drift_fail_closed(self):
        for before,after,_ in experiment.EDITS:
            with self.subTest(anchor=after),self.assertRaises(ValueError):
                experiment.restore(self.selected.replace(after,before,1))
        with self.assertRaises(ValueError):experiment.restore(self.selected+'// changed sample path\n')

    def test_maintained_native_selection_inverse(self):
        from tools import workstation_effects_reserved_config as m
        current=(ROOT/m.SOURCE).read_bytes()
        self.assertEqual(m.digest(current),m.NATIVE_SHA256)
        parent=m.normalize(current)
        self.assertEqual(m.digest(parent),m.PARENT_SHA256)
        self.assertEqual(m.normalize(current.replace(m.DEFAULT.encode(),m.SELECTED.encode())),parent)
        for before,after in m.EDITS:
            with self.subTest(anchor=after):
                self.assertNotEqual(m.normalize(current.replace(after.encode(),before.encode(),1)),parent)

    def test_held_command_and_destructive_controls(self):
        original=(ROOT/experiment.DISPATCH).read_text()
        mutants=dict(
            cancels_on_PANIC=original.replace('else if(config_valid_o || history_valid_o)',
                'else if(clear_i || config_valid_o || history_valid_o)'),
            mutable_rate=original.replace('rate_44100_o<=rate_44100_i','rate_44100_o<=0'),
            ignores_fault=original.replace('!fault_i','1\'b1'))
        for name,text in [('original',original),*mutants.items()]:
            with self.subTest(case=name),tempfile.TemporaryDirectory(prefix='effects-dispatch-') as directory:
                p=Path(directory);(p/'dut.sv').write_text(text);(p/'tb.sv').write_text(BENCH)
                compile=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(p/'dut.sv'),str(p/'tb.sv')],capture_output=True,text=True,timeout=30)
                self.assertEqual(compile.returncode,0,compile.stderr)
                run=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True,timeout=30)
                if name=='original':
                    self.assertEqual(run.returncode,0,run.stdout+run.stderr)
                    self.assertIn('dispatched=2',run.stdout)
                else:self.assertNotEqual(run.returncode,0,'destructive control passed: '+name)

if __name__=='__main__':unittest.main()
