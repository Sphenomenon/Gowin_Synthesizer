`timescale 1ns/1ps
`default_nettype none
module midi_pluck_vpp_detector #(
 parameter integer WINDOW_SAMPLES=250,
 parameter integer CALIBRATION_WINDOWS=16,
 parameter integer HOLD_WINDOWS=5,
 parameter integer QUIET_WINDOWS=1,
 parameter integer DISPLAY_WINDOWS=20,
 parameter integer ADAPTIVE_NOISE=0,
 parameter integer CARRIER_MODE=0,
 parameter integer SETTLE_WINDOWS=10,
 parameter integer TRIGGER_WINDOWS=2
)(
 input wire clk,reset,online,enable,recalibrate,sample_valid,
 input wire [79:0] samples,
 input wire [15:0] on_threshold,off_threshold,
 output reg calibrated,frame_valid,
 output wire sample_ready,
 output wire [4:0] gates,
 output wire [79:0] amplitudes,trigger_counts,
 output wire [79:0] noise_floor,on_levels,off_levels,current_vpp,
 output wire [4:0] valid_channels,
 output wire [15:0] calibration_windows_done,
 output reg [31:0] trigger_count,
 output wire [15:0] overruns
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
 reg [width_for(WINDOW_SAMPLES-1)-1:0] sample_index;
 reg [width_for(CALIBRATION_WINDOWS-1)-1:0] calibration_index;
 reg [width_for(SETTLE_WINDOWS)-1:0] settle_remaining;
 reg previous_enable;
 wire restart_window=CARRIER_MODE && (recalibrate || enable!=previous_enable);
 wire window_end=online && sample_valid && !restart_window && sample_index==WINDOW_SAMPLES-1;
 wire [4:0] triggers;
 wire [2:0] trigger_increment={2'd0,triggers[0]}+{2'd0,triggers[1]}+
                              {2'd0,triggers[2]}+{2'd0,triggers[3]}+{2'd0,triggers[4]};
 assign sample_ready=1'b1;
 assign overruns=16'd0;
 localparam [15:0] CALIBRATION_LENGTH=CALIBRATION_WINDOWS;
 assign calibration_windows_done=calibrated ? CALIBRATION_LENGTH : calibration_index;
 always @(posedge clk)begin
  if(reset)begin
   sample_index<=0;calibration_index<=0;calibrated<=0;frame_valid<=0;trigger_count<=0;
   settle_remaining<=CARRIER_MODE ? SETTLE_WINDOWS : 0;
   previous_enable<=0;
  end else begin
   previous_enable<=enable;
   frame_valid<=window_end;
   if(!online || restart_window)sample_index<=0;
   else if(sample_valid)sample_index<=window_end ? 0 : sample_index+1'b1;
   if(!online || !enable || recalibrate)begin
    calibration_index<=0;calibrated<=0;settle_remaining<=CARRIER_MODE ? SETTLE_WINDOWS : 0;
   end
   else if(window_end && !calibrated)begin
    if(settle_remaining!=0)settle_remaining<=settle_remaining-1'b1;
    else if(calibration_index==CALIBRATION_WINDOWS-1)calibrated<=1;
    else calibration_index<=calibration_index+1'b1;
   end
   if(trigger_increment!=0)trigger_count<=trigger_count+trigger_increment;
  end
 end
 genvar channel;
 generate for(channel=0;channel<5;channel=channel+1)begin:channels
  reg signed [15:0] minimum,maximum;
  wire signed [15:0] raw_value=samples[channel*16+:16];
  wire signed [15:0] next_minimum=sample_index==0 || raw_value<minimum ? raw_value : minimum;
  wire signed [15:0] next_maximum=sample_index==0 || raw_value>maximum ? raw_value : maximum;
  wire [15:0] span=next_maximum-next_minimum;
  reg [15:0] display_vpp,channel_triggers;
  reg [15:0] calibration_peak,window_vpp;
  wire [15:0] floor_value=ADAPTIVE_NOISE || CARRIER_MODE ? calibration_peak : 16'd0;
  wire [15:0] relative_on=(floor_value>>1)+{15'd0,floor_value[0]};
  wire [15:0] relative_off=(floor_value>>2)+{15'd0,(|floor_value[1:0])};
  wire [15:0] on_drop=on_threshold>relative_on ? on_threshold : relative_on;
  wire [15:0] off_drop=off_threshold>relative_off ? off_threshold : relative_off;
  wire [16:0] on_sum={1'b0,floor_value}+{1'b0,on_threshold};
  wire [16:0] off_sum={1'b0,floor_value}+{1'b0,off_threshold};
  wire [15:0] on_limit=CARRIER_MODE ? (floor_value>on_drop ? floor_value-on_drop : 16'd0) :
                       (on_sum[16] ? 16'hffff : on_sum[15:0]);
  wire [15:0] off_limit=CARRIER_MODE ? (floor_value>off_drop ? floor_value-off_drop : 16'd0) :
                        (off_sum[16] ? 16'hffff : off_sum[15:0]);
  wire valid_thresholds=on_threshold>off_threshold && (CARRIER_MODE ?
                       ({1'b0,floor_value}>{on_threshold,1'b0} && on_limit<off_limit) : !on_sum[16]);
  reg [width_for(DISPLAY_WINDOWS-1)-1:0] display_remaining;
  reg [width_for(HOLD_WINDOWS)-1:0] hold_remaining;
  reg [width_for(QUIET_WINDOWS-1)-1:0] quiet_count;
  reg [width_for(TRIGGER_WINDOWS-1)-1:0] blocked_count;
  reg gate,armed;
  wire active_span=CARRIER_MODE ? span<=on_limit : span>=on_limit;
  wire released_span=CARRIER_MODE ? span>=off_limit : span<=off_limit;
  assign gates[channel]=gate;
  assign amplitudes[channel*16+:16]=display_vpp;
  assign trigger_counts[channel*16+:16]=channel_triggers;
  assign noise_floor[channel*16+:16]=floor_value;
  assign on_levels[channel*16+:16]=on_limit;
  assign off_levels[channel*16+:16]=off_limit;
  assign current_vpp[channel*16+:16]=window_vpp;
  assign valid_channels[channel]=calibrated && valid_thresholds;
  assign triggers[channel]=!reset && window_end && calibrated && valid_thresholds && enable && !recalibrate && armed && active_span &&
                           (!CARRIER_MODE || blocked_count==TRIGGER_WINDOWS-1);
  always @(posedge clk)begin
   if(reset)begin
    minimum<=0;maximum<=0;display_vpp<=0;display_remaining<=0;
    calibration_peak<=0;window_vpp<=0;
    channel_triggers<=0;hold_remaining<=0;quiet_count<=0;blocked_count<=0;gate<=0;armed<=0;
   end else begin
    if(!online)begin minimum<=0;maximum<=0;display_vpp<=0;display_remaining<=0;window_vpp<=0;end
    else if(sample_valid)begin
     minimum<=next_minimum;maximum<=next_maximum;
     if(window_end)begin
      window_vpp<=span;
      if(span>=display_vpp || display_remaining==0)begin
       display_vpp<=span;display_remaining<=DISPLAY_WINDOWS-1;
      end else display_remaining<=display_remaining-1'b1;
     end
    end
    if(!online || !enable || recalibrate)begin
     hold_remaining<=0;quiet_count<=0;blocked_count<=0;gate<=0;armed<=0;calibration_peak<=0;
    end
    else if(window_end)begin
     if(!calibrated)begin
      hold_remaining<=0;quiet_count<=0;gate<=0;
      if(CARRIER_MODE)begin
       if(settle_remaining==0 && (calibration_index==0 || span<calibration_peak))calibration_peak<=span;
       armed<=0;blocked_count<=0;
      end else begin
       if(ADAPTIVE_NOISE && span>calibration_peak)calibration_peak<=span;
       armed<=calibration_index==CALIBRATION_WINDOWS-1 && (ADAPTIVE_NOISE || span<=off_threshold);
      end
     end else begin
      if(hold_remaining!=0)begin
       hold_remaining<=hold_remaining-1'b1;
       if(hold_remaining==1)gate<=0;
      end
      if(triggers[channel])begin
       gate<=1;hold_remaining<=HOLD_WINDOWS;armed<=0;quiet_count<=0;blocked_count<=0;
       if(channel_triggers!=16'hffff)channel_triggers<=channel_triggers+1'b1;
      end else if(!armed)begin
       blocked_count<=0;
       if(valid_thresholds && hold_remaining==0 && released_span)begin
        if(quiet_count==QUIET_WINDOWS-1)begin armed<=1;quiet_count<=0;end
        else quiet_count<=quiet_count+1'b1;
       end else quiet_count<=0;
      end else if(CARRIER_MODE)begin
       if(active_span && valid_thresholds)blocked_count<=blocked_count+1'b1;
       else blocked_count<=0;
      end
     end
    end
   end
  end
 end endgenerate
`ifndef SYNTHESIS
 initial begin
  if(WINDOW_SAMPLES<2 || CALIBRATION_WINDOWS<1 || CALIBRATION_WINDOWS>65535 || HOLD_WINDOWS<1 || QUIET_WINDOWS<1 || DISPLAY_WINDOWS<1 || SETTLE_WINDOWS<0 || TRIGGER_WINDOWS<1 || (CARRIER_MODE && ADAPTIVE_NOISE))
   $fatal(1,"Invalid peak-to-peak detector window parameters");
 end
`endif
endmodule
`default_nettype wire
