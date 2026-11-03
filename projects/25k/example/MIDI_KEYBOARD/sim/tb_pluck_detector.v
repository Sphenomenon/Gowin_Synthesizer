`timescale 1ns/1ps
module tb_pluck_detector;
 reg clk=0;
 always #5 clk=!clk;
 reg reset=1,online=0,valid=0;
 reg [79:0] samples=0;
 wire calibrated;
 wire [4:0] gates;
 wire [79:0] amplitudes,counts;
 wire [31:0] total;
 wire [15:0] overruns;
 wire compact_calibrated,full_frame,compact_frame,full_ready,compact_ready;
 wire [4:0] compact_gates;
 wire [31:0] compact_total;
 wire [15:0] compact_overruns;
 wire [79:0] compact_amplitudes,compact_counts;
 midi_pluck_detector #(.CALIBRATION_SAMPLES(4),.HOLD_SAMPLES(3),.QUIET_SAMPLES(2)) dut(
  .clk(clk),.reset(reset),.online(online),.sample_valid(valid),.samples(samples),
  .calibrated(calibrated),.frame_valid(full_frame),.sample_ready(full_ready),.gates(gates),.amplitudes(amplitudes),.trigger_counts(counts),.trigger_count(total),.overruns(overruns));
 midi_pluck_detector #(.CALIBRATION_SAMPLES(4),.HOLD_SAMPLES(3),.QUIET_SAMPLES(2),.DIAGNOSTIC_DETAILS(0)) compact_dut(
  .clk(clk),.reset(reset),.online(online),.sample_valid(valid),.samples(samples),
  .calibrated(compact_calibrated),.frame_valid(compact_frame),.sample_ready(compact_ready),
  .gates(compact_gates),.amplitudes(compact_amplitudes),.trigger_counts(compact_counts),
  .trigger_count(compact_total),.overruns(compact_overruns));
 always @(posedge clk)begin
  #1;
  if({compact_calibrated,compact_frame,compact_ready,compact_gates,compact_total,compact_overruns}
     !=={calibrated,full_frame,full_ready,gates,total,overruns} || compact_amplitudes!==0 || compact_counts!==0)
   $fatal(1,"compact diagnostics changed acquisition or trigger behavior");
 end
 task sample;
  input [79:0] data;
  begin
   @(negedge clk);samples=data;valid=1;
   @(negedge clk);valid=0;samples=~data;repeat(12)@(negedge clk);
  end
 endtask
 initial begin
  #100000;$fatal(1,"detector test timeout");
 end
 initial begin
  repeat(3)@(negedge clk);reset=0;online=1;
  repeat(4)sample(0);
  if(!calibrated || gates!=0 || total!=0)$fatal(1,"calibration emitted notes");
  sample({48'd0,16'hf830,16'd1500});
  if(gates!=3 || total!=2 || amplitudes[31:16]!=2000 || counts[31:0]!=32'h00010001)
   $fatal(1,"signed simultaneous triggers lost");
  repeat(10)sample({48'd0,16'hf830,16'd1500});
  if(gates!=0 || total!=2)$fatal(1,"sustained signal retriggered or stuck note");
  repeat(2)sample(0);
  sample({48'd0,16'h8000,16'd1600});
  if(gates!=3 || total!=4 || amplitudes[31:16]!=32768)$fatal(1,"rearm or negative full scale failed");
  @(negedge clk);online=0;
  @(negedge clk);
  if(gates!=0 || calibrated || total!=4)$fatal(1,"acquisition fault did not release notes/preserve counts");
  online=1;
  repeat(4)sample(80'h10001000100010001000);
  if(gates!=0 || !calibrated || total!=4)$fatal(1,"DC baseline must not generate startup notes");
  @(negedge clk);valid=1;
  @(negedge clk);valid=0;
  @(negedge clk);valid=1;
  @(negedge clk);valid=0;
  repeat(8)@(negedge clk);
  if(overruns!=1 || calibrated || gates!=0)$fatal(1,"overlapping sample must fail closed and report overrun");
  $display("PASS tb_pluck_detector calibration, signed magnitude, simultaneous triggers, hold, rearm and loss");$finish;
 end
endmodule
