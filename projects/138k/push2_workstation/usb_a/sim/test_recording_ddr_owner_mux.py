#!/usr/bin/env python3
"""Two real native-commit bridges, disjoint DDR regions and adversarial returns."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class RecordingOwnerMux(unittest.TestCase):
    def simulate(self, source):
        with tempfile.TemporaryDirectory(prefix='recording-owner-mux-') as directory:
            executable=Path(directory)/'tb'
            rtl=Path(directory)/'mux.sv';rtl.write_text(source)
            command=['iverilog','-g2012','-Wall','-s','tb_recording_ddr_owner_mux','-o',str(executable),
                str(ROOT/'sim/memory/tb_recording_ddr_owner_mux.sv'),
                str(rtl),
                str(ROOT/'rtl/memory/workstation_recording_ddr_native_bridge.sv')]
            result=subprocess.run(command,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run(['vvp',str(executable)],capture_output=True,text=True,timeout=30)
            return result

    def test_real_bridges_commit_fairness_masks_and_failures(self):
        result=self.simulate((ROOT/'rtl/memory/workstation_recording_ddr_owner_mux.sv').read_text())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('PASS recording owner mux:',result.stdout)
        print(result.stdout.strip())

    def test_commit_owner_range_timeout_fairness_and_rearm_mutants(self):
        original=(ROOT/'rtl/memory/workstation_recording_ddr_owner_mux.sv').read_text()
        changes=[
            ('early commit','state==NATIVE && native_accept_i','state==NATIVE'),
            ('wrong response owner','response_o=owned_response_allowed ? (owner ? 2\'b10:2\'b01)',
                                    'response_o=owned_response_allowed ? (owner ? 2\'b01:2\'b10)'),
            ('read not retained','else state<=RESPONSE;','else state<=IDLE;'),
            ('range not checked','(state==IDLE && available && !address_good)','1\'b0'),
            ('timeout ignored','invalid_response || timed_out ||','invalid_response ||'),
            ('unfair writer','prefer<=!owner','prefer<=owner'),
            ('rearm ignored','rst_ni && channel_ready_i && !transport_fault_o','rst_ni && !transport_fault_o'),
            ('authority withdrawal ignored','(state!=IDLE && !channel_ready_i)','1\'b0')]
        for label,old,new in changes:
            with self.subTest(mutation=label):
                self.assertIn(old,original)
                result=self.simulate(original.replace(old,new))
                self.assertNotEqual(result.returncode,0,label+' escaped the protocol oracle')
                self.assertIn('FATAL:',result.stdout)

    def test_owned_transfer_immediate_vetoes_and_actual_source_mutants(self):
        bench=(ROOT/'sim/memory/tb_recording_ddr_owner_mux.sv').read_text()
        bench=bench.replace('module tb_recording_ddr_owner_mux;',
            'module tb_recording_ddr_owner_mux #(parameter DIRECTED=1);',1)
        anchor='    initial begin\n        reset();'
        self.assertEqual(bench.count(anchor),1)
        bench=bench.replace(anchor,'    initial if(!DIRECTED)begin\n        reset();',1)
        directed='''
    initial if(DIRECTED)begin
        #1;reset_n=1;channel_ready=1;upstream_fault=0;
        force dut.state=2'd1;force dut.owner=1'b0;
        force dut.fault_o=1'b0;force dut.active_write=1'b0;force dut.waited=32'd0;
        native_commit=1;read_return=0;#0.1;
        if(native!==2'b01 || response!==0)$fatal(1,"owned clean native transfer");
        upstream_fault=1;#0.1;
        if(native!==0 || response!==0)$fatal(1,"owned transport veto");
        upstream_fault=0;force dut.active_write=1'b1;read_return=1;#0.1;
        if(native!==0 || response!==0)$fatal(1,"owned write response veto");
        force dut.state=2'd2;force dut.active_write=1'b0;native_commit=0;#0.1;
        if(native!==0 || response!==2'b01)$fatal(1,"owned clean delayed response");
        native_commit=1;#0.1;
        if(native!==0 || response!==0)$fatal(1,"owned invalid native response veto");
        native_commit=0;channel_ready=0;#0.1;
        if(native!==0 || response!==0)$fatal(1,"owned authority withdrawal veto");
        $display("PASS owned transfer immediate veto controls");$finish;
    end
'''
        pos=bench.rfind('endmodule');bench=bench[:pos]+directed+bench[pos:]
        source=(ROOT/'rtl/memory/workstation_recording_ddr_owner_mux.sv').read_text()
        mutants=[
            ('transport', 'wire owned_open=rst_ni && channel_ready_i && !fault_o && !transport_fault_i;',
                'wire owned_open=rst_ni && channel_ready_i && !fault_o;', 'owned transport veto'),
            ('write_response', '(owned_open && !(response_i && active_write))',
                '(owned_open)', 'owned write response veto'),
            ('invalid_native', '(owned_open && !invalid_native)',
                '(owned_open)', 'owned invalid native response veto')]
        with tempfile.TemporaryDirectory(prefix='recording-owned-veto-') as directory:
            stage=Path(directory);tb=stage/'tb.sv';tb.write_text(bench)
            cases=[('baseline',source,None)]
            for name,old,new,expected in mutants:
                self.assertEqual(source.count(old),1)
                cases.append((name,source.replace(old,new,1),expected))
            for name,actual,expected in cases:
                with self.subTest(case=name):
                    rtl=stage/(name+'.sv');rtl.write_text(actual);executable=stage/(name+'.vvp')
                    c=subprocess.run(['iverilog','-g2012','-s','tb_recording_ddr_owner_mux','-o',str(executable),
                        str(tb),str(rtl),str(ROOT/'rtl/memory/workstation_recording_ddr_native_bridge.sv')],
                        capture_output=True,text=True,timeout=30)
                    self.assertEqual(c.returncode,0,c.stdout+c.stderr)
                    r=subprocess.run(['vvp',str(executable)],capture_output=True,text=True,timeout=30)
                    if expected:
                        self.assertNotEqual(r.returncode,0)
                        self.assertIn(expected,r.stdout)
                    else:
                        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
                        self.assertIn('PASS owned transfer immediate veto controls',r.stdout)
        print('PASS owned transfer immediate veto controls and 3 actual source mutants')

if __name__=='__main__':unittest.main()
