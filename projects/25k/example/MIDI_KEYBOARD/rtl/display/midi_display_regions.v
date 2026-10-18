`timescale 1ns/1ps
// Compare complete scenes only at the same snapshot edge as the renderer.
// The scanner consumes this mask before requesting another snapshot.
// Region 0 supersedes every partial region when a full repaint is required.
module midi_display_regions (
 input wire clk, reset, snapshot,
 input wire [15:0] key_bitmap,
 input wire [3:0] midi_channel,
 input wire signed [7:0] transpose,
 input wire [6:0] velocity, program_number,
 input wire [1:0] slider_mode,
 input wire [7:0] brightness, strip_value,
 input wire [2:0] focus,
 input wire usb_online, ble_online, touch_ready, panic_busy,
 input wire slider_ready, slider_touched, slider_overrun,
 input wire [7:0] slider_raw_position, slider_filtered_position,
 input wire [7:0] slider_error, slider_general_status, slider_sample_count,
 input wire [15:0] theme_rgb565, clear_rgb565,
 output reg [26:0] dirty_regions
);
 reg have_snapshot;
 reg [15:0] last_keys;
 reg [3:0] last_channel;
 reg signed [7:0] last_transpose;
 reg [6:0] last_velocity,last_program;
 reg [1:0] last_mode;
 reg [7:0] last_brightness,last_strip;
 reg [2:0] last_focus;
 reg last_usb,last_ble,last_touch,last_panic;
 reg last_slider_ready,last_slider_touched,last_slider_overrun;
 reg [7:0] last_slider_raw,last_slider_filtered;
 reg [7:0] last_slider_error,last_slider_general,last_slider_count;
 reg [15:0] last_theme,last_clear;
 reg [26:0] changed;
 integer i;

 always @* begin
  changed=27'd0;
  if(!have_snapshot || theme_rgb565!=last_theme || clear_rgb565!=last_clear)
   changed[0]=1'b1;
  else begin
   // 1: header x168..369, y7..13.
   changed[1]=(usb_online!=last_usb || ble_online!=last_ble ||
               touch_ready!=last_touch || panic_busy!=last_panic);
   // 2..7: six cards x8/70/132/194/256/318 .. +57, y29..71.
   changed[2]=(transpose!=last_transpose);
   changed[3]=(midi_channel!=last_channel);
   changed[4]=(velocity!=last_velocity);
   changed[5]=(slider_mode!=last_mode);
   changed[6]=(program_number!=last_program);
   changed[7]=(brightness!=last_brightness);
   if(focus!=last_focus) begin
    // Invalid focus values have no card; the sidebar is safe to repaint.
    for(i=0;i<6;i=i+1)
     if(focus==i || last_focus==i) changed[2+i]=1'b1;
   end
   // 8: S2 row x8..139, y74..80, including its ready/error color.
   changed[8]=(slider_ready!=last_slider_ready || slider_touched!=last_slider_touched ||
               slider_raw_position!=last_slider_raw || slider_filtered_position!=last_slider_filtered ||
               slider_error!=last_slider_error);
   // 9..24: key i at x8+23*i .. 27+23*i, y82..126.
   changed[24:9]=key_bitmap^last_keys;
   // 25: sidebar x384..419, y29..126.
   changed[25]=(slider_mode!=last_mode || strip_value!=last_strip || focus!=last_focus);
   // 26: diagnostic footer x208..297, y133..139, including status color.
   changed[26]=(slider_ready!=last_slider_ready || slider_error!=last_slider_error ||
                slider_overrun!=last_slider_overrun || slider_general_status!=last_slider_general ||
                slider_sample_count!=last_slider_count);
  end
 end

 always @(posedge clk) begin
  if(reset) begin
   have_snapshot<=1'b0;dirty_regions<=27'd0;
   last_keys<=0;last_channel<=0;last_transpose<=0;last_velocity<=0;last_program<=0;
   last_mode<=0;last_brightness<=0;last_strip<=0;last_focus<=0;
   last_usb<=0;last_ble<=0;last_touch<=0;last_panic<=0;
   last_slider_ready<=0;last_slider_touched<=0;last_slider_overrun<=0;
   last_slider_raw<=0;last_slider_filtered<=0;last_slider_error<=0;
   last_slider_general<=0;last_slider_count<=0;last_theme<=0;last_clear<=0;
  end else if(snapshot) begin
   have_snapshot<=1'b1;dirty_regions<=changed;
   last_keys<=key_bitmap;last_channel<=midi_channel;last_transpose<=transpose;
   last_velocity<=velocity;last_program<=program_number;last_mode<=slider_mode;
   last_brightness<=brightness;last_strip<=strip_value;last_focus<=focus;
   last_usb<=usb_online;last_ble<=ble_online;last_touch<=touch_ready;last_panic<=panic_busy;
   last_slider_ready<=slider_ready;last_slider_touched<=slider_touched;last_slider_overrun<=slider_overrun;
   last_slider_raw<=slider_raw_position;last_slider_filtered<=slider_filtered_position;
   last_slider_error<=slider_error;last_slider_general<=slider_general_status;last_slider_count<=slider_sample_count;
   last_theme<=theme_rgb565;last_clear<=clear_rgb565;
  end
 end
endmodule
