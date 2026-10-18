`timescale 1ns/1ps
// FORMAT=4 is reserved: the core must report it as unsupported and must not
// consume any file bytes or emit PCM. FORMAT=3 is the FLAC decoder.
module tb_tf_audio_ip_unsupported;
    reg clk = 1'b0;
    always #5 clk = ~clk;

    reg rst_n = 1'b0;
    reg byte_valid = 1'b0;
    reg [7:0] byte_data = 8'h00;
    wire byte_ready;
    wire pcm_valid;
    reg pcm_ready = 1'b1;
    wire signed [15:0] pcm_left, pcm_right;
    wire [1:0] format;
    wire format_ready;
    wire [19:0] sample_rate_hz;
    wire [1:0] channels;
    wire [5:0] bits_per_sample;
    wire eof_seen, unsupported, error;
    wire [31:0] bytes_seen;

    tf_audio_decoder_ip #(.FORMAT(4)) dut (
        .clk_i(clk), .rst_ni(rst_n), .restart_i(1'b0),
        .byte_valid_i(byte_valid), .byte_ready_o(byte_ready),
        .byte_data_i(byte_data), .byte_last_i(1'b0),
        .pcm_valid_o(pcm_valid), .pcm_ready_i(pcm_ready),
        .pcm_left_o(pcm_left), .pcm_right_o(pcm_right),
        .format_o(format), .format_ready_o(format_ready),
        .sample_rate_hz_o(sample_rate_hz), .channels_o(channels),
        .bits_per_sample_o(bits_per_sample), .eof_seen_o(eof_seen),
        .unsupported_o(unsupported), .error_o(error),
        .bytes_seen_o(bytes_seen), .frame_count_o(),
        .resync_count_o(), .stuck_frames_o(),
        .pcm_fifo_parity_errors_o());

    integer errors = 0;
    integer i;
    initial begin
        repeat (4) @(posedge clk);
        rst_n = 1'b1;
        for (i = 0; i < 8; i = i + 1) begin
            @(negedge clk);
            byte_data  = 8'hA5;
            byte_valid = 1'b1;
            @(negedge clk);
            byte_valid = 1'b0;
        end
        repeat (4) @(posedge clk);

        if (format !== 2'd3) begin errors = errors + 1; $display("  FAIL format"); end
        if (!unsupported) begin errors = errors + 1; $display("  FAIL unsupported"); end
        if (!error) begin errors = errors + 1; $display("  FAIL error"); end
        if (byte_ready !== 1'b0) begin errors = errors + 1; $display("  FAIL byte_ready"); end
        if (pcm_valid !== 1'b0) begin errors = errors + 1; $display("  FAIL pcm_valid"); end
        if (format_ready !== 1'b0) begin errors = errors + 1; $display("  FAIL format_ready"); end
        if (bytes_seen !== 32'd0) begin errors = errors + 1; $display("  FAIL bytes_seen=%0d", bytes_seen); end

        if (errors != 0) begin
            $display("tb_tf_audio_ip_unsupported: FAIL errors=%0d", errors);
            $finish;
        end
        $display("PASS tb_tf_audio_ip_unsupported");
        $finish;
    end
endmodule
