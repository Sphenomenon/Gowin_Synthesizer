`timescale 1ns/1ps

// Independent compute-domain final PCM owner; not selected by any profile.
// This completion is a PRE-SERIAL diagnostic. Default analysis/record taps
// must consume the physical serializer frame through pcm_frame_fanout instead.
module workstation_final_pcm_router (
    input wire clk_i, rst_ni,
    input wire request_i, request_44k1_i,
    input wire [31:0] request_epoch_i, request_sequence_i,
    output wire request_ready_o,
    input wire active_44k1_i,
    input wire [31:0] active_epoch_i, cancel_epoch_i,
    input wire scope_enable_i, tf_active_i,
    input wire [15:0] master_volume_i,
    input wire mute_i,
    // TF pair/rate/generation must be one atomic, same-clock transaction.
    // Mismatched or absent input is NOT consumed or held as a prior sample.
    input wire tf_valid_i, tf_error_i,
    input wire signed [15:0] tf_left_i, tf_right_i,
    input wire [19:0] tf_sample_rate_i,
    input wire [31:0] tf_generation_i, expected_tf_generation_i,
    output wire tf_ready_o,
    // Existing request-driven render service: one in flight; global reset.
    input wire render_ready_i, render_done_i, render_error_i,
    input wire signed [31:0] render_left_i, render_right_i,
    output reg render_request_o, render_44k1_o,
    output reg frame_valid_o, frame_error_o, frame_44k1_o, frame_source_tf_o,
    output reg [31:0] frame_epoch_o, frame_sequence_o, frame_pcm_o,
    output reg [7:0] frame_error_bits_o,
    output reg [15:0] frame_gain_o,
    output wire quiescent_o,
    output reg [31:0] rejected_request_count_o, tf_underrun_count_o,
    output reg [31:0] rate_mismatch_count_o, stale_source_count_o,
    output reg [31:0] cancelled_frame_count_o, unexpected_render_count_o,
    output reg [31:0] clipped_frame_count_o
);
    localparam [1:0] IDLE=0, WAIT_RENDER=1, MULTIPLY=2, FINISH=3;
    localparam [7:0] SOURCE_ERROR=8'h01, TF_UNDERRUN=8'h02,
        RATE_MISMATCH=8'h04, STALE_SOURCE=8'h08, CANCELLED=8'h10,
        RENDER_BUSY=8'h20;
    reg [1:0] state;
    reg held_rate, held_tf;
    reg [31:0] held_epoch, held_sequence, held_cancel, held_tf_generation;
    reg [7:0] held_errors;
    reg [15:0] applied_gain, held_gain;
    reg [7:0] gain_remainder;
    reg signed [15:0] selected_left, selected_right;
    reg selected_clipped;
    reg signed [32:0] product_left, product_right;
    wire choose_tf=tf_active_i && !scope_enable_i;
    wire current_request=request_44k1_i==active_44k1_i && request_epoch_i==active_epoch_i;
    wire tf_same_rate=tf_sample_rate_i==(request_44k1_i ? 20'd44100:20'd48000);
    wire tf_current=tf_generation_i==expected_tf_generation_i;
    wire accepted=request_i && request_ready_o;
    wire [16:0] rate_step_product=17'd40960+{9'd0,gain_remainder};
    wire [8:0] gain_step=request_44k1_i ? 9'(rate_step_product/17'd147):9'd256;
    wire [15:0] target_gain=mute_i ? 16'd0:master_volume_i;
    wire [16:0] gain_upper={1'b0,applied_gain}+{8'd0,gain_step};
    wire [16:0] gain_lower={1'b0,applied_gain}-{8'd0,gain_step};
    wire [15:0] next_gain=target_gain==0 ? 16'd0:
        {1'b0,target_gain}>gain_upper ? gain_upper[15:0]:
        !gain_lower[16] && {1'b0,target_gain}<gain_lower ? gain_lower[15:0]:target_gain;
    wire cancelled=held_epoch!=active_epoch_i || held_rate!=active_44k1_i ||
        held_cancel!=cancel_epoch_i || (held_tf && held_tf_generation!=expected_tf_generation_i);
    assign request_ready_o=rst_ni && state==IDLE;
    assign quiescent_o=request_ready_o && !frame_valid_o && !render_request_o;
    assign tf_ready_o=accepted && current_request && choose_tf && tf_same_rate && tf_current;

    function automatic [31:0] increment(input [31:0] value);
        increment=&value ? value:value+1'b1;
    endfunction
    // Exact existing PT8211 Q1.31 conversion: nearest, ties away from zero.
    function automatic [16:0] quantize16(input signed [31:0] value);
        reg signed [32:0] rounded, scaled;
        begin
            rounded={value[31],value}+(value[31] ? 33'sd32767:33'sd32768);
            scaled=rounded>>>16;
            if(scaled>32767)quantize16={1'b1,16'h7fff};
            else if(scaled< -32768)quantize16={1'b1,16'h8000};
            else quantize16={1'b0,scaled[15:0]};
        end
    endfunction
    function automatic [16:0] scale16(input signed [32:0] product);
        reg signed [32:0] scaled;
        begin
            // Signed arithmetic truncation matches the old FPC at steady gain.
            scaled=product>>>15;
            if(scaled>32767)scale16={1'b1,16'h7fff};
            else if(scaled< -32768)scale16={1'b1,16'h8000};
            else scale16={1'b0,scaled[15:0]};
        end
    endfunction
    wire [16:0] quantized_left=quantize16(render_left_i), quantized_right=quantize16(render_right_i);
    wire [16:0] scaled_left=scale16(product_left), scaled_right=scale16(product_right);
    always @(posedge clk_i or negedge rst_ni) begin
        if(!rst_ni) begin
            state<=IDLE;held_rate<=0;held_tf<=0;held_epoch<=0;held_sequence<=0;
            held_cancel<=0;held_tf_generation<=0;held_errors<=0;
            applied_gain<=0;held_gain<=0;gain_remainder<=73;
            selected_left<=0;selected_right<=0;selected_clipped<=0;
            product_left<=0;product_right<=0;
            render_request_o<=0;render_44k1_o<=0;
            frame_valid_o<=0;frame_error_o<=0;frame_error_bits_o<=0;frame_44k1_o<=0;
            frame_source_tf_o<=0;frame_epoch_o<=0;frame_sequence_o<=0;frame_pcm_o<=0;frame_gain_o<=0;
            rejected_request_count_o<=0;tf_underrun_count_o<=0;rate_mismatch_count_o<=0;
            stale_source_count_o<=0;cancelled_frame_count_o<=0;unexpected_render_count_o<=0;clipped_frame_count_o<=0;
        end else begin
            render_request_o<=0;frame_valid_o<=0;
            if(request_i && !request_ready_o)rejected_request_count_o<=increment(rejected_request_count_o);
            if(render_done_i && state!=WAIT_RENDER)unexpected_render_count_o<=increment(unexpected_render_count_o);
            case(state)
                IDLE: if(accepted)begin
                    held_rate<=request_44k1_i;held_epoch<=request_epoch_i;held_sequence<=request_sequence_i;
                    held_cancel<=cancel_epoch_i;held_tf<=choose_tf;held_tf_generation<=expected_tf_generation_i;
                    applied_gain<=next_gain;held_gain<=next_gain;
                    if(request_44k1_i && target_gain!=0)gain_remainder<=8'(rate_step_product%17'd147);
                    selected_left<=0;selected_right<=0;selected_clipped<=0;held_errors<=0;
                    state<=MULTIPLY;
                    if(!current_request)begin
                        held_errors<=STALE_SOURCE;stale_source_count_o<=increment(stale_source_count_o);
                    end else if(choose_tf)begin
                        if(!tf_same_rate)begin held_errors<=RATE_MISMATCH;rate_mismatch_count_o<=increment(rate_mismatch_count_o);end
                        else if(!tf_current)begin held_errors<=STALE_SOURCE;stale_source_count_o<=increment(stale_source_count_o);end
                        else if(!tf_valid_i)begin held_errors<=TF_UNDERRUN;tf_underrun_count_o<=increment(tf_underrun_count_o);end
                        else if(tf_error_i)held_errors<=SOURCE_ERROR;
                        else begin selected_left<=tf_left_i;selected_right<=tf_right_i;end
                    end else if(!render_ready_i)held_errors<=RENDER_BUSY;
                    else begin render_request_o<=1;render_44k1_o<=request_44k1_i;state<=WAIT_RENDER;end
                end
                WAIT_RENDER: if(render_done_i)begin
                    if(render_error_i)begin selected_left<=0;selected_right<=0;held_errors<=held_errors|SOURCE_ERROR;end
                    else begin
                        selected_left<=quantized_left[15:0];selected_right<=quantized_right[15:0];
                        selected_clipped<=quantized_left[16] || quantized_right[16];
                    end
                    state<=MULTIPLY;
                end
                MULTIPLY: begin
                    product_left<=selected_left*$signed({1'b0,held_gain});
                    product_right<=selected_right*$signed({1'b0,held_gain});
                    state<=FINISH;
                end
                FINISH: begin
                    frame_valid_o<=1;frame_44k1_o<=held_rate;frame_epoch_o<=held_epoch;
                    frame_sequence_o<=held_sequence;frame_source_tf_o<=held_tf;frame_gain_o<=held_gain;
                    frame_error_bits_o<=held_errors|(cancelled ? CANCELLED:8'd0);
                    frame_error_o<=held_errors!=0 || cancelled;
                    frame_pcm_o<=held_errors!=0 || cancelled ? 32'd0:{scaled_left[15:0],scaled_right[15:0]};
                    if(cancelled)cancelled_frame_count_o<=increment(cancelled_frame_count_o);
                    if(!cancelled && held_errors==0 && (selected_clipped || scaled_left[16] || scaled_right[16]))
                        clipped_frame_count_o<=increment(clipped_frame_count_o);
                    state<=IDLE;
                end
                default:state<=IDLE;
            endcase
        end
    end
endmodule
