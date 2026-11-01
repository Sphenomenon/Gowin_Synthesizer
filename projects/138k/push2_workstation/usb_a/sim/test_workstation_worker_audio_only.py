#!/usr/bin/env python3
"""Actual W audio memory, strict retirement and default-profile protection."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_worker_audio_only import constraints, restore_constraints, retired_source


class WorkerAudioOnly(unittest.TestCase):
    def test_hci_only_keeps_all_apb_bounds_without_recording(self):
        from tools.workstation_runtime_profile import protocol_constraints
        base = protocol_constraints()
        selected = protocol_constraints(business_owner_enabled=True, hci_only=True)
        added = [line for line in selected.splitlines() if line not in base.splitlines()]
        self.assertEqual(len(added), 8)
        self.assertTrue(all('business_commands/' in line for line in added))
        self.assertEqual(sum(line.startswith('set_max_delay 20.000 ') for line in added), 2)
        self.assertEqual(sum(line.startswith('set_false_path -hold ') for line in added), 2)
        self.assertEqual(sum(line.startswith('set_max_delay 2.000 ') for line in added), 2)
        self.assertEqual(sum(line.startswith('set_false_path -to ') for line in added), 2)
        self.assertNotIn('recording_ble_store/', selected)
        for options in (dict(business_owner_enabled=True), dict(hci_only=True),
                        dict(hci_only=True, business_owner_enabled=True, ble_raw_enabled=True),
                        dict(hci_only=1, business_owner_enabled=True)):
            with self.assertRaises(ValueError):
                protocol_constraints(**options)

    def test_timing_retirement_is_exact_reversible_and_fail_closed(self):
        source = (
            'create_generated_clock -name video_pixel148 -source [get_ports {clk_50m}] [get_pins {u_video/u_clock/CLKOUT}]\n'
            'set_false_path -to [get_pins {u_video/ui_reset_pipe*/CLEAR live/reset*/CLEAR}]\n'
            'set_false_path -hold -to [get_pins {u_managed/runtime/serializer/current_sequence_0_s*/CE live/pcm*/CE}]\n'
            'set_max_delay 10.000 -from [get_regs {u_video/flags_meta*}] -to [get_regs {u_video/flags_sync*}]\n'
            'set_max_delay 13.020 -from [get_regs {live/data*}] -to [get_regs {live/capture*}]\n'
            'set_false_path -hold -from [get_regs {recording_ble_store/held*}] -to [get_regs {recording_ble_store/local*}]\n'
            'report_timing -setup -to_clock [get_clocks {video_pixel148}]\n')
        selected, evidence = constraints(source)
        self.assertEqual(restore_constraints(selected, evidence), source)
        self.assertIn('set_false_path -to [get_pins {live/reset*/CLEAR}]\n', selected)
        self.assertIn('set_false_path -hold -to [get_pins {live/pcm*/CE}]\n', selected)
        self.assertIn('set_max_delay 13.020 -from [get_regs {live/data*}] -to [get_regs {live/capture*}]\n', selected)
        self.assertIn('u_audio_memory/flags_meta*', selected)
        for text in (selected.replace('13.020', '20.000'), selected.replace('live/reset', 'live/business'),
                     selected.replace('u_audio_memory/flags_meta*', 'u_audio_memory/*'), selected + source):
            with self.assertRaises(ValueError):
                restore_constraints(text, evidence)
        for path in ('rtl/display_data/feedback_dashboard.v', 'src/video/video_timing_1080p.v',
                     'native_bluetooth/bt_gatt.v', 'rtl/bluetooth/cpu_owner/workstation_ble_record_data_engine.sv',
                     'rtl/tf_audio/workstation_tf_runtime_service.sv', 'vendor/sipeed_dvi/dvi_tx_tmds_enc.v'):
            self.assertTrue(retired_source(path), path)
        for path in ('rtl/timing/basic_pitch_ddr_client_queues.sv',
                     'vendor/sipeed_dvi/video_pll_init.v',
                     'rtl/audio/scope_vec/scope_tf_control.sv',
                     'rtl/audio/workstation_ae350_pcm_owner.sv',
                     'rtl/bluetooth/hci_owner/workstation_hci_native_transport.sv',
                     'rtl/workstation/workstation_usb2_input.sv'):
            self.assertFalse(retired_source(path), path)

    def test_default_runtime_modules_are_preprocessor_identical(self):
        # This test protects the default M/accepted hierarchy, independently of
        # any changed source hashes or resource expectations.
        for relative in ('rtl/workstation/workstation_runtime_controlled.sv',
                         'rtl/audio/workstation_observation_consumers.sv'):
            prior = subprocess.check_output(['git', 'show', '615907b1:projects/138k/push2_workstation/usb_a/' + relative], cwd=ROOT)
            with tempfile.TemporaryDirectory(prefix='w21-default-') as directory:
                work = Path(directory)
                (work / 'before.sv').write_bytes(prior)
                outputs = []
                for path in (work / 'before.sv', ROOT / relative):
                    result = subprocess.run(['iverilog', '-g2012', '-E', '-o', '-', str(path)], capture_output=True, check=True)
                    outputs.append(b''.join(result.stdout.split()))
                self.assertEqual(outputs[0], outputs[1], relative)

    def test_unused_synth_midi_retirement_keeps_live_control_constraints(self):
        from tools.workstation_runtime_profile import protocol_constraints
        from tools.workstation_runtime_cdc import runtime_cdc_bundle
        original = runtime_cdc_bundle(ROOT, raw_common_reset=True)['sdc'] + protocol_constraints()
        prior, old_evidence = constraints(original)
        selected, evidence = constraints(original, retire_synth_midi=True)
        removed = [line for line in prior.splitlines() if line not in selected.splitlines()]
        self.assertEqual(len(removed), 2)
        self.assertTrue(all('u_managed/midi_drops/' in line for line in removed))
        self.assertEqual([line for line in selected.splitlines() if line not in prior.splitlines()], [])
        self.assertEqual(restore_constraints(selected, evidence), original)
        self.assertEqual(restore_constraints(prior, old_evidence), original)
        self.assertNotIn('synth_midi_retired', old_evidence)
        self.assertTrue(evidence['synth_midi_retired'])
        for broken in (dict(evidence, synth_midi_retired=False), dict(evidence, synth_midi_retired=1)):
            with self.assertRaises(ValueError):
                restore_constraints(selected, broken)
        self.assertIn('u_managed/pc_bytes/', selected)
        self.assertIn('u_native_usb/', selected)

    def test_real_bist_delay_native_memory_and_failure_quarantine(self):
        with tempfile.TemporaryDirectory(prefix='w21-memory-') as directory:
            work = Path(directory)
            (work / 'src/memory').mkdir(parents=True)
            (work / 'src/memory/ddr_address_map.vh').write_bytes((ROOT / 'rtl/ddr_address_map.vh').read_bytes())
            (work / 'tb.sv').write_text(MEMORY_TB)
            sources = [ROOT / path for path in (
                'rtl/memory/workstation_audio_memory.sv', 'rtl/memory/workstation_ddr_bist.v',
                'rtl/timing/basic_pitch_ddr_client_queues.sv', 'rtl/timing/basic_pitch_ddr_arbiter_pipeline.sv')]
            compile_result = subprocess.run(['iverilog', '-g2012', '-I', str(ROOT), '-I', str(work),
                '-s', 'tb', '-o', str(work / 'sim'), str(work / 'tb.sv'), *map(str, sources)],
                cwd=work, capture_output=True, text=True)
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            result = subprocess.run(['vvp', str(work / 'sim')], cwd=work, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS actual W memory', result.stdout)
            print(result.stdout, end='')


MEMORY_TB = r'''`timescale 1ns/1ps
module tb;
reg clk=0,clk50=0,rst=0,cal=0,pll=0,mrst=0;
always #5 clk=!clk;always #10 clk50=!clk50;
reg dv=0,dw=0;reg[28:0] da=0;reg[255:0] dd=0;
wire ready,crst,drdy,drsp,en,wren,wend;wire[2:0]cmd;
wire[28:0]addr;wire[255:0]data,rd;wire[31:0]mask;wire[7:0]flags;
reg ardy=0,wrdy=0,rv=0;reg[255:0]rdata=0;reg[31:0]lfsr=32'h13579bdf;
workstation_audio_memory #(.BIST_BURSTS(16)) dut(
 .reset_ni(rst),.clk_50m_i(clk50),.memory_clk_i(clk),.memory_reset_ni(mrst),
 .memory_calibrated_i(cal),.memory_pll_locked_i(pll),.client_reset_no(crst),.client_ready_o(ready),
 .delay_valid_i(dv),.delay_write_i(dw),.delay_address_i(da),.delay_data_i(dd),
 .delay_ready_o(drdy),.delay_response_o(drsp),.app_cmd_o(cmd),.app_en_o(en),
 .app_wren_o(wren),.app_wend_o(wend),.app_address_o(addr),.app_data_o(data),.app_mask_o(mask),
 .app_ready_i(ardy),.app_write_ready_i(wrdy),.app_response_i(rv),.app_response_data_i(rdata),
 .response_data_o(rd),.memory_flags_o(flags));
reg[255:0]mem[0:511],pending[0:31];integer rp=0,wp=0,count=0,cycles=0;
integer writes=0,reads=0,responses=0,delay_commands=0;
function integer index_of(input[28:0]a);
 begin index_of=(a>=29'h0c000000 ? 256:0)+a[10:3];end
endfunction
always @(negedge clk)begin
 lfsr={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
 ardy=rst && (lfsr[0]||lfsr[4]);wrdy=rst && (lfsr[1]||lfsr[6]);rv=0;
 if(crst && count>0 && lfsr[3])begin
  rv=1;rdata=pending[rp];rp=(rp+1)%32;count=count-1;responses=responses+1;
 end
end
always @(posedge clk)begin
 cycles=cycles+1;
 if(en && ardy)begin
  if(!crst)$fatal(1,"native request before backend release");
  if(addr[2:0]!=0 || mask!==0)$fatal(1,"BL8/mask changed");
  if(addr>=29'h0c000000 && addr<29'h0c008000)delay_commands=delay_commands+1;
  else if(addr>=128)$fatal(1,"retired client generated DDR transaction %h",addr);
  if(cmd==0)begin
   if(!wren||!wend||!wrdy)$fatal(1,"split write acceptance");
   mem[index_of(addr)]=data;writes=writes+1;
  end else if(cmd==1)begin
   if(count>=31)$fatal(1,"model response queue overflow");
   pending[wp]=mem[index_of(addr)];wp=(wp+1)%32;count=count+1;reads=reads+1;
  end else $fatal(1,"unknown native command");
 end
 if(cycles>100000)$fatal(1,"timeout");
end
task request(input bit write_i,input integer n);
 begin
  @(negedge clk);dv=1;dw=write_i;da=29'h0c000000+n*8;dd={8{32'h12340000+n}};
  do @(posedge clk);while(!drdy);
  @(negedge clk);dv=0;
 end
endtask
integer target;reg[255:0]expected;
initial begin
 #13;rst=1;mrst=1;pll=1;
 repeat(20)begin @(negedge clk);if(en||crst||ready)$fatal(1,"calibration wait removed");end
 cal=1;wait(ready);repeat(6)@(negedge clk);
 if(flags[6]!==1 || flags[2:0]!==3'b011)$fatal(1,"boot status semantics changed");
 for(integer n=0;n<128;n=n+1)request(1,n);
 wait(writes==160);repeat(8)@(negedge clk);
 for(integer n=0;n<128;n=n+1)begin
  request(0,n);wait(drsp);#1;expected={8{32'h12340000+n}};
  if(rd!==expected)$fatal(1,"owner6 data mismatch n=%0d",n);
 end
 repeat(12)@(negedge clk);
 if(delay_commands!=256 || reads!=160 || responses!=160)$fatal(1,"native ledger count mismatch");
 // A truly unsolicited response poisons the ledger, preventing new requests.
 @(negedge clk);force rv=1'b1;@(posedge clk);@(negedge clk);release rv;
 repeat(5)@(negedge clk);if(ready)$fatal(1,"transport fault not quarantined");
 dv=1;dw=0;da=29'h0c000000;
 repeat(20)begin @(negedge clk);if(en)$fatal(1,"new command after transport fault");end
 dv=0;cal=0;#1;if(crst||ready)$fatal(1,"backend loss did not assert locally");
 $display("PASS actual W memory: 64 BIST + 256 delay commands; stalled BL8 writes, ordered reads, boot readiness and fault quarantine");
 $finish;
end
endmodule
'''


if __name__ == '__main__':
    unittest.main()
