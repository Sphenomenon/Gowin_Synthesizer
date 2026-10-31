`timescale 1ns/1ps
// Compare every public producer output. The old module is renamed only in
// the runner output after its original bytes pass the fixed SHA256 gate.
module display_analysis_equivalence_checker (
    input wire clk,rst_ni,
    input wire frame_valid_i,frame_error_i,frame_44k1_i,
    input wire [31:0] frame_epoch_i,frame_sequence_i,frame_pcm_i,
    input wire observation_trusted_i,observation_loss_i,
    input wire [31:0] trigger_reference_i,active_voices_i,status_i,memory_status_i,
    input wire [2:0] effect_mask_i,
    input wire [5:0] effect_order_i,
    input wire start_i,export_done_i,
    input wire start_ready_o,
    input wire source_context_valid_o,
    input wire [31:0] source_sample_rate_o,source_epoch_o,source_generation_o,
    input wire waveform_context_valid_o,analysis_context_valid_o,
    input wire [31:0] waveform_sample_rate_o,waveform_epoch_o,waveform_generation_o,
    input wire [31:0] analysis_sample_rate_o,analysis_epoch_o,analysis_generation_o,
    input wire [255:0] effect_meta_o,
    input wire [31:0] analysis_sequence_o,analysis_skipped_o,stereo_peaks_o,
    input wire analysis_valid_o,
    input wire [2:0] image_gain_o,
    input wire [31:0] discarded_contexts_o,
    input wire read_enable_i,
    input wire [1:0] read_kind_i,
    input wire [15:0] read_addr_i,
    input wire [31:0] read_data_o
);
    wire reference_start_ready_o;
    wire reference_source_context_valid_o;
    wire [31:0] reference_source_sample_rate_o;
    wire [31:0] reference_source_epoch_o;
    wire [31:0] reference_source_generation_o;
    wire reference_waveform_context_valid_o;
    wire reference_analysis_context_valid_o;
    wire [31:0] reference_waveform_sample_rate_o;
    wire [31:0] reference_waveform_epoch_o;
    wire [31:0] reference_waveform_generation_o;
    wire [31:0] reference_analysis_sample_rate_o;
    wire [31:0] reference_analysis_epoch_o;
    wire [31:0] reference_analysis_generation_o;
    wire [255:0] reference_effect_meta_o;
    wire [31:0] reference_analysis_sequence_o;
    wire [31:0] reference_analysis_skipped_o;
    wire [31:0] reference_stereo_peaks_o;
    wire reference_analysis_valid_o;
    wire [2:0] reference_image_gain_o;
    wire [31:0] reference_discarded_contexts_o;
    wire [31:0] reference_read_data_o;
    reference_display_data_analysis_source reference_source (
        .clk(clk),
        .rst_ni(rst_ni),
        .frame_valid_i(frame_valid_i),
        .frame_error_i(frame_error_i),
        .frame_44k1_i(frame_44k1_i),
        .frame_epoch_i(frame_epoch_i),
        .frame_sequence_i(frame_sequence_i),
        .frame_pcm_i(frame_pcm_i),
        .observation_trusted_i(observation_trusted_i),
        .observation_loss_i(observation_loss_i),
        .trigger_reference_i(trigger_reference_i),
        .active_voices_i(active_voices_i),
        .status_i(status_i),
        .memory_status_i(memory_status_i),
        .effect_mask_i(effect_mask_i),
        .effect_order_i(effect_order_i),
        .start_i(start_i),
        .export_done_i(export_done_i),
        .read_enable_i(read_enable_i),
        .read_kind_i(read_kind_i),
        .read_addr_i(read_addr_i),
        .start_ready_o(reference_start_ready_o),
        .source_context_valid_o(reference_source_context_valid_o),
        .source_sample_rate_o(reference_source_sample_rate_o),
        .source_epoch_o(reference_source_epoch_o),
        .source_generation_o(reference_source_generation_o),
        .waveform_context_valid_o(reference_waveform_context_valid_o),
        .analysis_context_valid_o(reference_analysis_context_valid_o),
        .waveform_sample_rate_o(reference_waveform_sample_rate_o),
        .waveform_epoch_o(reference_waveform_epoch_o),
        .waveform_generation_o(reference_waveform_generation_o),
        .analysis_sample_rate_o(reference_analysis_sample_rate_o),
        .analysis_epoch_o(reference_analysis_epoch_o),
        .analysis_generation_o(reference_analysis_generation_o),
        .effect_meta_o(reference_effect_meta_o),
        .analysis_sequence_o(reference_analysis_sequence_o),
        .analysis_skipped_o(reference_analysis_skipped_o),
        .stereo_peaks_o(reference_stereo_peaks_o),
        .analysis_valid_o(reference_analysis_valid_o),
        .image_gain_o(reference_image_gain_o),
        .discarded_contexts_o(reference_discarded_contexts_o),
        .read_data_o(reference_read_data_o)
    );
    integer compared_edges=0;
    always @(posedge clk or negedge clk or negedge rst_ni)begin
        #2;compared_edges=compared_edges+1;
        if(start_ready_o!==reference_start_ready_o)
            $fatal(1,"display analysis output mismatch: start_ready_o edge=%0d dut=%h reference=%h",compared_edges,start_ready_o,reference_start_ready_o);
        if(source_context_valid_o!==reference_source_context_valid_o)
            $fatal(1,"display analysis output mismatch: source_context_valid_o edge=%0d dut=%h reference=%h",compared_edges,source_context_valid_o,reference_source_context_valid_o);
        if(source_sample_rate_o!==reference_source_sample_rate_o)
            $fatal(1,"display analysis output mismatch: source_sample_rate_o edge=%0d dut=%h reference=%h",compared_edges,source_sample_rate_o,reference_source_sample_rate_o);
        if(source_epoch_o!==reference_source_epoch_o)
            $fatal(1,"display analysis output mismatch: source_epoch_o edge=%0d dut=%h reference=%h",compared_edges,source_epoch_o,reference_source_epoch_o);
        if(source_generation_o!==reference_source_generation_o)
            $fatal(1,"display analysis output mismatch: source_generation_o edge=%0d dut=%h reference=%h",compared_edges,source_generation_o,reference_source_generation_o);
        if(waveform_context_valid_o!==reference_waveform_context_valid_o)
            $fatal(1,"display analysis output mismatch: waveform_context_valid_o edge=%0d dut=%h reference=%h",compared_edges,waveform_context_valid_o,reference_waveform_context_valid_o);
        if(analysis_context_valid_o!==reference_analysis_context_valid_o)
            $fatal(1,"display analysis output mismatch: analysis_context_valid_o edge=%0d dut=%h reference=%h",compared_edges,analysis_context_valid_o,reference_analysis_context_valid_o);
        if(waveform_sample_rate_o!==reference_waveform_sample_rate_o)
            $fatal(1,"display analysis output mismatch: waveform_sample_rate_o edge=%0d dut=%h reference=%h",compared_edges,waveform_sample_rate_o,reference_waveform_sample_rate_o);
        if(waveform_epoch_o!==reference_waveform_epoch_o)
            $fatal(1,"display analysis output mismatch: waveform_epoch_o edge=%0d dut=%h reference=%h",compared_edges,waveform_epoch_o,reference_waveform_epoch_o);
        if(waveform_generation_o!==reference_waveform_generation_o)
            $fatal(1,"display analysis output mismatch: waveform_generation_o edge=%0d dut=%h reference=%h",compared_edges,waveform_generation_o,reference_waveform_generation_o);
        if(analysis_sample_rate_o!==reference_analysis_sample_rate_o)
            $fatal(1,"display analysis output mismatch: analysis_sample_rate_o edge=%0d dut=%h reference=%h",compared_edges,analysis_sample_rate_o,reference_analysis_sample_rate_o);
        if(analysis_epoch_o!==reference_analysis_epoch_o)
            $fatal(1,"display analysis output mismatch: analysis_epoch_o edge=%0d dut=%h reference=%h",compared_edges,analysis_epoch_o,reference_analysis_epoch_o);
        if(analysis_generation_o!==reference_analysis_generation_o)
            $fatal(1,"display analysis output mismatch: analysis_generation_o edge=%0d dut=%h reference=%h",compared_edges,analysis_generation_o,reference_analysis_generation_o);
        if(effect_meta_o!==reference_effect_meta_o)
            $fatal(1,"display analysis output mismatch: effect_meta_o edge=%0d dut=%h reference=%h",compared_edges,effect_meta_o,reference_effect_meta_o);
        if(analysis_sequence_o!==reference_analysis_sequence_o)
            $fatal(1,"display analysis output mismatch: analysis_sequence_o edge=%0d dut=%h reference=%h",compared_edges,analysis_sequence_o,reference_analysis_sequence_o);
        if(analysis_skipped_o!==reference_analysis_skipped_o)
            $fatal(1,"display analysis output mismatch: analysis_skipped_o edge=%0d dut=%h reference=%h",compared_edges,analysis_skipped_o,reference_analysis_skipped_o);
        if(stereo_peaks_o!==reference_stereo_peaks_o)
            $fatal(1,"display analysis output mismatch: stereo_peaks_o edge=%0d dut=%h reference=%h",compared_edges,stereo_peaks_o,reference_stereo_peaks_o);
        if(analysis_valid_o!==reference_analysis_valid_o)
            $fatal(1,"display analysis output mismatch: analysis_valid_o edge=%0d dut=%h reference=%h",compared_edges,analysis_valid_o,reference_analysis_valid_o);
        if(image_gain_o!==reference_image_gain_o)
            $fatal(1,"display analysis output mismatch: image_gain_o edge=%0d dut=%h reference=%h",compared_edges,image_gain_o,reference_image_gain_o);
        if(discarded_contexts_o!==reference_discarded_contexts_o)
            $fatal(1,"display analysis output mismatch: discarded_contexts_o edge=%0d dut=%h reference=%h",compared_edges,discarded_contexts_o,reference_discarded_contexts_o);
        if(read_data_o!==reference_read_data_o)
            $fatal(1,"display analysis output mismatch: read_data_o edge=%0d dut=%h reference=%h",compared_edges,read_data_o,reference_read_data_o);
    end
endmodule
