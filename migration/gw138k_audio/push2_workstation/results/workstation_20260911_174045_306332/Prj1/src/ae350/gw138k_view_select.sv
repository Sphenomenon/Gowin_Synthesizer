// Scanout registers frame_swap on the edge where it samples selected_base.
// Delay eligibility by that same cycle: a newly queued page must not steal an
// acknowledgement belonging to the preceding selection.
module gw138k_view_select (
 input wire clk,reset_n,frame_swap,analysis_pending,
 input wire ui_pending,ui_visible,ui_next_visible,
 input wire [28:0] ui_front_base,ui_next_base,
 output reg analysis_bank,
 output wire analysis_commit,ui_commit,frame_available,
 output wire composite,
 output wire [28:0] selected_analysis_base,
 output wire [28:0] selected_base
);
 reg analysis_valid,analysis_eligible,ui_eligible;
 assign analysis_commit=frame_swap && analysis_eligible;
 assign ui_commit=frame_swap && ui_eligible;
 // Unified HDMI page: the RTL analysis framebuffer is authoritative.
 // The former AUDIO LAB UI DDR page remains allocated for future shared-data
 // work, but it no longer covers the waveform/effect-chain display.
 wire selected_ui=1'b0;
 wire [28:0] analysis_base=(analysis_pending ? !analysis_bank : analysis_bank)?29'd1048576:29'd0;
 assign selected_analysis_base=analysis_base;
 assign composite=selected_ui && (analysis_valid || analysis_pending);
 assign selected_base=selected_ui?(ui_pending?ui_next_base:ui_front_base):analysis_base;
 assign frame_available=selected_ui || analysis_valid || analysis_pending;
 always @(posedge clk or negedge reset_n)
   if(!reset_n) begin analysis_bank<=0;analysis_valid<=0;analysis_eligible<=0;ui_eligible<=0;end
   else begin
     analysis_eligible<=analysis_pending;ui_eligible<=ui_pending;
     if(analysis_commit) begin analysis_bank<=!analysis_bank;analysis_valid<=1;end
   end
endmodule
