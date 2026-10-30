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
            ('wrong response owner','response_o=open && read_return ? (owner ? 2\'b10:2\'b01)',
                                    'response_o=open && read_return ? (owner ? 2\'b01:2\'b10)'),
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

if __name__=='__main__':unittest.main()
