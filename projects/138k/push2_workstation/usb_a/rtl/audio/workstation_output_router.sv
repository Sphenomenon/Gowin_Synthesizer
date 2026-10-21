`timescale 1ns/1ps

module workstation_output_router (
    input wire clk_i, rst_ni,
    input wire scope_enable_i, tf_active_i,
    input wire synth_tick_i, tf_tick_i,
    input wire synth_bck_i, synth_ws_i, synth_data_i, synth_pa_i,
    input wire tf_bck_i, tf_ws_i, tf_data_i, tf_pa_i,
    input wire [31:0] synth_reference_i, synth_voices_i, synth_health_i,
    output wire bck_o, ws_o, data_o, pa_o,
    output wire tap_valid_o,
    output wire [127:0] tap_snapshot_o
);
    wire switching, tf_selected, sample_valid;
    wire [31:0] pcm, reference_sample;

    scope_dac_select selector (
        .clk_i, .rst_ni, .scope_enable_i, .tf_source_active_i(tf_active_i),
        .synth_frame_tick_i(synth_tick_i), .tf_frame_tick_i(tf_tick_i),
        .synth_bck_i, .synth_ws_i, .synth_din_i(synth_data_i), .synth_pa_i,
        .tf_bck_i, .tf_ws_i, .tf_din_i(tf_data_i), .tf_pa_i,
        .hp_bck_o(bck_o), .hp_ws_o(ws_o), .hp_din_o(data_o), .pa_en_o(pa_o),
        .tf_selected_o(tf_selected), .switching_o(switching)
    );
    pt8211_observer observer (
        .clk(clk_i), .reset_n(rst_ni && !switching), .bck(bck_o), .ws(ws_o), .din(data_o),
        .frame_reference(tf_selected ? 32'd0 : synth_reference_i),
        .pcm_pair(pcm), .sample_valid(sample_valid), .trigger_reference(reference_sample)
    );
    assign tap_valid_o = sample_valid && !switching;
    assign tap_snapshot_o = {pcm, reference_sample, tf_selected ? 32'd0 : synth_voices_i, synth_health_i};
endmodule
