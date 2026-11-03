`timescale 1ns/1ps
module tb_pluck_noise_calibration;
 reg clk=0;
 always #5 clk=!clk;
 reg reset=1,online=1,enable=1,recalibrate=0,sample_valid=0;
 reg [79:0] samples=0;
 reg [15:0] on_margin=64,off_margin=32;
 wire calibrated,frame_valid;
 wire [4:0] gates,valid_channels;
 wire [79:0] amplitudes,trigger_counts,noise_floor,on_levels,off_levels,current_vpp;
 wire [31:0] trigger_count;
 wire [15:0] calibration_done;
 midi_pluck_vpp_detector #(.WINDOW_SAMPLES(4),.CALIBRATION_WINDOWS(4),.HOLD_WINDOWS(2),.QUIET_WINDOWS(3),.ADAPTIVE_NOISE(1)) dut(
  .clk(clk),.reset(reset),.online(online),.enable(enable),.recalibrate(recalibrate),.sample_valid(sample_valid),.samples(samples),
  .on_threshold(on_margin),.off_threshold(off_margin),.calibrated(calibrated),.frame_valid(frame_valid),.gates(gates),
  .amplitudes(amplitudes),.trigger_counts(trigger_counts),.trigger_count(trigger_count),.noise_floor(noise_floor),
  .on_levels(on_levels),.off_levels(off_levels),.current_vpp(current_vpp),.valid_channels(valid_channels),
  .calibration_windows_done(calibration_done));
 task sample5;
  input [15:0] first,second,third,fourth,fifth;
  begin
   @(negedge clk);samples={fifth,fourth,third,second,first};sample_valid=1;
   @(negedge clk);sample_valid=0;
  end
 endtask
 task window5;
  input [15:0] first,second,third,fourth,fifth;
  begin
   sample5(16'h8000,16'h8000,16'h8000,16'h8000,16'h8000);
   sample5(16'h8000,16'h8000,16'h8000,16'h8000,16'h8000);
   sample5(16'h8000,16'h8000,16'h8000,16'h8000,16'h8000);
   sample5(first-16'd32768,second-16'd32768,third-16'd32768,fourth-16'd32768,fifth-16'd32768);
  end
 endtask
 task calibrate_idle;
  begin
   window5(10,80,20,100,30);window5(15,100,25,160,35);
   window5(12,140,24,180,32);window5(20,160,30,200,40);
  end
 endtask
 task quiet_window;
  begin window5(10,100,20,140,30);end
 endtask
 initial begin #100000;$fatal(1,"noise calibration timeout");end
 initial begin
  repeat(3)@(negedge clk);reset=0;
  calibrate_idle();
  if(!calibrated || calibration_done!=4 || trigger_count!=0 || valid_channels!=31)$fatal(1,"noise calibration published notes or incomplete validity");
  if(noise_floor!=={16'd40,16'd200,16'd30,16'd160,16'd20})$fatal(1,"independent channel noise peaks/last window lost: %h",noise_floor);
  if(on_levels!=={16'd104,16'd264,16'd94,16'd224,16'd84} || off_levels!=={16'd72,16'd232,16'd62,16'd192,16'd52})
   $fatal(1,"per-channel noise-plus-margin levels incorrect");
  repeat(100)begin
   quiet_window();window5(19,158,29,198,39);window5(0,0,0,0,0);
  end
  if(trigger_count!=0 || gates!=0)$fatal(1,"channels 2/4 idle noise caused retrigger");
  window5(84,100,20,140,30);
  if(trigger_count!=1 || gates!=1 || current_vpp[15:0]!=84)$fatal(1,"single-window real pulse or exact threshold not accepted");
  repeat(12)window5(200,100,20,140,30);
  if(trigger_count!=1 || gates!=0 || noise_floor[15:0]!=20)$fatal(1,"continuous activity retriggered or polluted frozen noise reference");
  quiet_window();quiet_window();window5(200,100,20,140,30);
  if(trigger_count!=1)$fatal(1,"fewer than three quiet windows rearmed");
  repeat(3)quiet_window();window5(200,300,200,400,200);
  if(trigger_count!=6 || gates!=31)$fatal(1,"five-channel rearm/mapping changed");
  @(negedge clk);recalibrate=1;on_margin=48;off_margin=24;
  @(negedge clk);recalibrate=0;
  if(calibrated || gates!=0 || noise_floor!=0 || trigger_count!=6)$fatal(1,"recalibration did not fail closed/retain counts");
  calibrate_idle();
  if(on_levels[31:16]!=208 || off_levels[63:48]!=224 || trigger_count!=6)$fatal(1,"new margins not authoritative after recalibration");
  @(negedge clk);enable=0;
  @(negedge clk);
  window5(65535,65535,65535,65535,65535);
  if(calibrated || valid_channels!=0 || noise_floor!=0 || current_vpp!={5{16'hffff}} || trigger_count!=6)
   $fatal(1,"disabled detector stopped measurements or retained learned arm");
  @(negedge clk);enable=1;
  repeat(4)window5(65520,20,30,40,50);
  if(!calibrated || valid_channels!=30 || on_levels[15:0]!=65535)$fatal(1,"overflowed noise-plus-margin threshold not inhibited");
  repeat(5)begin window5(65535,20,30,40,50);window5(0,0,0,0,0);end
  if(trigger_count!=6)$fatal(1,"saturated/noisy channel wrapped into sensitive threshold");
  @(negedge clk);online=0;
  @(negedge clk);
  if(calibrated || noise_floor!=0 || valid_channels!=0 || gates!=0 || trigger_count!=6)$fatal(1,"ADC fault kept stale calibration");
  online=1;calibrate_idle();
  if(trigger_count!=6 || !calibrated)$fatal(1,"ADC recovery replayed activity");
  $display("PASS tb_pluck_noise_calibration independent noise peaks, idle 2/4 jitter suppression, real short pulses, held activity/rearm, margins, disarm, overflow and ADC recovery");$finish;
 end
endmodule
