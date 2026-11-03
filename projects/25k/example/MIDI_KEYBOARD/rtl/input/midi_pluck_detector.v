`timescale 1ns/1ps
`default_nettype none
module midi_pluck_detector #(
 parameter integer SAMPLE_HZ=4000,
 parameter integer CALIBRATION_SAMPLES=64,
 parameter integer ON_THRESHOLD=1024,
 parameter integer OFF_THRESHOLD=512,
 parameter integer DIAGNOSTIC_DETAILS=1,
 parameter integer HOLD_SAMPLES=SAMPLE_HZ/20,
 parameter integer QUIET_SAMPLES=SAMPLE_HZ/100
)(
 input wire clk,reset,online,sample_valid,
 input wire [79:0] samples,
 output reg calibrated,frame_valid,
 output wire sample_ready,
 output reg [4:0] gates,
 output wire [79:0] amplitudes,
 output wire [79:0] trigger_counts,
 output reg [31:0] trigger_count,
 output reg [15:0] overruns
);
 function integer width_for;
  input integer maximum;
  integer remaining;
  begin
   remaining=maximum;width_for=0;
   while(remaining>0)begin width_for=width_for+1;remaining=remaining>>1;end
   if(width_for<1)width_for=1;
  end
 endfunction
 localparam integer HOLD_BITS=width_for(HOLD_SAMPLES);
 localparam integer QUIET_BITS=width_for(QUIET_SAMPLES);
 localparam integer STATE_BITS=24+HOLD_BITS;
 (* syn_ramstyle="block_ram" *) reg [STATE_BITS-1:0] channel_state[0:7];
 reg [STATE_BITS-1:0] read_state;
 reg [STATE_BITS-1:0] write_state;
 reg [QUIET_BITS-1:0] quiet[0:4];
 reg [4:0] armed;
 reg [width_for(CALIBRATION_SAMPLES)-1:0] calibration_count;
 reg processing,read_phase;
 reg [2:0] channel_index;
 reg [79:0] captured;
 reg next_gate,next_armed,triggered;
 reg [QUIET_BITS-1:0] next_quiet;
 wire signed [15:0] raw_value=captured[channel_index*16+:16];
 wire signed [23:0] baseline=read_state[23:0];
 wire [HOLD_BITS-1:0] hold_count=read_state[24+:HOLD_BITS];
 wire [QUIET_BITS-1:0] quiet_count=quiet[channel_index];
 wire channel_armed=armed[channel_index];
 wire signed [16:0] deviation={raw_value[15],raw_value}-{baseline[23],baseline[23:8]};
 wire [15:0] magnitude=deviation[16] ? -deviation : deviation;
 wire signed [24:0] baseline_difference={raw_value[15],raw_value,8'd0}-{baseline[23],baseline};
 wire signed [24:0] baseline_step=calibrated ? baseline_difference>>>10 : baseline_difference>>>4;
 wire state_write=processing && read_phase && online && !sample_valid && !reset;
 wire [2:0] read_address=processing && read_phase && channel_index!=4 ? channel_index+1'b1 : channel_index;
 integer reset_index;
 assign sample_ready=!processing;
 always @(posedge clk)begin
  if(!reset && online && sample_valid && !processing)captured<=samples;
 end
 always @(posedge clk)begin
  if(state_write)channel_state[channel_index]<=write_state;
  read_state<=channel_state[read_address];
 end
 always @* begin
  write_state=read_state;next_gate=gates[channel_index];triggered=0;
  next_quiet=quiet_count;next_armed=channel_armed;
  if(!calibrated)begin
   write_state[23:0]=calibration_count==0 ? {raw_value,8'd0} : baseline+baseline_step;
   write_state[24+:HOLD_BITS]=0;next_quiet=0;
   next_armed=calibration_count==CALIBRATION_SAMPLES-1;
   next_gate=0;
  end else begin
   if(hold_count!=0)begin
    write_state[24+:HOLD_BITS]=hold_count-1'b1;
    if(hold_count==1)next_gate=0;
   end
   if(!channel_armed)begin
    if(hold_count==0 && magnitude<=OFF_THRESHOLD)begin
     if(quiet_count==QUIET_SAMPLES-1)begin next_armed=1;next_quiet=0;end
     else next_quiet=quiet_count+1'b1;
    end else next_quiet=0;
   end else if(magnitude>=ON_THRESHOLD)begin
    next_gate=1;write_state[24+:HOLD_BITS]=HOLD_SAMPLES;next_armed=0;triggered=1;
   end else if(magnitude<=OFF_THRESHOLD)write_state[23:0]=baseline+baseline_step;
  end
 end
 generate if(DIAGNOSTIC_DETAILS)begin:detail
  reg [79:0] amplitude_state,count_state;
  wire [15:0] channel_triggers=count_state[channel_index*16+:16];
  assign amplitudes=amplitude_state;
  assign trigger_counts=count_state;
  always @(posedge clk)begin
   if(reset)begin amplitude_state<=0;count_state<=0;end
   else if(!online || (sample_valid && processing))amplitude_state<=0;
   else if(processing && read_phase && !sample_valid)begin
    amplitude_state[channel_index*16+:16]<=magnitude;
    if(triggered && channel_triggers!=16'hffff)
     count_state[channel_index*16+:16]<=channel_triggers+1'b1;
   end
  end
 end else begin:compact
  assign amplitudes=80'd0;
  assign trigger_counts=80'd0;
 end endgenerate
`ifndef SYNTHESIS
 initial begin
  if(CALIBRATION_SAMPLES<1 || HOLD_SAMPLES<1 || QUIET_SAMPLES<1 ||
     OFF_THRESHOLD<0 || OFF_THRESHOLD>=ON_THRESHOLD || ON_THRESHOLD>65535)
   $fatal(1,"Invalid pluck detector timing/threshold parameters");
 end
`endif
 always @(posedge clk)begin
  if(reset)begin
   calibrated<=0;frame_valid<=0;gates<=0;calibration_count<=0;armed<=0;
   trigger_count<=0;overruns<=0;
   processing<=0;read_phase<=0;channel_index<=0;
   for(reset_index=0;reset_index<5;reset_index=reset_index+1)quiet[reset_index]<=0;
  end else begin
   frame_valid<=0;
   if(!online || (sample_valid && processing))begin
    calibrated<=0;gates<=0;calibration_count<=0;processing<=0;read_phase<=0;armed<=0;
    for(reset_index=0;reset_index<5;reset_index=reset_index+1)quiet[reset_index]<=0;
    if(online && sample_valid && processing && overruns!=16'hffff)overruns<=overruns+1'b1;
   end else if(sample_valid)begin channel_index<=0;processing<=1;read_phase<=0;end
   else if(processing)begin
    if(!read_phase)read_phase<=1;
    else begin
     read_phase<=0;quiet[channel_index]<=next_quiet;armed[channel_index]<=next_armed;
     gates[channel_index]<=next_gate;
     if(triggered)begin
      trigger_count<=trigger_count+1'b1;
     end
     if(channel_index==4)begin
      processing<=0;frame_valid<=1;
      if(!calibrated)begin
       calibration_count<=calibration_count+1'b1;
       if(calibration_count==CALIBRATION_SAMPLES-1)calibrated<=1;
      end
     end else channel_index<=channel_index+1'b1;
    end
   end
  end
 end
endmodule
`default_nettype wire
