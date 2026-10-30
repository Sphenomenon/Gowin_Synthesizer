`timescale 1ns/1ps

// Versioned LAST/session extension of the maintained TF transport.
// Transport generation is the Gray cancellation fence; session generation is
// caller metadata carried atomically with PCM/LAST, not another parameter owner.
// The original bridge and profiles remain unchanged; see v2 provenance/contract.

// Opt-in decoder50 -> continuous compute transport. No file/DDR/routing policy.
// Invalidate advances a registered Gray generation on THAT source edge, so the
// final cancellation remains observable even if source_clk stops immediately.
// A separate single-step Gray ACK chases the published generation. New source
// PCM is gated until that ACK returns: a new packet cannot precede its cancel
// barrier. Stream changes never reset either side of the payload FIFO.
module workstation_tf_frame_bridge_v2 #(
    parameter integer FIFO_ADDRESS_BITS=4,
    parameter [31:0] INITIAL_GENERATION=32'd0
) (
    input wire rst_ni,source_clk_i,compute_clk_i,
    // Source-domain pulses/held controls. Each high invalidate edge is one
    // event; caller combines restart/track/card-lost into this explicit event.
    input wire invalidate_i,source_quiesce_i,
    input wire source_valid_i,source_error_i,source_last_i,
    input wire [31:0] source_session_generation_i,
    input wire [19:0] source_sample_rate_i,
    input wire signed [15:0] source_left_i,source_right_i,
    output wire source_ready_o,
    output reg [31:0] source_generation_o,
    output wire source_generation_pending_o,
    // Source-clock ACK for a caller running on that clock; it requires source
    // edges. The compute-domain ACK below can complete with source stopped.
    output wire source_quiescent_o,
    output reg [31:0] source_accepted_count_o,source_unsupported_count_o,source_error_count_o,
    // Compute-domain held valid/ready packet. Cancellation/quiesce may withdraw
    // a stalled packet; ordinary stalls preserve every payload bit.
    output wire tf_valid_o,
    input wire tf_ready_i,
    output wire tf_error_o,tf_last_o,
    output wire [31:0] tf_session_generation_o,
    output wire [19:0] tf_sample_rate_o,
    output wire signed [15:0] tf_left_o,tf_right_o,
    output wire [31:0] tf_generation_o,
    output reg [31:0] expected_generation_o,
    output reg expected_generation_valid_o,generation_change_o,
    output wire media_quiescent_o,
    output reg [31:0] stale_discard_count_o,quiesce_discard_count_o
);
    initial begin
        if(FIFO_ADDRESS_BITS<2 || FIFO_ADDRESS_BITS>8)
            $fatal(1,"invalid TF frame FIFO size");
    end
    function automatic [31:0] gray(input [31:0] value);
        gray=(value>>1)^value;
    endfunction
    function automatic [31:0] binary(input [31:0] value);
        reg [31:0] prefix1,prefix2,prefix4,prefix8;
        begin
            // Parallel suffix XOR: five levels instead of a 31-bit ripple.
            prefix1=value^(value>>1);
            prefix2=prefix1^(prefix1>>2);
            prefix4=prefix2^(prefix2>>4);
            prefix8=prefix4^(prefix4>>8);
            binary=prefix8^(prefix8>>16);
        end
    endfunction
    function automatic [31:0] increment(input [31:0] value);
        increment=&value ? value : value+1'b1;
    endfunction
    localparam [31:0] INITIAL_GRAY=(INITIAL_GENERATION>>1)^INITIAL_GENERATION;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [2:0] source_release,compute_release;
    always @(posedge source_clk_i or negedge rst_ni)
        if(!rst_ni)source_release<=0;else source_release<={source_release[1:0],1'b1};
    always @(posedge compute_clk_i or negedge rst_ni)
        if(!rst_ni)compute_release<=0;else compute_release<={compute_release[1:0],1'b1};
    wire source_reset_n=source_release[2],compute_reset_n=compute_release[2];
    reg [31:0] source_generation_gray,ack_binary,ack_gray;
    reg source_seen_edge,quiet_published;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [31:0] generation_meta,generation_sync,ack_meta,ack_sync;
    (* ASYNC_REG="TRUE" *) reg [1:0] source_alive_sync,expected_valid_sync,quiesce_sync,quiet_sync,quiesce_return_sync;
    wire [31:0] next_generation=source_generation_o+1'b1;
    wire unsupported=source_sample_rate_i!=20'd48000 && source_sample_rate_i!=20'd44100;
    // Count invalidations from the first edge after COMMON reset, including
    // local FIFO release. No first-clear identity can be lost to reset skew.
    always @(posedge source_clk_i or negedge rst_ni)begin
        if(!rst_ni)begin
            source_generation_o<=INITIAL_GENERATION;source_generation_gray<=INITIAL_GRAY;
            source_seen_edge<=0;
            ack_meta<=INITIAL_GRAY;ack_sync<=INITIAL_GRAY;expected_valid_sync<=0;quiet_sync<=0;quiesce_return_sync<=0;
            source_accepted_count_o<=0;source_unsupported_count_o<=0;source_error_count_o<=0;
        end else begin
            source_seen_edge<=1;
            ack_meta<=ack_gray;ack_sync<=ack_meta;
            expected_valid_sync<={expected_valid_sync[0],expected_generation_valid_o};
            quiet_sync<={quiet_sync[0],quiet_published};
            quiesce_return_sync<={quiesce_return_sync[0],quiesce_sync[1]};
            if(invalidate_i)begin source_generation_o<=next_generation;source_generation_gray<=gray(next_generation);end
            if(source_valid_i && source_ready_o)begin
                source_accepted_count_o<=increment(source_accepted_count_o);
                if(unsupported)source_unsupported_count_o<=increment(source_unsupported_count_o);
                if(source_error_i)source_error_count_o<=increment(source_error_count_o);
            end
        end
    end
    assign source_generation_pending_o=!expected_valid_sync[1] || ack_sync!=source_generation_gray;
    assign source_quiescent_o=source_reset_n && source_quiesce_i && !invalidate_i &&
        !source_generation_pending_o && quiet_sync[1];
    wire write_ready,read_valid,read_ready;
    wire [117:0] read_data;
    assign source_ready_o=source_reset_n && !invalidate_i && !source_quiesce_i && !quiesce_return_sync[1] &&
        !source_generation_pending_o && write_ready;
    music_async_fifo #(.WIDTH(118),.ADDRESS_BITS(FIFO_ADDRESS_BITS)) frames(
        .write_clk_i(source_clk_i),.write_rst_ni(source_reset_n),
        .write_valid_i(source_valid_i && source_ready_o),.write_ready_o(write_ready),
        .write_data_i({source_generation_o,source_session_generation_i,source_sample_rate_i,
                      source_error_i || unsupported,source_last_i,
                      unsupported ? 16'd0 : source_left_i,unsupported ? 16'd0 : source_right_i}),
        .read_clk_i(compute_clk_i),.read_rst_ni(compute_reset_n),
        .read_valid_o(read_valid),.read_ready_i(read_ready),.read_data_o(read_data));

    wire [31:0] synchronized_generation=binary(generation_sync);
    // Gray is bijective, so compare the synchronized identity in its native
    // code. Cancellation/quiet guards need not wait for binary decoding.
    wire cancel_pending=!expected_generation_valid_o || generation_sync!=gray(expected_generation_o);
    reg held_valid;
    reg [117:0] held_packet;
    reg [2:0] quiet_settle;
    wire [31:0] head_generation=read_data[117:86];
    wire read_fire=read_valid && read_ready;
    wire held_fire=tf_valid_o && tf_ready_i;
    assign tf_valid_o=compute_reset_n && held_valid && expected_generation_valid_o &&
        !cancel_pending && !quiesce_sync[1] && tf_generation_o==expected_generation_o;
    assign {tf_generation_o,tf_session_generation_o,tf_sample_rate_o,tf_error_o,
            tf_last_o,tf_left_o,tf_right_o}=held_packet;
    assign read_ready=compute_reset_n && expected_generation_valid_o && !cancel_pending &&
        (quiesce_sync[1] ? !held_valid : (!held_valid || held_fire));
    assign media_quiescent_o=compute_reset_n && expected_generation_valid_o && !cancel_pending &&
        quiesce_sync[1] && quiet_settle==5 && !read_valid && !held_valid;

    // Both Gray buses change by at most one count per producing edge. Physical
    // integration MUST bound bit skew/max delay to the producing period; the
    // continuous nominal76.8MHz compute domain must keep up with decoder50.
    always @(posedge compute_clk_i or negedge rst_ni)begin
        if(!rst_ni)begin
            generation_meta<=INITIAL_GRAY;generation_sync<=INITIAL_GRAY;source_alive_sync<=0;quiesce_sync<=0;
            expected_generation_o<=INITIAL_GENERATION;expected_generation_valid_o<=0;generation_change_o<=0;
            ack_binary<=INITIAL_GENERATION;ack_gray<=INITIAL_GRAY;
            held_valid<=0;held_packet<=0;quiet_settle<=0;quiet_published<=0;
            stale_discard_count_o<=0;quiesce_discard_count_o<=0;
        end else begin
            generation_meta<=source_generation_gray;generation_sync<=generation_meta;
            source_alive_sync<={source_alive_sync[0],source_seen_edge};
            quiesce_sync<={quiesce_sync[0],source_quiesce_i};
            // Publish the compute-domain proof from a register before its
            // two-stage return crossing. The public compute proof above keeps
            // its immediate cancellation/withdrawal guards. Source ACK still
            // requires the matching generation and a held quiesce request.
            quiet_published<=media_quiescent_o;
            generation_change_o<=0;
            if(compute_reset_n && source_alive_sync[1])begin
                expected_generation_valid_o<=1;
                if(cancel_pending)begin
                    expected_generation_o<=synchronized_generation;generation_change_o<=1;
                    held_valid<=0;
                    if(held_valid)stale_discard_count_o<=increment(stale_discard_count_o);
                end else begin
                    if(quiesce_sync[1])begin
                        held_valid<=0;
                        if(held_valid || read_fire)quiesce_discard_count_o<=increment(quiesce_discard_count_o);
                    end else begin
                        if(held_fire)held_valid<=0;
                        if(read_fire && head_generation==expected_generation_o)begin
                            held_packet<=read_data;held_valid<=1;
                        end
                    end
                    if(read_fire && !quiesce_sync[1] && head_generation!=expected_generation_o)
                        stale_discard_count_o<=increment(stale_discard_count_o);
                end
            end
            // Never copy a skipped multi-bit Gray word back across the clock
            // boundary. This independent ACK advances ONE binary/Gray step.
            if(expected_generation_valid_o && ack_binary!=expected_generation_o)begin
                ack_binary<=ack_binary+1'b1;ack_gray<=gray(ack_binary+1'b1);
            end
            if(!quiesce_sync[1] || cancel_pending || !expected_generation_valid_o)quiet_settle<=0;
            else if(quiet_settle!=5)quiet_settle<=quiet_settle+1'b1;
        end
    end
endmodule
