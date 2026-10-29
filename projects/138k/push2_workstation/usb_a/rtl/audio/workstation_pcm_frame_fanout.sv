`timescale 1ns/1ps

// Selected-MCLK domain, AFTER the physical serializer completes the frame.
// Taps never throttle audio. Pulse-valid sinks accept only when ready; loss
// is reported independently so window/object owners can discard/fail.
module workstation_pcm_frame_fanout (
    input wire clk_i, rst_ni,
    input wire frame_valid_i, frame_error_i, frame_44k1_i,
    input wire [31:0] frame_epoch_i, frame_sequence_i, frame_pcm_i,
    input wire analysis_enable_i, analysis_ready_i, record_enable_i, record_ready_i,
    output wire analysis_valid_o, record_valid_o,
    output wire frame_error_o, frame_44k1_o,
    output wire [31:0] frame_epoch_o, frame_sequence_o, frame_pcm_o,
    output wire stream_change_o, sequence_gap_o, analysis_gap_o, record_fault_o,
    output reg [31:0] analysis_drop_count_o, record_drop_count_o,
    output reg [31:0] sequence_gap_count_o, stream_change_count_o, error_frame_count_o
);
    reg have_previous, previous_rate;
    reg [31:0] previous_epoch, previous_sequence;
    wire changed=have_previous && (previous_rate!=frame_44k1_i || previous_epoch!=frame_epoch_i);
    assign stream_change_o=frame_valid_i && (!have_previous || changed);
    assign sequence_gap_o=frame_valid_i && have_previous && !changed && frame_sequence_i!=previous_sequence+1'b1;
    assign analysis_valid_o=frame_valid_i && analysis_enable_i;
    assign record_valid_o=frame_valid_i && record_enable_i;
    assign analysis_gap_o=analysis_valid_o && (frame_error_i || sequence_gap_o || changed || !analysis_ready_i);
    assign record_fault_o=record_valid_o && (frame_error_i || sequence_gap_o || changed || !record_ready_i);
    assign frame_error_o=frame_error_i;
    assign frame_44k1_o=frame_44k1_i;
    assign frame_epoch_o=frame_epoch_i;
    assign frame_sequence_o=frame_sequence_i;
    assign frame_pcm_o=frame_pcm_i;
    function automatic [31:0] increment(input [31:0] value);
        increment=&value ? value:value+1'b1;
    endfunction
    always @(posedge clk_i or negedge rst_ni)begin
        if(!rst_ni)begin
            have_previous<=0;previous_rate<=0;previous_epoch<=0;previous_sequence<=0;
            analysis_drop_count_o<=0;record_drop_count_o<=0;sequence_gap_count_o<=0;
            stream_change_count_o<=0;error_frame_count_o<=0;
        end else if(frame_valid_i)begin
            have_previous<=1;previous_rate<=frame_44k1_i;previous_epoch<=frame_epoch_i;previous_sequence<=frame_sequence_i;
            if(analysis_valid_o && !analysis_ready_i)analysis_drop_count_o<=increment(analysis_drop_count_o);
            if(record_valid_o && !record_ready_i)record_drop_count_o<=increment(record_drop_count_o);
            if(sequence_gap_o)sequence_gap_count_o<=increment(sequence_gap_count_o);
            if(stream_change_o)stream_change_count_o<=increment(stream_change_count_o);
            if(frame_error_i)error_frame_count_o<=increment(error_frame_count_o);
        end
    end
endmodule
