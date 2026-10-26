from pathlib import Path
import hashlib
import runpy
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
EXPERIMENT=ROOT/'reports/hdmi_usb3_20261025'
sys.path.insert(0,str(ROOT))

from tools.workstation_baselines import load_baseline
from tools.workstation_resource_timing import raster


class HdmiUsb3Diagnostic(unittest.TestCase):
    def test_boot_reset_one_shot_exact_duration_and_power_reset(self):
        bench='''
module tb;
reg clk=0;
always #5 clk=~clk;
reg power_reset_n=0;
wire reset_n,restart_done;
integer cycle,reset_edges,hold_cycles;
reg previous_reset_n;
hdmi_usb3_boot_reset #(.RESTART_AFTER_CYCLES(12),.RESTART_HOLD_CYCLES(4))
 startup(.clk(clk),.power_reset_n(power_reset_n),.reset_n(reset_n),.restart_done(restart_done));
task assert_power_reset;
 begin
  #2;power_reset_n=0;#1;
  if(reset_n!==0 || restart_done!==0) $fatal(1,"asynchronous power reset did not assert");
  repeat(2) @(negedge clk);
 end
endtask
task check_sequence;
 begin
  power_reset_n=1;
  previous_reset_n=0;reset_edges=0;hold_cycles=0;
  for(cycle=1;cycle<=200;cycle=cycle+1) begin
   @(posedge clk);#1;
   if(reset_n!==(cycle<=12 || cycle>16)) $fatal(1,"incorrect reset at cycle %0d",cycle);
   if(restart_done!==(cycle>16)) $fatal(1,"incorrect completion at cycle %0d",cycle);
   if(previous_reset_n && !reset_n) reset_edges=reset_edges+1;
   if(!reset_n) hold_cycles=hold_cycles+1;
   previous_reset_n=reset_n;
   @(negedge clk);
  end
  if(reset_edges!=1 || hold_cycles!=4) $fatal(1,"reset repeated or duration changed");
 end
endtask
initial begin
 assert_power_reset;
 check_sequence;
 assert_power_reset;
 check_sequence;
 assert_power_reset;
 power_reset_n=1;
 repeat(14) @(negedge clk);
 if(reset_n!==0) $fatal(1,"expected to interrupt restart hold");
 assert_power_reset;
 check_sequence;
 $display("PASS single registered restart, exact delay/hold, saturation and power-reset interruption");
 $finish;
end
endmodule
'''
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            (folder/'tb.sv').write_text(bench)
            subprocess.run(['iverilog','-g2012','-s','tb','-o',str(folder/'sim'),
                            str(EXPERIMENT/'hdmi_usb3_diagnostic.sv'),str(folder/'tb.sv')],check=True)
            result=subprocess.run(['vvp',str(folder/'sim')],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('PASS single registered restart',result.stdout)

    def test_startup_change_requires_a_new_candidate_identity(self):
        adapter=runpy.run_path(str(EXPERIMENT/'prepare.py'),run_name='hdmi_diagnostic_test')
        with tempfile.TemporaryDirectory() as directory:
            for user_code in ('C1102515','C11025D1','C11025D2'):
                output=Path(directory)/user_code
                with self.assertRaises(ValueError):
                    adapter['prepare'](output,user_code)
                self.assertFalse(output.exists())

    def test_complete_raster_matches_official_accepted_source(self):
        baseline=load_baseline(ROOT,'accepted_full83')
        reference=baseline.read_bytes('src/video/video_timing_1080p.v').decode()
        candidate=raster(reference)
        self.assertEqual(hashlib.sha256(candidate.encode()).hexdigest(),
                         '2ca5d841f5d3e110e9b85c93898a2c0dc9f0627b3b268ba11e7088d99d08b5db')
        declaration='module video_timing_1080p ('
        self.assertEqual(reference.count(declaration),1)
        reference=reference.replace(declaration,'module official_video_timing (')
        connections='''(.pixel_clk(pixel_clk),.reset_n(reset_n),
 .pixel_x(OUTPUTS[28:17]),.pixel_y(OUTPUTS[16:6]),
 .data_enable(OUTPUTS[5]),.hsync(OUTPUTS[4]),.vsync(OUTPUTS[3]),
 .frame_start(OUTPUTS[2]),.line_start(OUTPUTS[1]),.vblank_start(OUTPUTS[0]));'''
        bench='''module tb;
reg pixel_clk=0;
reg reset_n=0;
wire [28:0] reference_outputs,candidate_outputs;
integer cycle,active_pixels=0,vblank_pixels=0,vsync_pixels=0;
always #2 pixel_clk=~pixel_clk;
'''+('official_video_timing reference_timing'+connections.replace('OUTPUTS','reference_outputs'))+(
    'video_timing_1080p candidate_timing'+connections.replace('OUTPUTS','candidate_outputs'))+'''
initial begin
 repeat(4) @(negedge pixel_clk);
 reset_n=1;
 for(cycle=0;cycle<2200*1125;cycle=cycle+1) begin
  @(negedge pixel_clk);
  if(reference_outputs!==candidate_outputs)
   $fatal(1,"raster mismatch at cycle %0d",cycle);
  if(candidate_outputs[5]) active_pixels=active_pixels+1;
  if(candidate_outputs[3]) vsync_pixels=vsync_pixels+1;
  if(candidate_outputs[0]) vblank_pixels=vblank_pixels+1;
 end
 if(active_pixels!=1920*1080 || vblank_pixels!=1 || vsync_pixels!=5*2200)
  $fatal(1,"incorrect frame geometry");
 reset_n=0;#1;
 if(reference_outputs!==candidate_outputs) $fatal(1,"reset assertion differs");
 repeat(4) @(negedge pixel_clk);
 reset_n=1;
 repeat(4400) begin
  @(negedge pixel_clk);
  if(reference_outputs!==candidate_outputs) $fatal(1,"reset restart differs");
 end
 $display("PASS complete 2200x1125 raster, all output markers and reset restart");
 $finish;
end
endmodule
'''
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            for name,text in (('reference.v',reference),('candidate.v',candidate),('tb.sv',bench)):
                (folder/name).write_text(text)
            subprocess.run(['iverilog','-g2012','-s','tb','-o',str(folder/'sim'),
                            *(str(folder/name) for name in ('reference.v','candidate.v','tb.sv'))],check=True)
            result=subprocess.run(['vvp',str(folder/'sim')],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('PASS complete 2200x1125 raster',result.stdout)

    def test_all_colorbar_pixels_blanking_and_status_characters(self):
        bench='''
module tb;
reg [11:0] pixel_x=0;
reg enabled=1;
wire [23:0] pixel_data;
reg [3:0] character_index=15;
reg [15:0] flags=65535;
wire [7:0] data;
reg [23:0] expected_color;
reg [7:0] expected_character;
integer position,flag_value,character;
reg [3:0] expected_nibble;
hdmi_usb3_colorbars pattern(pixel_x,enabled,pixel_data);
hdmi_usb3_status_character status(character_index,flags,data);
initial begin
 for(position=0;position<1920;position=position+1) begin
  pixel_x=position;#1;
  case(position/240)
   0:expected_color=24'hffffff;
   1:expected_color=24'h00ffff;
   2:expected_color=24'h00ff00;
   3:expected_color=24'hffff00;
   4:expected_color=24'h0000ff;
   5:expected_color=24'hff00ff;
   6:expected_color=24'hff0000;
   7:expected_color=24'h000000;
  endcase
  if(pixel_data!==expected_color) $fatal(1,"color at %0d: %h instead of %h",position,pixel_data,expected_color);
 end
 enabled=0;
 for(position=0;position<4096;position=position+1) begin
  pixel_x=position;#1;
  if(pixel_data!==0) $fatal(1,"blanking is not black");
 end
 for(flag_value=0;flag_value<65536;flag_value=flag_value+1) begin
  flags=flag_value;
  for(character=0;character<11;character=character+1) begin
   character_index=character;#1;
   case(character)
    0:expected_character="H";
    1:expected_character="3";
    2:expected_character="D";
    3:expected_character="1";
    4:expected_character=" ";
    9:expected_character=13;
    10:expected_character=10;
    default:begin
     expected_nibble=(flag_value >> ((8-character)*4)) & 15;
     expected_character=expected_nibble<10 ? 48+expected_nibble : 55+expected_nibble;
    end
   endcase
   if(data!==expected_character) $fatal(1,"status character mismatch: flags=%h index=%0d got=%h expected=%h",flags,character_index,data,expected_character);
  end
 end
 $display("PASS all 1920 pixels, 4096 blank positions and 65536 status words");
 $finish;
end
endmodule
'''
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            (folder/'tb.sv').write_text(bench)
            subprocess.run(['iverilog','-g2012','-s','tb','-o',str(folder/'sim'),
                            str(EXPERIMENT/'hdmi_usb3_diagnostic.sv'),str(folder/'tb.sv')],check=True)
            result=subprocess.run(['vvp',str(folder/'sim')],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('PASS all 1920 pixels',result.stdout)

    def test_source_policy_uses_only_cached_hdmi_subset(self):
        adapter=runpy.run_path(str(EXPERIMENT/'prepare.py'),run_name='hdmi_diagnostic_test')
        self.assertEqual(len(adapter['FILES']),8)
        self.assertTrue(all(not any(part in source for part in ('bluetooth','audio','ddr3','firmware'))
                            for source in adapter['FILES']))
        source=(EXPERIMENT/'hdmi_usb3_diagnostic.sv').read_text()
        self.assertIn("assign flash_cs_n=1'b1;",source)
        self.assertIn("assign hdmi_cec=1'bz;",source)
        self.assertIn('.den(data_enable)',source)
        self.assertNotIn('if(hdmi_hpd)',source)
        self.assertIn(".ext_reset_n(1'b1),.reset_n(power_reset_n)",source)
        self.assertIn('.power_reset_n(power_reset_n),.reset_n(reset_n)',source)
        self.assertIn('report_flags<={10\'d0,restart_done,pixel_seen,status_sync_q[3:0]}',source)
        self.assertIn('parameter integer RESTART_AFTER_CYCLES=25000000',source)
        self.assertIn('parameter integer RESTART_HOLD_CYCLES=1000000',source)


if __name__=='__main__':
    unittest.main()
