`timescale 1ns/1ps
module tb_tf_wav_pcm_decoder;
    reg clk = 1'b0;
    always #5 clk = ~clk;

    reg rst_n = 1'b0;
    reg restart = 1'b0;
    reg in_valid = 1'b0;
    reg [7:0] in_byte = 8'h00;
    wire in_ready;
    wire header_valid;
    wire [19:0] sample_rate_hz;
    wire stereo;
    wire [5:0] bits_per_sample;
    wire pcm_valid;
    reg pcm_ready = 1'b1;
    wire signed [15:0] pcm_left, pcm_right;

    tf_wav_pcm_decoder dut (
        .clk(clk), .rst_n(rst_n), .restart(restart),
        .in_valid(in_valid), .in_byte(in_byte), .in_ready(in_ready),
        .header_valid(header_valid), .sample_rate_hz(sample_rate_hz),
        .stereo(stereo), .bits_per_sample(bits_per_sample),
        .pcm_valid(pcm_valid), .pcm_ready(pcm_ready),
        .pcm_left(pcm_left), .pcm_right(pcm_right)
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

    task automatic send_byte(input [7:0] value);
        begin
            @(negedge clk);
            while (!in_ready) @(negedge clk);
            in_byte  = value;
            in_valid = 1'b1;
            @(negedge clk);
            in_valid = 1'b0;
        end
    endtask

    task automatic send_header;
        begin
            send_byte("R"); send_byte("I"); send_byte("F"); send_byte("F");
            send_byte(8'h24); send_byte(8'h00); send_byte(8'h00); send_byte(8'h00);
            send_byte("W"); send_byte("A"); send_byte("V"); send_byte("E");
            send_byte("f"); send_byte("m"); send_byte("t"); send_byte(8'h20);
            send_byte(8'h10); send_byte(8'h00); send_byte(8'h00); send_byte(8'h00);
            send_byte(8'h01); send_byte(8'h00); send_byte(8'h02); send_byte(8'h00);
            send_byte(8'h44); send_byte(8'hAC); send_byte(8'h00); send_byte(8'h00);
            send_byte(8'h10); send_byte(8'hB1); send_byte(8'h02); send_byte(8'h00);
            send_byte(8'h04); send_byte(8'h00); send_byte(8'h10); send_byte(8'h00);
            send_byte("d"); send_byte("a"); send_byte("t"); send_byte("a");
            send_byte(8'h08); send_byte(8'h00); send_byte(8'h00); send_byte(8'h00);
        end
    endtask

    initial begin
        repeat (4) @(posedge clk);
        rst_n = 1'b1;
        send_header();
        // Stereo little-endian PCM16: L=0x1234, R=0xFEDC; L=0xFFFE, R=0x4000.
        send_byte(8'h34); send_byte(8'h12); send_byte(8'hDC); send_byte(8'hFE);
        send_byte(8'hFE); send_byte(8'hFF); send_byte(8'h00); send_byte(8'h40);
        repeat (8) @(posedge clk);
        if (!header_valid || sample_rate_hz !== 20'd44100 || !stereo || bits_per_sample !== 6'd16)
            errors = errors + 1;
        if (got != 2 || errors != 0) begin
            $display("tb_tf_wav_pcm_decoder: FAIL got=%0d errors=%0d rate=%0d", got, errors, sample_rate_hz);
            $finish;
        end
        $display("PASS tb_tf_wav_pcm_decoder");
        $finish;
    end
endmodule
