`timescale 1ns/1ps
`default_nettype none
module midi_pluck_carrier_engine #(
 parameter integer WINDOW_SAMPLES=50,
 parameter integer CALIBRATION_WINDOWS=500,
 parameter integer HOLD_WINDOWS=25,
 parameter integer QUIET_WINDOWS=5,
 parameter integer DISPLAY_WINDOWS=100,
 parameter integer SETTLE_WINDOWS=50,
 parameter integer TRIGGER_WINDOWS=2,
 parameter integer STABLE_INPUT=0
)(
 input wire clk,reset,online,enable,recalibrate,sample_valid,
 input wire [79:0] samples,
 input wire [15:0] on_threshold,off_threshold,
 output reg calibrated,frame_valid,
 output wire sample_ready,
 output reg [4:0] gates,
 output reg [79:0] amplitudes,trigger_counts,noise_floor,on_levels,off_levels,current_vpp,
 output wire [4:0] valid_channels,
 output wire [15:0] calibration_windows_done,
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
 localparam integer HOLD_BITS=width_for(HOLD_WINDOWS);
 localparam integer QUIET_BITS=width_for(QUIET_WINDOWS-1);
 localparam integer BLOCKED_BITS=width_for(TRIGGER_WINDOWS-1);
 localparam integer DISPLAY_BITS=width_for(DISPLAY_WINDOWS-1);
 localparam integer QUIET_OFFSET=HOLD_BITS;
 localparam integer BLOCKED_OFFSET=QUIET_OFFSET+QUIET_BITS;
 localparam integer DISPLAY_OFFSET=BLOCKED_OFFSET+BLOCKED_BITS;
 localparam integer ARMED_OFFSET=DISPLAY_OFFSET+DISPLAY_BITS;
 localparam integer STATE_BITS=ARMED_OFFSET>16 ? ARMED_OFFSET : 16;
 (* syn_ramstyle="block_ram" *) reg [STATE_BITS-1:0] state_memory [0:31];
 reg [STATE_BITS-1:0] read_state;
 reg [79:0] captured;
 reg signed [15:0] minimum,maximum;
 reg [15:0] next_maximum,span,selected_floor,selected_on,selected_off;
 reg [2:0] channel_index,phase;
 reg processing,first_sample,last_sample,previous_enable;
 reg [width_for(WINDOW_SAMPLES-1)-1:0] sample_index;
 reg [width_for(CALIBRATION_WINDOWS-1)-1:0] calibration_index;
 reg [width_for(SETTLE_WINDOWS)-1:0] settle_remaining;
 reg [4:0] arm_valid,display_valid,threshold_valid,armed_channels;
 wire restart_window=recalibrate || enable!=previous_enable;
 wire collision=sample_valid && processing;
 wire abort_frame=!online || restart_window || collision;
 wire write_state=processing && !reset && !abort_frame;
 wire [79:0] frame_samples=STABLE_INPUT ? samples : captured;
 wire signed [15:0] raw_value=frame_samples[channel_index*16+:16];
 wire signed [15:0] low_value=first_sample || raw_value<minimum ? raw_value : minimum;
 wire signed [15:0] high_value=first_sample || raw_value>maximum ? raw_value : maximum;
 wire [HOLD_BITS-1:0] hold_count=arm_valid[channel_index] ? read_state[0+:HOLD_BITS] : 0;
 wire [QUIET_BITS-1:0] quiet_count=arm_valid[channel_index] ? read_state[QUIET_OFFSET+:QUIET_BITS] : 0;
 wire [BLOCKED_BITS-1:0] blocked_count=arm_valid[channel_index] ? read_state[BLOCKED_OFFSET+:BLOCKED_BITS] : 0;
 wire [DISPLAY_BITS-1:0] display_count=display_valid[channel_index] ? read_state[DISPLAY_OFFSET+:DISPLAY_BITS] : 0;
 wire armed=arm_valid[channel_index] && armed_channels[channel_index];
 wire [15:0] floor_value=noise_floor[channel_index*16+:16];
 wire [15:0] display_vpp=amplitudes[channel_index*16+:16];
 wire [15:0] channel_triggers=trigger_counts[channel_index*16+:16];
 wire [15:0] next_floor=!enable ? 16'd0 : !calibrated && settle_remaining==0 &&
                         (calibration_index==0 || span<floor_value) ? span : floor_value;
 wire [15:0] relative_on=(selected_floor>>1)+{15'd0,selected_floor[0]};
 wire [15:0] relative_off=(selected_floor>>2)+{15'd0,(|selected_floor[1:0])};
 wire [15:0] on_drop=on_threshold>relative_on ? on_threshold : relative_on;
 wire [15:0] off_drop=off_threshold>relative_off ? off_threshold : relative_off;
 wire [16:0] on_difference={1'b0,selected_floor}-{1'b0,on_drop};
 wire [16:0] off_difference={1'b0,selected_floor}-{1'b0,off_drop};
 wire [15:0] on_limit=on_difference[16] ? 16'd0 : on_difference[15:0];
 wire [15:0] off_limit=off_difference[16] ? 16'd0 : off_difference[15:0];
 wire valid_thresholds=on_threshold>off_threshold &&
                       {1'b0,selected_floor}>{on_threshold,1'b0} && selected_on<selected_off;
 wire triggered=enable && calibrated && armed && valid_thresholds &&
                span<=selected_on && blocked_count==TRIGGER_WINDOWS-1;
 reg [HOLD_BITS-1:0] next_hold;
 reg [QUIET_BITS-1:0] next_quiet;
 reg [BLOCKED_BITS-1:0] next_blocked;
 reg [DISPLAY_BITS-1:0] next_display;
 reg next_armed,next_gate;
 wire [STATE_BITS-1:0] metadata={next_display,next_blocked,next_quiet,next_hold};
 wire [4:0] read_address={channel_index,phase==0 ? 2'd0 : phase==1 ? 2'd1 : 2'd2};
 wire [4:0] write_address={channel_index,phase==3 ? 2'd0 : phase==4 ? 2'd1 : 2'd2};
 wire [STATE_BITS-1:0] write_value=phase==3 ? {{(STATE_BITS-16){1'b0}},low_value} :
                                   phase==4 ? {{(STATE_BITS-16){1'b0}},next_maximum} : metadata;
 assign sample_ready=!processing;
 assign valid_channels=threshold_valid & {5{calibrated}};
 assign calibration_windows_done=calibrated ? CALIBRATION_WINDOWS : calibration_index;
 always @(posedge clk)begin
  if(processing && phase<3)read_state<=state_memory[read_address];
  if(write_state && (phase==3 || phase==4 || phase==6))state_memory[write_address]<=write_value;
 end
 always @* begin
  next_hold=hold_count;next_quiet=quiet_count;next_blocked=blocked_count;
  next_armed=armed;next_gate=gates[channel_index];next_display=display_count;
  if(last_sample)begin
   next_display=span>=display_vpp || display_count==0 ? DISPLAY_WINDOWS-1 : display_count-1'b1;
   if(!enable || !calibrated)begin
    next_hold=0;next_quiet=0;next_blocked=0;next_armed=0;next_gate=0;
   end else begin
    if(hold_count!=0)begin next_hold=hold_count-1'b1;if(hold_count==1)next_gate=0;end
    if(triggered)begin
     next_gate=1;next_hold=HOLD_WINDOWS;next_armed=0;next_quiet=0;next_blocked=0;
    end else if(!armed)begin
     next_blocked=0;
     if(valid_thresholds && hold_count==0 && span>=selected_off)begin
      if(quiet_count==QUIET_WINDOWS-1)begin next_armed=1;next_quiet=0;end
      else next_quiet=quiet_count+1'b1;
     end else next_quiet=0;
    end else next_blocked=span<=selected_on && valid_thresholds ? blocked_count+1'b1 : 0;
   end
  end
  if(!enable)begin next_hold=0;next_quiet=0;next_blocked=0;next_armed=0;next_gate=0;end
 end
 always @(posedge clk)begin
  if(reset)begin
   calibrated<=0;frame_valid<=0;gates<=0;amplitudes<=0;trigger_counts<=0;noise_floor<=0;
   on_levels<=0;off_levels<=0;current_vpp<=0;trigger_count<=0;overruns<=0;
   processing<=0;phase<=0;channel_index<=0;sample_index<=0;calibration_index<=0;
   settle_remaining<=SETTLE_WINDOWS;previous_enable<=0;arm_valid<=0;display_valid<=0;threshold_valid<=0;armed_channels<=0;
   first_sample<=0;last_sample<=0;minimum<=0;maximum<=0;next_maximum<=0;span<=0;
   selected_floor<=0;selected_on<=0;selected_off<=0;
  end else begin
   previous_enable<=enable;frame_valid<=0;
   if(abort_frame)begin
    processing<=0;phase<=0;sample_index<=0;calibration_index<=0;calibrated<=0;
    settle_remaining<=SETTLE_WINDOWS;gates<=0;arm_valid<=0;noise_floor<=0;threshold_valid<=0;
    on_levels<=0;off_levels<=0;
    if(!online || collision)begin amplitudes<=0;current_vpp<=0;display_valid<=0;end
    if(online && collision && overruns!=16'hffff)overruns<=overruns+1'b1;
   end else begin
    if(!enable)begin
     calibrated<=0;calibration_index<=0;settle_remaining<=SETTLE_WINDOWS;
     gates<=0;arm_valid<=0;noise_floor<=0;threshold_valid<=0;on_levels<=0;off_levels<=0;
    end
    if(sample_valid)begin
     captured<=samples;processing<=1;phase<=0;channel_index<=0;
     first_sample<=sample_index==0;last_sample<=sample_index==WINDOW_SAMPLES-1;
     sample_index<=sample_index==WINDOW_SAMPLES-1 ? 0 : sample_index+1'b1;
    end else if(processing)begin
     if(phase==1)minimum<=read_state[15:0];
     if(phase==2)maximum<=read_state[15:0];
     if(phase==3)begin span<=high_value-low_value;next_maximum<=high_value;end
     if(phase==4)selected_floor<=next_floor;
     if(phase==5)begin selected_on<=on_limit;selected_off<=off_limit;end
     if(phase==6)begin
      arm_valid[channel_index]<=enable;
      armed_channels[channel_index]<=next_armed;
      gates[channel_index]<=next_gate;
      if(last_sample)begin
       current_vpp[channel_index*16+:16]<=span;
       display_valid[channel_index]<=1;
       if(span>=display_vpp || display_count==0)amplitudes[channel_index*16+:16]<=span;
       noise_floor[channel_index*16+:16]<=selected_floor;
       on_levels[channel_index*16+:16]<=selected_on;off_levels[channel_index*16+:16]<=selected_off;
       threshold_valid[channel_index]<=valid_thresholds && enable;
       if(triggered)begin
        trigger_count<=trigger_count+1'b1;
        if(channel_triggers!=16'hffff)trigger_counts[channel_index*16+:16]<=channel_triggers+1'b1;
       end
      end
      phase<=0;
      if(channel_index==4)begin
       processing<=0;frame_valid<=last_sample;
       if(last_sample && enable && !calibrated)begin
        if(settle_remaining!=0)settle_remaining<=settle_remaining-1'b1;
        else if(calibration_index==CALIBRATION_WINDOWS-1)calibrated<=1;
        else calibration_index<=calibration_index+1'b1;
       end
      end else channel_index<=channel_index+1'b1;
     end else phase<=phase+1'b1;
    end
   end
  end
 end
`ifndef SYNTHESIS
 initial if(WINDOW_SAMPLES<2 || CALIBRATION_WINDOWS<1 || CALIBRATION_WINDOWS>65535 || HOLD_WINDOWS<1 ||
            QUIET_WINDOWS<1 || DISPLAY_WINDOWS<1 || SETTLE_WINDOWS<0 || TRIGGER_WINDOWS<1)
  $fatal(1,"Invalid serialized carrier parameters");
`endif
endmodule
`default_nettype wire
