#!/usr/bin/env python3
"""A9 divider raw release: stopped USB clock and exact source lineage."""
from pathlib import Path
import hashlib,json,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]

class TelemetryRelease(unittest.TestCase):
    def test_actual_divider_stopped_clock_and_parent_negative(self):
        p=ROOT/'rtl/telemetry/gw138k_push_performance_uart.sv'
        meta=json.loads(p.with_suffix('.provenance.json').read_text())
        source=p.read_text();parent=source.replace(meta['new'],meta['old'],1)
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),meta['source_sha256'])
        self.assertEqual(hashlib.sha256(parent.encode()).hexdigest(),meta['parent_sha256'])
        # Unchanged surrounding transports are stubbed: this test observes the
        # actual divider and its release, not mailbox delivery or UART bytes.
        tb='''`timescale 1ns/1ps
module gw138k_stream_cdc #(parameter WIDTH=1)(input reset_n,source_clk,destination_clk,source_valid,input [WIDTH-1:0]source_data,output [31:0]drop_count,output destination_valid,output [WIDTH-1:0]destination_data);
assign drop_count=0;assign destination_valid=0;assign destination_data=0;endmodule
module uart_tx #(parameter BAUD=1)(input clk,rst_n,input [31:0]data,input valid,output ready,serial_out,byte_done);
assign ready=1;assign serial_out=1;assign byte_done=0;endmodule
module tb;
reg clk=0,usb=0,reset=1,assert_n=1;always #5 clk=~clk;
gw138k_push_performance_uart #(.USB_CDC_SEPARATE_RESET(1)) dut(
.clk_50m(clk),.reset_n(reset),.usb_clk(usb),.usb_reset_n(reset),.usb_cdc_assert_ni(assert_n),
.audio_clk(clk),.audio_reset_n(reset),.audio_locked(1'b1),.sample_valid(1'b0),
.memory_flags(8'd0),.audio_status(32'd0),.video_diagnostics(128'd0),
.cpu_clk(clk),.cpu_reset_n(reset),.cpu_words(224'd0),.performance_words(448'd0),
.usb_words(224'd0),.push_words(224'd0));
task tick;begin #3;usb=1;#1;usb=0;#1;end endtask
initial begin
#1;assert_n=0;reset=0;#1;
if(dut.usb_divider!==0)$fatal(1,"async assertion did not clear divider");
assert_n=1;reset=1;#30;
if(dut.usb_divider_reset_n!==0)$fatal(1,"raw release escaped with USB clock stopped");
tick();if(dut.usb_divider_reset_n!==0)$fatal(1,"only one receiving edge");
tick();if(dut.usb_divider_reset_n!==1 || dut.usb_divider!==0)$fatal(1,"second-edge release");
tick();if(dut.usb_divider!==1)$fatal(1,"divider did not start after release");
assert_n=0;#1;if(dut.usb_divider!==0 || dut.usb_divider_reset_n!==0)$fatal(1,"stopped-clock reassertion");
assert_n=1;#20;if(dut.usb_divider_reset_n!==0)$fatal(1,"warm release escaped");
tick();tick();tick();if(dut.usb_divider!==1)$fatal(1,"warm release failed");
$display("PASS actual telemetry USB local release");$finish;
end
endmodule
'''
        with tempfile.TemporaryDirectory()as name:
            out=Path(name);(out/'tb.sv').write_text(tb)
            for label,text,passed in [('current',source,True),('raw_parent',parent,False)]:
                (out/'source.sv').write_text(text)
                c=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'test'),str(out/'tb.sv'),str(out/'source.sv')],capture_output=True,text=True)
                self.assertEqual(c.returncode,0,c.stderr)
                r=subprocess.run(['vvp',str(out/'test')],capture_output=True,text=True,timeout=30)
                self.assertEqual(r.returncode==0,passed,(label,r.stdout,r.stderr))
                if not passed:self.assertIn('raw release escaped',r.stdout)

if __name__=='__main__':unittest.main()
