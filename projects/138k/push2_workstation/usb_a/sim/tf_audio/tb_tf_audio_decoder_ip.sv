`timescale 1ns/1ps
module tb_tf_audio_decoder_ip;
    reg clk = 1'b0;
    always #5 clk = ~clk;

    reg rst_n = 1'b0;
    reg restart = 1'b0;
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

    tf_audio_decoder_ip #(.FORMAT(2)) dut (
        .clk_i(clk), .rst_ni(rst_n), .restart_i(restart),
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
        .pcm_fifo_parity_errors_o(parity_errors)
    );

    integer got = 0;
    integer errors = 0;

    always @(negedge clk) begin
        if (rst_n && pcm_valid && pcm_ready) begin
            case (got)
                0: if (pcm_left !== 16'sh1234 || pcm_right !== -16'sh0124)
                       errors = errors + 1;
                1: if (pcm_left !== -16'sh0002 || pcm_right !== 16'sh4000)
                       errors = errors + 1;
                default: errors = errors + 1;
            endcase
            got = got + 1;
        end
    end

    task automatic send_byte(input [7:0] value, input last);
        begin
            @(negedge clk);
            while (!byte_ready) @(negedge clk);
            byte_data  = value;
            byte_last  = last;
            byte_valid = 1'b1;
            @(negedge clk);
            byte_valid = 1'b0;
            byte_last  = 1'b0;
        end
    endtask

    task automatic send_header;
        begin
            send_byte("R", 0); send_byte("I", 0); send_byte("F", 0); send_byte("F", 0);
            send_byte(8'h24, 0); send_byte(8'h00, 0); send_byte(8'h00, 0); send_byte(8'h00, 0);
            send_byte("W", 0); send_byte("A", 0); send_byte("V", 0); send_byte("E", 0);
            send_byte("f", 0); send_byte("m", 0); send_byte("t", 0); send_byte(8'h20, 0);
            send_byte(8'h10, 0); send_byte(8'h00, 0); send_byte(8'h00, 0); send_byte(8'h00, 0);
            send_byte(8'h01, 0); send_byte(8'h00, 0); send_byte(8'h02, 0); send_byte(8'h00, 0);
            send_byte(8'h44, 0); send_byte(8'hAC, 0); send_byte(8'h00, 0); send_byte(8'h00, 0);
            send_byte(8'h10, 0); send_byte(8'hB1, 0); send_byte(8'h02, 0); send_byte(8'h00, 0);
            send_byte(8'h04, 0); send_byte(8'h00, 0); send_byte(8'h10, 0); send_byte(8'h00, 0);
            send_byte("d", 0); send_byte("a", 0); send_byte("t", 0); send_byte("a", 0);
            send_byte(8'h08, 0); send_byte(8'h00, 0); send_byte(8'h00, 0); send_byte(8'h00, 0);
        end
    endtask

    initial begin
        repeat (4) @(posedge clk);
        rst_n = 1'b1;
        send_header();
        send_byte(8'h34, 0); send_byte(8'h12, 0); send_byte(8'hDC, 0); send_byte(8'hFE, 0);
        send_byte(8'hFE, 0); send_byte(8'hFF, 0); send_byte(8'h00, 0); send_byte(8'h40, 1);
        repeat (8) @(posedge clk);
        if (format !== 2'd2 || !format_ready || sample_rate_hz !== 20'd44100 ||
            channels !== 2'd2 || bits_per_sample !== 6'd16 || unsupported || error ||
            !eof_seen || bytes_seen !== 32'd52)
            errors = errors + 1;
        if (got != 2 || errors != 0) begin
            $display("tb_tf_audio_decoder_ip: FAIL got=%0d errors=%0d bytes=%0d rate=%0d", got, errors, bytes_seen, sample_rate_hz);
            $finish;
        end
        $display("PASS tb_tf_audio_decoder_ip");
        $finish;
    end
endmodule
