`timescale 1ns/1ps
`default_nettype none
// Source-stage partition seam; no physical LCD transport is selected here.
// One frame/request slot. Result release is always DEADLINE_CYCLES clocks
// after acceptance, including missing/failed W. A transport must prove its
// worst-case RTT before enabling this optional stage in an actual profile.
// All sideband ports are synchronous to clk_i; packet CRC/CDC live outside.
module workstation_remote_reverb_m #(
    parameter integer DEADLINE_CYCLES=512
) (
    input wire clk_i,rst_ni,clear_i,valid_i,enabled_i,
    input wire signed [31:0] left_i,right_i,
    output wire ready_o,active_o,
    output reg valid_o,
    output reg signed [31:0] left_o,right_o,
    output reg clip_o,
    input wire config_valid_i,rate_44100_i,history_clear_i,
    output wire config_ready_o,history_ready_o,quiescent_o,
    output reg config_applied_o,history_done_o,applied_rate_44100_o,
    input wire link_ready_i,
    input wire [31:0] link_session_i,
    output wire req_valid_o,
    input wire req_ready_i,
    output wire [31:0] req_session_o,req_generation_o,req_sequence_o,
    output wire req_rate_44100_o,req_enabled_o,req_reset_gain_o,
    output wire signed [31:0] req_left_o,req_right_o,
    input wire rsp_valid_i,
    output wire rsp_ready_o,
    input wire [31:0] rsp_session_i,rsp_generation_i,rsp_sequence_i,
    input wire rsp_rate_44100_i,rsp_active_i,rsp_clip_i,rsp_error_i,
    input wire signed [31:0] rsp_left_i,rsp_right_i,
    output reg [31:0] fallback_count_o,rejected_count_o
);
    localparam integer AGE_BITS=DEADLINE_CYCLES>1 ? $clog2(DEADLINE_CYCLES) : 1;
    reg busy,request_pending,request_sent,have_response,remote_active;
    reg response_clip,response_active;
    reg signed [31:0] dry_left,dry_right,response_left,response_right;
    reg [31:0] generation,sequence_number,frame_session,frame_generation,frame_sequence;
    reg frame_rate,frame_enabled,frame_reset_gain,generation_reset_gain;
    reg [AGE_BITS-1:0] age;
    reg previous_link,previous_clear;
    reg [31:0] previous_session;
    wire usable_link=link_ready_i && link_session_i!=0;
    wire link_changed=usable_link!=previous_link ||
        (usable_link && link_session_i!=previous_session);
    wire config_accept=config_valid_i && config_ready_o;
    wire history_accept=history_clear_i && history_ready_o;
    wire fence=(clear_i && !previous_clear) || config_accept || history_accept || link_changed;
    wire frame_live=busy && frame_session==link_session_i &&
        frame_generation==generation && usable_link && !fence && !clear_i;
    wire response_matches=frame_live && request_sent && !have_response &&
        rsp_session_i==frame_session && rsp_generation_i==frame_generation &&
        rsp_sequence_i==frame_sequence && rsp_rate_44100_i==frame_rate && !rsp_error_i;
    wire deadline=busy && age==AGE_BITS'(DEADLINE_CYCLES-1);
    assign ready_o=!busy && !valid_o && !clear_i && !config_valid_i && !history_clear_i;
    // Maintenance frames still run when disabled, draining the W wet slew.
    assign active_o=enabled_i || remote_active;
    assign quiescent_o=!busy && !valid_o && !clear_i;
    assign config_ready_o=quiescent_o && !valid_i;
    assign history_ready_o=config_ready_o && !config_valid_i;
    assign req_valid_o=request_pending && frame_live && !deadline;
    assign req_session_o=frame_session;
    assign req_generation_o=frame_generation;
    assign req_sequence_o=frame_sequence;
    assign req_rate_44100_o=frame_rate;
    assign req_enabled_o=frame_enabled;
    assign req_reset_gain_o=frame_reset_gain;
    assign req_left_o=dry_left;
    assign req_right_o=dry_right;
    // Drain stale frames as well; they never occupy the local sample slot.
    assign rsp_ready_o=1'b1;
    function automatic [31:0] next_generation(input [31:0] value);
        next_generation=value==32'hffff_ffff ? 32'd1 : value+1'b1;
    endfunction
    always @(posedge clk_i or negedge rst_ni)begin
        if(!rst_ni)begin
            busy<=0;request_pending<=0;request_sent<=0;have_response<=0;remote_active<=0;
            response_clip<=0;response_active<=0;dry_left<=0;dry_right<=0;response_left<=0;response_right<=0;
            generation<=1;sequence_number<=0;frame_session<=0;frame_generation<=0;frame_sequence<=0;
            frame_rate<=0;frame_enabled<=0;frame_reset_gain<=1;generation_reset_gain<=1;
            age<=0;previous_link<=0;previous_session<=0;previous_clear<=0;
            valid_o<=0;left_o<=0;right_o<=0;clip_o<=0;
            config_applied_o<=0;history_done_o<=0;applied_rate_44100_o<=0;
            fallback_count_o<=0;rejected_count_o<=0;
        end else begin
            valid_o<=0;clip_o<=0;config_applied_o<=0;history_done_o<=0;
            previous_link<=usable_link;previous_session<=link_session_i;previous_clear<=clear_i;
            if(fence)begin
                generation<=next_generation(generation);sequence_number<=0;
                request_pending<=0;request_sent<=0;have_response<=0;
                // Ordinary config/history preserve the W wet gain. Retain
                // its active tail for the chain's next SELECT, before any
                // maintenance frame can refresh this cached public state.
                if(clear_i || link_changed)remote_active<=0;
                generation_reset_gain<=clear_i || link_changed;
            end
            if(config_accept)begin
                applied_rate_44100_o<=rate_44100_i;config_applied_o<=1;history_done_o<=1;
            end else if(history_accept)history_done_o<=1;
            if(req_valid_o && req_ready_i)begin request_pending<=0;request_sent<=1;end
            if(rsp_valid_i)begin
                if(response_matches)begin
                    have_response<=1;response_left<=rsp_left_i;response_right<=rsp_right_i;
                    response_clip<=rsp_clip_i;response_active<=rsp_active_i;
                end else if(rejected_count_o!=32'hffff_ffff)rejected_count_o<=rejected_count_o+1'b1;
            end
            if(clear_i || config_accept || history_accept)begin
                busy<=0;request_pending<=0;request_sent<=0;have_response<=0;
                valid_o<=0;left_o<=0;right_o<=0;
            end else if(busy)begin
                if(deadline)begin
                    busy<=0;request_pending<=0;request_sent<=0;have_response<=0;valid_o<=1;
                    // A link fence revokes even a previously cached response.
                    if(have_response && frame_live)begin
                        left_o<=response_left;right_o<=response_right;clip_o<=response_clip;
                        remote_active<=response_active;
                    end else if(rsp_valid_i && response_matches)begin
                        left_o<=rsp_left_i;right_o<=rsp_right_i;clip_o<=rsp_clip_i;
                        remote_active<=rsp_active_i;
                    end else begin
                        left_o<=dry_left;right_o<=dry_right;remote_active<=0;
                        if(fallback_count_o!=32'hffff_ffff)fallback_count_o<=fallback_count_o+1'b1;
                    end
                end else age<=age+1'b1;
            end else if(valid_i && ready_o)begin
                busy<=1;age<=0;dry_left<=left_i;dry_right<=right_i;
                frame_session<=link_session_i;frame_generation<=fence ? next_generation(generation) : generation;
                frame_sequence<=fence ? 32'd0 : sequence_number;
                sequence_number<=fence ? 32'd1 : sequence_number+1'b1;
                frame_rate<=applied_rate_44100_o;frame_enabled<=enabled_i;
                frame_reset_gain<=fence ? (clear_i || link_changed) : generation_reset_gain;
                request_pending<=usable_link;request_sent<=0;have_response<=0;
            end
        end
    end
`ifndef SYNTHESIS
    initial if(DEADLINE_CYCLES<4 || DEADLINE_CYCLES>512)
        $fatal(1,"remote reverb source-stage deadline must be 4..512 clocks");
`endif
endmodule
`default_nettype wire
