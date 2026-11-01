`timescale 1ns/1ps
module tb_pluck_carrier_engine #(parameter integer STABLE_INPUT=0);
 reg clk=0;
 always #10 clk=!clk;
 reg reset=1,online=1,enable=0,recalibrate=0,sample_valid=0;
 reg [79:0] samples=0;
 reg [15:0] on_threshold=64,off_threshold=32;
 wire calibrated,frame_valid,sample_ready;
 wire [4:0] gates,valid_channels;
 wire [79:0] amplitudes,trigger_counts,noise_floor,on_levels,off_levels,current_vpp;
 wire [15:0] calibration_windows_done,overruns;
 wire [31:0] trigger_count;
 wire reference_calibrated,reference_frame_valid;
 wire [4:0] reference_gates,reference_valid_channels;
 wire [79:0] reference_amplitudes,reference_trigger_counts,reference_noise_floor;
 wire [79:0] reference_on_levels,reference_off_levels,reference_current_vpp;
 wire [15:0] reference_calibration_windows_done;
 wire [31:0] reference_trigger_count;
 integer sample_number,channel,checks=0,serial_frames=0,reference_frames=0;
 reg [31:0] random_state=32'h7606b201;
 reg [4:0] blocked=0;
 midi_pluck_carrier_engine #(.WINDOW_SAMPLES(4),.CALIBRATION_WINDOWS(8),.SETTLE_WINDOWS(2),
  .HOLD_WINDOWS(4),.QUIET_WINDOWS(3),.DISPLAY_WINDOWS(5),.STABLE_INPUT(STABLE_INPUT)) dut(.*);
 midi_pluck_vpp_detector #(.CARRIER_MODE(1),.WINDOW_SAMPLES(4),.CALIBRATION_WINDOWS(8),.SETTLE_WINDOWS(2),
  .HOLD_WINDOWS(4),.QUIET_WINDOWS(3),.DISPLAY_WINDOWS(5)) reference(
  .clk(clk),.reset(reset),.online(online),.enable(enable),.recalibrate(recalibrate),.sample_valid(sample_valid),
  .samples(samples),.on_threshold(on_threshold),.off_threshold(off_threshold),
  .calibrated(reference_calibrated),.frame_valid(reference_frame_valid),.gates(reference_gates),
  .amplitudes(reference_amplitudes),.trigger_counts(reference_trigger_counts),.noise_floor(reference_noise_floor),
  .on_levels(reference_on_levels),.off_levels(reference_off_levels),.current_vpp(reference_current_vpp),
  .valid_channels(reference_valid_channels),.calibration_windows_done(reference_calibration_windows_done),
  .trigger_count(reference_trigger_count));
 always @(posedge clk)if(!reset)begin
  if(frame_valid)serial_frames=serial_frames+1;
  if(reference_frame_valid)reference_frames=reference_frames+1;
 end
 task compare;
  begin
   checks=checks+1;
   if({calibrated,gates,amplitudes,trigger_counts,noise_floor,on_levels,off_levels,current_vpp,
       valid_channels,calibration_windows_done,trigger_count} !==
      {reference_calibrated,reference_gates,reference_amplitudes,reference_trigger_counts,reference_noise_floor,
       reference_on_levels,reference_off_levels,reference_current_vpp,reference_valid_channels,
       reference_calibration_windows_done,reference_trigger_count} || serial_frames!=reference_frames || overruns!=0)
    $fatal(1,"Serialized/reference mismatch sample=%0d cal=%b/%b gates=%h/%h floor=%h/%h on=%h/%h off=%h/%h count=%0d/%0d windows=%0d/%0d frames=%0d/%0d",
      sample_number,calibrated,reference_calibrated,gates,reference_gates,noise_floor,reference_noise_floor,
      on_levels,reference_on_levels,off_levels,reference_off_levels,trigger_count,reference_trigger_count,
      calibration_windows_done,reference_calibration_windows_done,serial_frames,reference_frames);
   if(!sample_ready)$fatal(1,"Serialized engine missed its sample budget");
  end
 endtask
 task sample;
  begin
   @(negedge clk);sample_valid=1;
   @(negedge clk);sample_valid=0;
   repeat(38)@(negedge clk);
   compare;
  end
 endtask
 initial begin
  repeat(4)@(negedge clk);reset=0;
  for(sample_number=0;sample_number<3200;sample_number=sample_number+1)begin
   random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
   if(sample_number==20)enable=1;
   if(sample_number>100 && sample_number%80==0)blocked=random_state[4:0];
   if(sample_number==800 || sample_number==1800)enable=0;
   if(sample_number==830 || sample_number==1830)begin enable=1;blocked=0;end
   if(sample_number==1200)online=0;
   if(sample_number==1210)begin online=1;blocked=0;end
   if(sample_number==2000 || sample_number==2600)begin
    recalibrate=1;blocked=0;on_threshold=sample_number==2000 ? 900 : 64;
    off_threshold=sample_number==2000 ? 800 : 32;
   end else recalibrate=0;
   for(channel=0;channel<5;channel=channel+1)
    samples[channel*16+:16]=sample_number[0] ? 16'h8000 :
      (blocked[channel] ? 16'h8000 : channel==4 ? 16'h8040 : 16'h8000+(channel+1)*1000);
   if(sample_number>=2800)begin
    for(channel=0;channel<5;channel=channel+1)
     samples[channel*16+:16]=sample_number[0] ? 16'h8000 : 16'h7fff;
   end
   sample;
  end
  if(trigger_count==0 || trigger_count!==reference_trigger_count)$fatal(1,"Equivalence did not exercise carrier triggers");
  @(negedge clk);sample_valid=1;
  @(negedge clk);sample_valid=0;
  repeat(5)@(negedge clk);sample_valid=1;
  @(negedge clk);sample_valid=0;
  repeat(40)@(negedge clk);
  if(overruns!=1 || calibrated || gates!=0 || !sample_ready)$fatal(1,"Collision did not fail closed");
  $display("PASS tb_pluck_carrier_engine %0d settled-cycle equivalence checks, shared RAM arithmetic, trigger/rearm, weak/reference, full signed span, reset and collision",checks);
  $finish;
 end
 initial begin #10000000;$fatal(1,"Carrier engine test timeout");end
endmodule
