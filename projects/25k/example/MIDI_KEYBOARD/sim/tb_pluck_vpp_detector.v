`timescale 1ns/1ps
module tb_pluck_vpp_detector;
 reg clk=0;
 always #5 clk=!clk;
 reg reset=1,online=1,enable=1,recalibrate=0,sample_valid=0;
 reg [79:0] samples=0;
 wire calibrated,frame_valid,sample_ready;
 wire [4:0] gates;
 wire [79:0] amplitudes,trigger_counts;
 wire [31:0] trigger_count;
 wire [15:0] overruns;
 integer frames=0;
 midi_pluck_vpp_detector #(.WINDOW_SAMPLES(4),.CALIBRATION_WINDOWS(2),.HOLD_WINDOWS(2),.QUIET_WINDOWS(2),.DISPLAY_WINDOWS(10)) dut(
  .clk(clk),.reset(reset),.online(online),.enable(enable),.recalibrate(recalibrate),.sample_valid(sample_valid),.samples(samples),
  .on_threshold(16'd80),.off_threshold(16'd20),.calibrated(calibrated),.frame_valid(frame_valid),.sample_ready(sample_ready),
  .gates(gates),.amplitudes(amplitudes),.trigger_counts(trigger_counts),.trigger_count(trigger_count),.overruns(overruns));
 always @(posedge clk)if(!reset && frame_valid)frames=frames+1;
 task sample5;
  input signed [15:0] first,second,third,fourth,fifth;
  begin
   @(negedge clk);samples={fifth,fourth,third,second,first};sample_valid=1;
   @(negedge clk);sample_valid=0;
  end
 endtask
 task window_all;
  input signed [15:0] low_value,high_value;
  begin
   sample5(low_value,low_value,low_value,low_value,low_value);
   sample5(low_value,low_value,low_value,low_value,low_value);
   sample5(low_value,low_value,low_value,low_value,low_value);
   sample5(high_value,high_value,high_value,high_value,high_value);
  end
 endtask
 task quiet_rearm;
  begin repeat(4)window_all(0,0);end
 endtask
 initial begin #100000;$fatal(1,"Vpp detector timeout");end
 initial begin
  repeat(3)@(negedge clk);reset=0;
  window_all(10000,10000);
  if(calibrated || gates!=0 || amplitudes!=0)$fatal(1,"first window/DC calibration incorrect");
  window_all(16000,16000);
  if(!calibrated || gates!=0 || amplitudes!=0 || trigger_count!=0)$fatal(1,"cross-window offset caused Vpp or startup replay");
  window_all(10000,10100);
  if(gates!=31 || trigger_count!=5 || trigger_counts!={5{16'd1}} || amplitudes!={5{16'd100}})
   $fatal(1,"last sample/full five-way trigger mismatch gates=%b total=%d Vpp=%h",gates,trigger_count,amplitudes);
  window_all(0,0);if(gates!=31)$fatal(1,"hold expired early");
  window_all(0,0);if(gates!=0)$fatal(1,"hold did not release at exact window count");
  window_all(0,0);window_all(0,0);
  if(amplitudes!={5{16'd100}})$fatal(1,"short pulse display hold lost");
  window_all(-500,-400);
  if(gates!=31 || trigger_count!=10)$fatal(1,"display hold blocked actual quiet rearm");
  @(negedge clk);enable=0;
  @(negedge clk);if(gates!=0 || calibrated)$fatal(1,"disarm failed closed");
  window_all(-32768,32767);
  if(amplitudes!={5{16'hffff}} || trigger_count!=10)$fatal(1,"signed full-scale span or disabled measurement incorrect");
  @(negedge clk);enable=1;
  window_all(0,0);window_all(0,0);
  sample5(0,0,0,0,0);sample5(0,0,0,0,0);sample5(0,0,0,0,0);sample5(0,-100,0,0,0);
  if(gates!=2 || trigger_count!=11 || trigger_counts[31:16]!=3)$fatal(1,"individual negative channel mapping incorrect");
  @(negedge clk);recalibrate=1;
  @(negedge clk);recalibrate=0;
  if(gates!=0 || calibrated || trigger_count!=11)$fatal(1,"threshold recalibration lost counts or retained gate");
  window_all(0,100);window_all(0,100);window_all(0,100);
  if(trigger_count!=11 || gates!=0)$fatal(1,"active calibration signal replayed");
  window_all(0,0);window_all(0,0);
  @(negedge clk);dut.channels[0].channel_triggers=16'hfffe;dut.trigger_count=32'hfffffffd;
  window_all(0,100);
  if(trigger_counts[15:0]!=16'hffff || trigger_count!=2)$fatal(1,"saturating channel or wrapping total count incorrect");
  quiet_rearm();window_all(0,100);
  if(trigger_counts[15:0]!=16'hffff || trigger_count!=7)$fatal(1,"channel counter saturation failed");
  @(negedge clk);online=0;
  @(negedge clk);
  if(calibrated || gates!=0 || amplitudes!=0 || trigger_count!=7)$fatal(1,"ADC fault did not cancel/clear measurement while retaining counts");
  online=1;window_all(0,0);window_all(0,0);
  if(!calibrated || trigger_count!=7 || gates!=0)$fatal(1,"recovery replayed note");
  @(negedge clk);reset=1;
  @(negedge clk);reset=0;
  if(trigger_count!=0 || trigger_counts!=0 || gates!=0 || calibrated || !sample_ready || overruns!=0)$fatal(1,"reset/acceptance invariant incorrect");
  if(frames<20)$fatal(1,"window commit pulses missing");
  $display("PASS tb_pluck_vpp_detector signed window Vpp, DC rejection, pulse hold, exact gate/rearm, five-way counts, disarm, recalibration, fault and reset");$finish;
 end
endmodule
