`timescale 1ns/1ps
module tb_pluck_carrier_detector;
 reg clk=0;
 always #10 clk=!clk;
 reg reset=1,online=1,enable=0,recalibrate=0,sample_valid=0;
 reg [79:0] samples=0;
 reg [15:0] on_margin=64,off_margin=32;
 wire calibrated,frame_valid;
 wire [4:0] gates,valid_channels;
 wire [79:0] references,on_levels,off_levels,current_vpp,counts;
 wire [31:0] total;
 wire [15:0] progress;
 midi_pluck_vpp_detector #(.WINDOW_SAMPLES(4),.CALIBRATION_WINDOWS(3),.SETTLE_WINDOWS(2),
  .CARRIER_MODE(1),.QUIET_WINDOWS(3),.HOLD_WINDOWS(5),.DISPLAY_WINDOWS(4),.TRIGGER_WINDOWS(2)) dut(
  .clk(clk),.reset(reset),.online(online),.enable(enable),.recalibrate(recalibrate),.sample_valid(sample_valid),
  .samples(samples),.on_threshold(on_margin),.off_threshold(off_margin),.calibrated(calibrated),.frame_valid(frame_valid),
  .gates(gates),.trigger_counts(counts),.trigger_count(total),.noise_floor(references),.on_levels(on_levels),
  .off_levels(off_levels),.current_vpp(current_vpp),.valid_channels(valid_channels),.calibration_windows_done(progress));
 task window;
  input [15:0] first,second,third,fourth,fifth;
  integer sample_number;
  begin
   for(sample_number=0;sample_number<4;sample_number=sample_number+1)begin
    @(negedge clk);sample_valid=1;
    samples=sample_number%2==0 ? {5{16'h8000}} :
      {16'h8000+fifth,16'h8000+fourth,16'h8000+third,16'h8000+second,16'h8000+first};
   end
   @(negedge clk);sample_valid=0;
  end
 endtask
 task open_window;
  begin window(1000,2000,800,3000,100);end
 endtask
 task calibrate_open;
  begin
   window(0,0,0,0,0);window(60000,60000,60000,60000,60000);
   if(calibrated || progress!=0)$fatal(1,"Carrier settling windows entered calibration");
   window(1100,2100,900,3100,110);open_window;window(1200,2200,1000,3200,120);
   if(!calibrated || progress!=3 || valid_channels!=15 || references!=={16'd100,16'd3000,16'd800,16'd2000,16'd1000})
    $fatal(1,"Carrier reference must be independent per-channel minimum after settling");
   if(on_levels[15:0]!=500 || off_levels[15:0]!=750 || on_levels[31:16]!=1000 || off_levels[31:16]!=1500)
    $fatal(1,"Carrier drop thresholds/hysteresis incorrect");
  end
 endtask
 initial begin
  repeat(4)@(negedge clk);reset=0;
  repeat(8)open_window;
  if(calibrated || gates!=0 || total!=0)$fatal(1,"Disarmed carrier input became ready/triggered");
  enable=1;calibrate_open;
  repeat(3)open_window;
  repeat(10)window(950,1900,750,2900,0);
  if(total!=0)$fatal(1,"Open carrier jitter/weak invalid CHN5 caused a trigger");
  window(400,2000,800,3000,0);open_window;
  if(total!=0)$fatal(1,"Single-window glitch triggered");
  window(500,1000,800,3000,0);
  if(gates!=0 || total!=0)$fatal(1,"Carrier low debounce missing");
  window(500,1000,800,3000,0);
  if(gates!=3 || total!=2 || counts[31:0]!==32'h00010001)$fatal(1,"Simultaneous inclusive falling-Vpp triggers missing");
  repeat(30)window(100,100,800,3000,0);
  if(gates!=0 || total!=2 || current_vpp[31:0]!==32'h00640064)$fatal(1,"Held blockage retriggered or current Vpp is peak-held");
  repeat(5)window(700,1400,800,3000,100);
  repeat(3)window(100,100,800,3000,100);
  if(total!=2)$fatal(1,"Sub-release amplitude rearmed detector");
  open_window;open_window;window(100,100,800,3000,100);
  repeat(3)window(100,100,800,3000,100);
  if(total!=2)$fatal(1,"Incomplete release debounce rearmed detector");
  repeat(3)open_window;
  repeat(2)window(400,900,800,3000,100);
  if(total!=4 || gates!=3)$fatal(1,"Restored beams did not rearm independent channels");
  online=0;@(negedge clk);
  if(gates!=0 || calibrated || valid_channels!=0)$fatal(1,"ADC fault did not cancel gates/reference");
  online=1;calibrate_open;
  repeat(3)open_window;
  repeat(2)window(1000,2000,200,500,100);
  if(total!=6 || gates!=12)$fatal(1,"CHN3/4 drop mapping incorrect");
  enable=0;@(negedge clk);
  if(gates!=0 || calibrated || total!=6)$fatal(1,"OFF cancellation/count retention incorrect");
  enable=1;recalibrate=1;@(negedge clk);recalibrate=0;
  repeat(2)window(65535,65535,65535,65535,65535);
  repeat(3)window(65535,65535,65535,65535,65535);
  if(references!=={5{16'hffff}} || on_levels[15:0]!=32767 || off_levels[15:0]!=49151 || valid_channels!=31)
   $fatal(1,"Full signed-range carrier span/ceil percentage overflow");
  on_margin=40000;off_margin=20000;
  repeat(4)window(65535,65535,65535,65535,65535);
  repeat(4)window(0,0,0,0,0);
  if(valid_channels!=0 || total!=6 || gates!=0)$fatal(1,"Unrepresentable carrier drop margins must fail closed");
  $display("PASS tb_pluck_carrier_detector settling/open-reference, five independent hysteresis thresholds, low debounce, single-shot blockage, release debounce, fault/OFF/full-range/overflow");$finish;
 end
 initial begin #1000000;$fatal(1,"Carrier detector timeout");end
endmodule
