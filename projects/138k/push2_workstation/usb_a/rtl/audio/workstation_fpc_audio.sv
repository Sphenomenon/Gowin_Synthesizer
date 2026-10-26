`timescale 1ns/1ps

module workstation_fpc_audio (
    input wire clk_50m_i, dac_reference_clk_i, audio_clk_i, rst_ni, audio_rst_ni,
    input wire [15:0] master_volume_i,
    input wire sample_valid_i, enable_i,
    input wire [31:0] pcm_pair_i,
    output wire mclk_o, bck_o, lrck_o,
    output reg data_o,
    output wire pdn_no, smute_o, sslow_o, sd_o, slow_o,
    output wire frame_clock_o,
    output reg frame_valid_o,
    output reg [31:0] frame_pcm_o,
    output reg [31:0] frame_sequence_o,
    output wire [31:0] mailbox_drop_count_o
);
    wire dac_clk = dac_reference_clk_i;
    wire pll_source_ready = rst_ni && audio_rst_ni;
    (* ASYNC_REG="TRUE", syn_preserve=1 *) reg [1:0] pll_release = 0;
    always @(posedge clk_50m_i or negedge pll_source_ready)
        if (!pll_source_ready) pll_release <= 0;
        else pll_release <= {pll_release[0], 1'b1};
    reg reference_toggle = 0;
    always @(posedge dac_clk or negedge pll_source_ready)
        if (!pll_source_ready) reference_toggle <= 0;
        else reference_toggle <= !reference_toggle;
    (* ASYNC_REG="TRUE", syn_preserve=1 *) reg [1:0] reference_sync = 0;
    reg reference_previous = 0;
    reg [5:0] reference_age = 0;
    reg reference_present = 0;
    always @(posedge clk_50m_i or negedge pll_source_ready) begin
        if (!pll_source_ready) begin
            reference_sync <= 0;
            reference_previous <= 0;
            reference_age <= 0;
            reference_present <= 0;
        end else begin
            reference_sync <= {reference_sync[0], reference_toggle};
            reference_previous <= reference_sync[1];
            if (reference_previous != reference_sync[1]) begin
                reference_age <= 0;
                reference_present <= 1;
            end else if (&reference_age) reference_present <= 0;
            else reference_age <= reference_age + 1'b1;
        end
    end
    wire qualified_reset_n = pll_release[1] && reference_present && pll_source_ready;
    (* ASYNC_REG="TRUE", syn_preserve=1 *) reg [3:0] release_pipe = 0;
    always @(posedge dac_clk or negedge qualified_reset_n)
        if (!qualified_reset_n) release_pipe <= 0;
        else release_pipe <= {release_pipe[2:0], 1'b1};
    wire dac_reset_n = release_pipe[3];
    wire received_valid;
    wire [48:0] received_sample;
    gw138k_stream_cdc #(.WIDTH(49)) u_samples (
        .reset_n(qualified_reset_n), .source_clk(audio_clk_i), .destination_clk(dac_clk),
        .source_valid(sample_valid_i), .source_data({master_volume_i, enable_i, pcm_pair_i}),
        .drop_count(mailbox_drop_count_o), .destination_valid(received_valid),
        .destination_data(received_sample)
    );

    reg [7:0] phase;
    reg [10:0] startup_frames;
    reg [4:0] stale_frames;
    reg [48:0] latest_sample;
    reg [31:0] frame_pcm;
    reg frame_enabled;
    wire frame_boundary = &phase;
    wire sample_current = received_valid || stale_frames < 5'd16;
    wire [48:0] selected_sample = received_valid ? received_sample : latest_sample;
    wire [15:0] target_gain = sample_current && selected_sample[32] ? selected_sample[48:33] : 16'd0;
    reg [15:0] gain;
    wire [15:0] next_gain = target_gain == 0 ? 16'd0 :
        target_gain > gain && target_gain-gain > 16'd256 ? gain+16'd256 :
        gain > target_gain && gain-target_gain > 16'd256 ? gain-16'd256 : target_gain;
    wire signed [32:0] left_product = $signed(selected_sample[31:16]) * $signed({1'b0,next_gain});
    wire signed [32:0] right_product = $signed(selected_sample[15:0]) * $signed({1'b0,next_gain});
    wire [31:0] scaled_pcm = {left_product[30:15],right_product[30:15]};
    assign frame_clock_o = dac_clk;

    assign mclk_o = dac_clk;
    assign bck_o = phase[1];
    assign lrck_o = phase[7];
    assign pdn_no = qualified_reset_n && dac_reset_n && startup_frames >= 11'd4;
    assign smute_o = !qualified_reset_n || !dac_reset_n || startup_frames < 11'd1028 || !frame_enabled || gain == 0;
    assign {sslow_o, sd_o, slow_o} = 3'b000;

    always @(posedge dac_clk or negedge dac_reset_n) begin
        if (!dac_reset_n) begin
            phase <= 0;
            startup_frames <= 0;
            stale_frames <= 5'd16;
            latest_sample <= 0;
            frame_pcm <= 0;
            frame_enabled <= 0;
            gain <= 0;
            data_o <= 0;
            frame_valid_o <= 0;
            frame_pcm_o <= 0;
            frame_sequence_o <= 0;
        end else begin
            frame_valid_o <= 0;
            phase <= phase + 1'b1;
            if (received_valid) begin
                latest_sample <= received_sample;
                stale_frames <= 0;
            end else if (frame_boundary && stale_frames < 5'd16) begin
                stale_frames <= stale_frames + 1'b1;
            end
            if (frame_boundary) begin
                frame_valid_o <= 1;
                frame_sequence_o <= frame_sequence_o+1'b1;
                gain <= next_gain;
                frame_pcm_o <= startup_frames >= 11'd1027 ? scaled_pcm : 32'd0;
                if (startup_frames < 11'd1028) startup_frames <= startup_frames + 1'b1;
                frame_pcm <= scaled_pcm;
                frame_enabled <= sample_current && selected_sample[32];
            end
            if (&phase[1:0]) begin
                if (phase[6]) data_o <= 0;
                else if (phase[7]) data_o <= frame_pcm[15-phase[5:2]];
                else data_o <= frame_pcm[31-phase[5:2]];
            end
        end
    end
endmodule
