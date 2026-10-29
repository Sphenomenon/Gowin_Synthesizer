`timescale 1ns/1ps

// Audio-specific bounded request/render/return bridge. Its common reset is
// global only: stopping/resetting the serializer must not forget an old render.
module workstation_pcm_frame_bridge (
    input wire reset_ni, serial_clk_i, compute_clk_i,
    input wire serial_reset_ni, serial_quiet_i,
    input wire quiesce_i,
    input wire request_i, request_44k1_i,
    input wire [31:0] request_epoch_i, request_sequence_i,
    output wire request_ready_o,
    output wire sample_valid_o,
    input wire sample_ready_i,
    output wire sample_44k1_o, sample_error_o,
    output wire [31:0] sample_epoch_o, sample_sequence_o, sample_pcm_o,
    // All render ports and quiescent_o belong to compute_clk_i.
    input wire render_ready_i, render_done_i,
    input wire [31:0] rendered_pcm_i,
    input wire rendered_error_i,
    output reg render_request_o,
    output reg render_44k1_o,
    output reg [31:0] render_epoch_o, render_sequence_o,
    output reg render_busy_o, quiescent_o,
    // Saturating counters, global reset only; never erased by stream reset.
    output reg [31:0] request_drop_count_o, return_discard_count_o,
    output reg [31:0] cancelled_request_count_o, cancelled_render_count_o,
    output reg [31:0] unexpected_render_count_o
);
    (* ASYNC_REG="TRUE", syn_preserve=1 *) reg [1:0] serial_release, compute_release;
    (* ASYNC_REG="TRUE", syn_preserve=1 *) reg serial_reset_n, compute_reset_n;
    always @(posedge serial_clk_i or negedge reset_ni)
        if (!reset_ni) begin serial_release <= 0; serial_reset_n <= 0; end
        else begin serial_release <= {serial_release[0],1'b1}; serial_reset_n <= serial_release[1]; end
    always @(posedge compute_clk_i or negedge reset_ni)
        if (!reset_ni) begin compute_release <= 0; compute_reset_n <= 0; end
        else begin compute_release <= {compute_release[0],1'b1}; compute_reset_n <= compute_release[1]; end

    reg request_toggle, request_ack;
    reg reply_toggle, reply_ack;
    // Bundled data is immutable until its two-way handshake completes.
    (* syn_preserve=1 *) reg [64:0] held_request;
    (* syn_preserve=1 *) reg [97:0] held_reply;
    (* ASYNC_REG="TRUE", syn_preserve=1 *) reg [1:0] request_sync, request_ack_sync;
    (* ASYNC_REG="TRUE", syn_preserve=1 *) reg [1:0] reply_sync, reply_ack_sync;
    (* ASYNC_REG="TRUE", syn_preserve=1 *) reg [1:0] serial_quiesce_sync, compute_quiesce_sync;
    reg source_quiet;
    (* ASYNC_REG="TRUE", syn_preserve=1 *) reg [1:0] source_quiet_sync;

    wire reply_pending=reply_sync[1]!=reply_ack;
    wire request_pending=request_sync[1]!=request_ack;
    wire reply_free=reply_toggle==reply_ack_sync[1];
    assign request_ready_o=serial_reset_n && serial_reset_ni && !serial_quiesce_sync[1] &&
                           request_toggle==request_ack_sync[1];
    assign sample_valid_o=serial_reset_n && serial_reset_ni && !serial_quiesce_sync[1] && reply_pending;
    assign {sample_44k1_o,sample_epoch_o,sample_sequence_o,sample_pcm_o,sample_error_o}=held_reply;

    function automatic [31:0] increment(input [31:0] value);
        increment=&value ? value : value+1'b1;
    endfunction

    always @(posedge serial_clk_i or negedge serial_reset_n) begin
        if (!serial_reset_n) begin
            request_toggle<=0; held_request<=0; reply_ack<=0;
            request_ack_sync<=0; reply_sync<=0; serial_quiesce_sync<=3;
            source_quiet<=0;
            request_drop_count_o<=0; return_discard_count_o<=0;
        end else begin
            request_ack_sync<={request_ack_sync[0],request_ack};
            reply_sync<={reply_sync[0],reply_toggle};
            serial_quiesce_sync<={serial_quiesce_sync[0],quiesce_i};
            source_quiet<=serial_quiesce_sync[1] && serial_quiet_i &&
                          request_toggle==request_ack_sync[1] && !reply_pending;
            if (request_i) begin
                if (request_ready_o) begin
                    held_request<={request_44k1_i,request_epoch_i,request_sequence_i};
                    request_toggle<=!request_toggle;
                end else request_drop_count_o<=increment(request_drop_count_o);
            end
            if (reply_pending) begin
                if (serial_quiesce_sync[1] || !serial_reset_ni) begin
                    reply_ack<=reply_sync[1];
                    return_discard_count_o<=increment(return_discard_count_o);
                end else if (sample_ready_i) reply_ack<=reply_sync[1];
            end
        end
    end

    always @(posedge compute_clk_i or negedge compute_reset_n) begin
        if (!compute_reset_n) begin
            request_sync<=0; request_ack<=0; reply_toggle<=0; held_reply<=0;
            reply_ack_sync<=0; compute_quiesce_sync<=3; source_quiet_sync<=0;
            render_request_o<=0; render_44k1_o<=0; render_epoch_o<=0; render_sequence_o<=0;
            render_busy_o<=0; quiescent_o<=0;
            cancelled_request_count_o<=0; cancelled_render_count_o<=0; unexpected_render_count_o<=0;
        end else begin
            request_sync<={request_sync[0],request_toggle};
            reply_ack_sync<={reply_ack_sync[0],reply_ack};
            compute_quiesce_sync<={compute_quiesce_sync[0],quiesce_i};
            source_quiet_sync<={source_quiet_sync[0],source_quiet};
            render_request_o<=0;
            quiescent_o<=compute_quiesce_sync[1] && source_quiet_sync[1] &&
                          !render_busy_o && !request_pending && reply_free;
            if (request_pending) begin
                if (compute_quiesce_sync[1]) begin
                    request_ack<=request_sync[1];
                    cancelled_request_count_o<=increment(cancelled_request_count_o);
                end else if (!render_busy_o && reply_free && render_ready_i) begin
                    {render_44k1_o,render_epoch_o,render_sequence_o}<=held_request;
                    request_ack<=request_sync[1];
                    render_request_o<=1;
                    render_busy_o<=1;
                end
            end
            if (render_done_i) begin
                if (!render_busy_o) unexpected_render_count_o<=increment(unexpected_render_count_o);
                else begin
                    render_busy_o<=0;
                    if (compute_quiesce_sync[1])
                        cancelled_render_count_o<=increment(cancelled_render_count_o);
                    else if (reply_free) begin
                        held_reply<={render_44k1_o,render_epoch_o,render_sequence_o,rendered_pcm_i,rendered_error_i};
                        reply_toggle<=!reply_toggle;
                    end else unexpected_render_count_o<=increment(unexpected_render_count_o);
                end
            end
        end
    end
endmodule
