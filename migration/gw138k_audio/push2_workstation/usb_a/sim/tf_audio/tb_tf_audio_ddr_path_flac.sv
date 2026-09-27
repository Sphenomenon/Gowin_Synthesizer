// Format-selection smoke test for the DDR-backed FLAC path.
module tb_tf_audio_ddr_path_flac;
    reg clk = 1'b0;
    always #5 clk = ~clk;
    reg rst_n = 1'b0;

    tf_audio_ddr_path #(
        .FILE_EXT  ("FLA"),
        .AUDIO_KIND(3)
    ) dut (
        .clk_50m(clk), .reset_n(rst_n), .restart(1'b0), .track_index(4'd0),
        .memory_clk(clk), .memory_reset_n(rst_n), .memory_ready(1'b0),
        .sample_tick(1'b0), .sd_miso(1'b0), .pcm_ready(1'b0),
        .app_rdy(1'b0), .app_wrdy(1'b0), .app_rvalid(1'b0),
        .app_rdata(256'd0),
        .sd_cs_n(), .sd_sck(), .sd_mosi(), .card_type(), .card_stat(),
        .filesystem_type(), .filesystem_stat(), .scan_done(), .card_ready(),
        .playing(), .eof(), .track_count(), .format_ready(), .unsupported(),
        .audio_ddr_error(), .audio_bank0_valid(), .audio_bank1_valid(),
        .audio_file_size(), .sample_rate_hz(), .stereo(), .bits_per_sample(),
        .pcm_valid(), .pcm_left(), .pcm_right(), .frame_count(),
        .resync_count(), .skipped_frames(), .stuck_frames(),
        .pcm_fifo_parity_errors(), .debug_cmdrsp(), .debug_rwrsp(),
        .debug_cardstate(), .debug_spidone(), .debug_rvalid_session(),
        .app_cmd(), .app_en(), .app_addr(), .app_wdata(), .app_wren(),
        .app_wend()
    );

    initial begin
        repeat (4) @(posedge clk);
        rst_n = 1'b1;
        repeat (8) @(posedge clk);
        $display("PASS tb_tf_audio_ddr_path_flac: FLAC format branch elaborated and reset");
        $finish;
    end
endmodule
