`timescale 1ns/1ps

// Physical completed-frame observation only. Source audio has NO ready port.
// Coordinated common reset; stream rate/epoch changes never reset this queue.
module workstation_pcm_observation_bridge #(
    parameter integer FIFO_ADDRESS_BITS=4,
    // Default is a 32-bit saturating counter. Smaller values are useful for
    // bounded-counter verification; they do not change its 32-bit port format.
    parameter integer DROP_COUNTER_BITS=32
) (
    input wire reset_ni, source_clk_i, destination_clk_i,
    input wire frame_valid_i,frame_44k1_i,frame_error_i,
    input wire [31:0] frame_epoch_i,frame_sequence_i,frame_pcm_i,
    output reg [31:0] source_drop_count_o,
    output wire [31:0] destination_drop_count_o,
    output reg destination_drop_event_o,
    output wire destination_loss_seen_o,
    // Destination valid/ready: complete payload stays stable while stalled.
    output wire frame_valid_o,
    input wire frame_ready_i,
    output wire frame_44k1_o,frame_error_o,
    output wire [31:0] frame_epoch_o,frame_sequence_o,frame_pcm_o,
    output wire signed [31:0] left_q31_o,right_q31_o,
    // Metadata accompanies valid, including a stalled head. Previous identity
    // advances only on a valid/ready transaction; sequence arithmetic wraps.
    output wire stream_change_o,sequence_gap_o
);
    initial begin
        if(FIFO_ADDRESS_BITS<2 || FIFO_ADDRESS_BITS>8 || DROP_COUNTER_BITS<2 || DROP_COUNTER_BITS>32)
            $fatal(1,"invalid PCM observation queue/counter size");
    end
    localparam [31:0] DROP_MAX=32'hffff_ffff>>(32-DROP_COUNTER_BITS);
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [2:0] source_release,destination_release;
    always @(posedge source_clk_i or negedge reset_ni)
        if(!reset_ni)source_release<=0;else source_release<={source_release[1:0],1'b1};
    always @(posedge destination_clk_i or negedge reset_ni)
        if(!reset_ni)destination_release<=0;else destination_release<={destination_release[1:0],1'b1};
    wire source_reset_n=source_release[2],destination_reset_n=destination_release[2];
    wire write_ready,read_valid;
    wire [97:0] read_data;
    wire drop=source_reset_n && frame_valid_i && !write_ready;
    wire [31:0] next_drop=drop && source_drop_count_o!=DROP_MAX ? source_drop_count_o+1'b1:source_drop_count_o;
    always @(posedge source_clk_i or negedge source_reset_n)
        if(!source_reset_n)source_drop_count_o<=0;else source_drop_count_o<=next_drop;

    // Existing maintained Gray-pointer FIFO owns payload CDC and storage.
    music_async_fifo #(.WIDTH(98),.ADDRESS_BITS(FIFO_ADDRESS_BITS)) frames(
        .write_clk_i(source_clk_i),.write_rst_ni(source_reset_n),
        .write_valid_i(source_reset_n && frame_valid_i),.write_ready_o(write_ready),
        .write_data_i({frame_44k1_i,frame_epoch_i,frame_sequence_i,frame_error_i,frame_pcm_i}),
        .read_clk_i(destination_clk_i),.read_rst_ni(destination_reset_n),.read_valid_o(read_valid),
        .read_ready_i(destination_reset_n && frame_ready_i),.read_data_o(read_data));
    assign frame_valid_o=destination_reset_n && read_valid;
    assign {frame_44k1_o,frame_epoch_o,frame_sequence_o,frame_error_o,frame_pcm_o}=read_data;
    assign left_q31_o=$signed({frame_pcm_o[31:16],16'd0});
    assign right_q31_o=$signed({frame_pcm_o[15:0],16'd0});

    // Reuse the existing registered-Gray counter crossing, but give it the
    // post-drop count. It then commits that last drop on THE SAME source edge,
    // even if source MCLK stops immediately afterwards. No next-frame trigger
    // or source mailbox ACK is required for destination loss visibility.
    // Counter changes by at most one per source edge, including saturation.
    gw138k_counter_cdc drops(
        .reset_n(reset_ni),.source_clk(source_clk_i),.destination_clk(destination_clk_i),
        .source_count(next_drop),.destination_count(destination_drop_count_o));
    assign destination_loss_seen_o=destination_drop_count_o!=0;
    reg [31:0] previous_drop;
    reg have_previous,previous_rate;
    reg [31:0] previous_epoch,previous_sequence;
    wire changed=have_previous && (frame_44k1_o!=previous_rate || frame_epoch_o!=previous_epoch);
    assign stream_change_o=frame_valid_o && (!have_previous || changed);
    assign sequence_gap_o=frame_valid_o && have_previous && !changed && frame_sequence_o!=previous_sequence+1'b1;
    always @(posedge destination_clk_i or negedge destination_reset_n)begin
        if(!destination_reset_n)begin
            previous_drop<=0;destination_drop_event_o<=0;
            have_previous<=0;previous_rate<=0;previous_epoch<=0;previous_sequence<=0;
        end else begin
            destination_drop_event_o<=destination_drop_count_o!=previous_drop;
            previous_drop<=destination_drop_count_o;
            if(frame_valid_o && frame_ready_i)begin
                have_previous<=1;previous_rate<=frame_44k1_o;
                previous_epoch<=frame_epoch_o;previous_sequence<=frame_sequence_o;
            end
        end
    end
endmodule
