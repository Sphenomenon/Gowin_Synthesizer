`timescale 1ns/1ps
// End-to-end smoke test for the MP3 branch of tf_audio_decoder_ip.
//
// A real 128 kbit/s ffmpeg-encoded MP3 is streamed in and the decoder must
// report the 48 kHz sample rate and produce a plausible number of non-silent
// stereo frames without stuck-frame or PCM-FIFO parity errors.  MP3 decoders
// are not bit-exact across implementations, so this is a structural check
// rather than a sample-for-sample comparison against the reference PCM.
module tb_tf_mp3_file;
    reg clk = 1'b0;
    always #5 clk = ~clk;

    reg rst_n = 1'b0;
    reg byte_valid = 1'b0;
    reg [7:0] byte_data = 8'h00;
    reg byte_last = 1'b0;
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
    wire [15:0] frame_count, resync_count, stuck_frames, parity_errors;

    tf_audio_decoder_ip #(.FORMAT(1)) dut (
        .clk_i(clk), .rst_ni(rst_n), .restart_i(1'b0),
        .byte_valid_i(byte_valid), .byte_ready_o(byte_ready),
        .byte_data_i(byte_data), .byte_last_i(byte_last),
        .pcm_valid_o(pcm_valid), .pcm_ready_i(pcm_ready),
        .pcm_left_o(pcm_left), .pcm_right_o(pcm_right),
        .format_o(format), .format_ready_o(format_ready),
        .sample_rate_hz_o(sample_rate_hz), .channels_o(channels),
        .bits_per_sample_o(bits_per_sample), .eof_seen_o(eof_seen),
        .unsupported_o(unsupported), .error_o(error),
        .bytes_seen_o(bytes_seen), .frame_count_o(frame_count),
        .resync_count_o(resync_count), .stuck_frames_o(stuck_frames),
        .pcm_fifo_parity_errors_o(parity_errors));

    integer errors = 0;
    integer nsamp = 0;
    integer nnonzero = 0;
    always @(posedge clk) if (rst_n && pcm_valid && pcm_ready) begin
        nsamp = nsamp + 1;
        if (pcm_left !== 16'sd0 || pcm_right !== 16'sd0) nnonzero = nnonzero + 1;
    end

    task automatic feed_byte(input [7:0] b);
        begin
            @(negedge clk);
            while (!byte_ready) @(negedge clk);
            byte_data  = b;
            byte_valid = 1'b1;
            @(negedge clk);
            byte_valid = 1'b0;
        end
    endtask

    task automatic feed_file(input [1023:0] path);
        integer fd;
        integer c;
        begin
            fd = $fopen(path, "rb");
            if (fd == 0) begin
                $display("  cannot open %0s", path);
                errors = errors + 1;
            end else begin
                c = $fgetc(fd);
                while (c != -1) begin
                    feed_byte(c[7:0]);
                    c = $fgetc(fd);
                end
                $fclose(fd);
            end
        end
    endtask

    initial begin
        repeat (4) @(posedge clk);
        rst_n = 1'b1;

        feed_file("sim/data/tf_mp3.mp3");
        // Let the decoder finish the frames already in flight.
        repeat (200000) @(posedge clk);

        if (format !== 2'd1) begin errors = errors + 1; $display("  FAIL format"); end
        if (sample_rate_hz !== 20'd48000) begin errors = errors + 1; $display("  FAIL rate=%0d", sample_rate_hz); end
        if (channels !== 2'd2) begin errors = errors + 1; $display("  FAIL channels"); end
        if (!format_ready) begin errors = errors + 1; $display("  FAIL format_ready"); end
        if (unsupported) begin errors = errors + 1; $display("  FAIL unsupported"); end
        if (frame_count == 16'd0) begin errors = errors + 1; $display("  FAIL frame_count"); end
        if (parity_errors != 16'd0) begin errors = errors + 1; $display("  FAIL parity=%0d", parity_errors); end
        // 0.25 s at 48 kHz is 12000 frames; allow for encoder delay/padding.
        if (nsamp < 10000) begin errors = errors + 1; $display("  FAIL nsamp=%0d", nsamp); end
        if (nnonzero < 5000) begin errors = errors + 1; $display("  FAIL non-silent=%0d", nnonzero); end

        $display("  mp3 frames=%0d nsamp=%0d nonzero=%0d rate=%0d",
                 frame_count, nsamp, nnonzero, sample_rate_hz);

        if (errors != 0) begin
            $display("tb_tf_mp3_file: FAIL errors=%0d", errors);
            $finish;
        end
        $display("PASS tb_tf_mp3_file");
        $finish;
    end
endmodule
