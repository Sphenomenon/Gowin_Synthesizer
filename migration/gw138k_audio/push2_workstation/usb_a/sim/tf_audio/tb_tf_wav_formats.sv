`timescale 1ns/1ps
// Sample-format coverage for tf_wav_pcm_decoder: 8-bit unsigned mono,
// 16-bit mono, 24-bit and 32-bit stereo truncation, non-PCM rejection, and
// output back-pressure (an irregular ready must not drop or reorder samples).
module tb_tf_wav_formats;
    reg clk = 1'b0;
    always #5 clk = ~clk;

    reg rst_n = 1'b0;
    reg restart = 1'b0;
    reg in_valid = 1'b0;
    reg [7:0] in_byte = 8'h00;
    wire in_ready;
    wire header_valid, stereo, pcm_valid, unsupported;
    wire [19:0] rate;
    wire [5:0] bits;
    wire signed [15:0] pcm_left, pcm_right;

    // Consumer ready: either a fixed level, or a repeating pattern used by the
    // back-pressure case.  A single driver (the wire) avoids the race that a
    // procedural toggle would introduce.
    reg  manual_ready = 1'b1;
    reg  bp_mode = 1'b0;
    reg  [3:0] bp_cnt = 4'd0;
    reg  bp_ready = 1'b0;
    wire pcm_ready = bp_mode ? bp_ready : manual_ready;

    always @(posedge clk) if (bp_mode) begin
        bp_cnt   <= (bp_cnt == 4'd4) ? 4'd0 : bp_cnt + 4'd1;
        bp_ready <= (bp_cnt < 4'd3);
    end

    tf_wav_pcm_decoder dut (
        .clk(clk), .rst_n(rst_n), .restart(restart),
        .in_valid(in_valid), .in_byte(in_byte), .in_ready(in_ready),
        .header_valid(header_valid), .sample_rate_hz(rate), .stereo(stereo),
        .bits_per_sample(bits), .pcm_valid(pcm_valid), .pcm_ready(pcm_ready),
        .pcm_left(pcm_left), .pcm_right(pcm_right), .unsupported(unsupported));

    integer errors = 0;
    integer nsamp = 0;
    reg signed [15:0] cap_l [0:15];
    reg signed [15:0] cap_r [0:15];
    always @(posedge clk) if (rst_n && pcm_valid && pcm_ready) begin
        if (nsamp < 16) begin cap_l[nsamp] = pcm_left; cap_r[nsamp] = pcm_right; end
        nsamp = nsamp + 1;
    end

    reg [7:0] pkt [0:255];
    integer len = 0;

    task automatic push(input [7:0] b); begin pkt[len] = b; len = len + 1; end endtask
    task automatic tag(input [31:0] s); begin
        push(s[31:24]); push(s[23:16]); push(s[15:8]); push(s[7:0]);
    end endtask
    task automatic le32(input [31:0] v); begin
        push(v[7:0]); push(v[15:8]); push(v[23:16]); push(v[31:24]);
    end endtask
    task automatic le16(input [15:0] v); begin push(v[7:0]); push(v[15:8]); end endtask

    task automatic build_header(input [15:0] fmt, input [15:0] ch,
                                input [31:0] fs, input [15:0] bp,
                                input [31:0] dlen);
        begin
            tag("RIFF"); le32(36 + dlen); tag("WAVE");
            tag("fmt "); le32(16);
            le16(fmt); le16(ch); le32(fs); le32(fs * ch * (bp / 8));
            le16(ch * (bp / 8)); le16(bp);
            tag("data"); le32(dlen);
        end
    endtask

    task automatic send_byte(input [7:0] b);
        begin
            @(negedge clk);
            while (!in_ready) @(negedge clk);
            in_byte  = b;
            in_valid = 1'b1;
            @(negedge clk);
            in_valid = 1'b0;
        end
    endtask

    task automatic run_pkt;
        integer i;
        begin
            restart = 1'b1;
            @(negedge clk);
            restart = 1'b0;
            nsamp   = 0;
            for (i = 0; i < len; i = i + 1) send_byte(pkt[i]);
            repeat (6) @(posedge clk);
        end
    endtask

    task automatic check(input logic ok, input [255:0] name);
        begin
            if (!ok) begin
                errors = errors + 1;
                $display("  FAIL %0s", name);
            end
        end
    endtask

    initial begin
        repeat (4) @(posedge clk);
        rst_n = 1'b1;

        // ---- 8-bit unsigned mono: 0x00 -> -32768, 0x80 -> 0, 0xFF -> 32512 --
        len = 0;
        build_header(1, 1, 8000, 8, 3);
        push(8'h00); push(8'h80); push(8'hFF);
        run_pkt;
        check(bits === 6'd8 && !stereo && header_valid && !unsupported, "8bit flags");
        check(nsamp == 3, "8bit count");
        check(cap_l[0] === -16'sd32768 && cap_r[0] === -16'sd32768, "8bit -full");
        check(cap_l[1] === 16'sd0, "8bit mid");
        check(cap_l[2] === 16'sd32512, "8bit +full");

        // ---- 16-bit mono duplicated to both channels ----------------------
        len = 0;
        build_header(1, 1, 44100, 16, 4);
        push(8'h00); push(8'h80);      // 0x8000 = -32768
        push(8'hFF); push(8'h7F);      // 0x7FFF = +32767
        run_pkt;
        check(!stereo && nsamp == 2, "16mono shape");
        check(cap_l[0] === -16'sd32768 && cap_r[0] === -16'sd32768, "16mono l/r equal");
        check(cap_l[1] === 16'sd32767 && cap_r[1] === 16'sd32767, "16mono +full");

        // ---- 24-bit stereo: top 16 bits kept ------------------------------
        len = 0;
        build_header(1, 2, 48000, 24, 12);
        push(8'h56); push(8'h34); push(8'h12);   // L 0x123456 -> 0x1234
        push(8'hEF); push(8'hCD); push(8'hAB);   // R 0xABCDEF -> 0xABCD
        push(8'hFF); push(8'hFF); push(8'hFF);   // L 0xFFFFFF -> 0xFFFF
        push(8'h00); push(8'h00); push(8'h80);   // R 0x800000 -> 0x8000
        run_pkt;
        check(stereo && bits === 6'd24 && nsamp == 2, "24bit shape");
        check(cap_l[0] === 16'sh1234 && cap_r[0] === -16'sh5433, "24bit sample0");
        check(cap_l[1] === -16'sd1 && cap_r[1] === -16'sd32768, "24bit extremes");

        // ---- 32-bit stereo: top 16 bits kept ------------------------------
        len = 0;
        build_header(1, 2, 48000, 32, 8);
        push(8'h78); push(8'h56); push(8'h34); push(8'h12);   // L -> 0x1234
        push(8'h98); push(8'hBA); push(8'hDC); push(8'hFE);   // R -> 0xFEDC
        run_pkt;
        check(stereo && bits === 6'd32 && nsamp == 1, "32bit shape");
        check(cap_l[0] === 16'sh1234 && cap_r[0] === -16'sd292, "32bit sample");

        // ---- non-PCM rejected --------------------------------------------
        len = 0;
        build_header(3, 2, 44100, 16, 4);   // IEEE float
        push(8'h00); push(8'h00); push(8'h80); push(8'h3F);
        run_pkt;
        check(unsupported && !header_valid && nsamp == 0, "non-PCM rejected");

        // ---- back-pressure: irregular ready must not drop samples ---------
        len = 0;
        build_header(1, 1, 8000, 8, 4);
        push(8'h10); push(8'h20); push(8'h30); push(8'h40);
        restart = 1'b1; @(negedge clk); restart = 1'b0; nsamp = 0;
        begin : bp
            integer i;
            manual_ready = 1'b1;
            for (i = 0; i < 44; i = i + 1) send_byte(pkt[i]);   // header, flowing
            bp_mode = 1'b1;                                     // ready now stutters
            for (i = 44; i < len; i = i + 1) send_byte(pkt[i]);
            manual_ready = 1'b1;
            bp_mode = 1'b0;
            repeat (8) @(posedge clk);
        end
        check(nsamp == 4, "backpressure count");
        check(cap_l[0] === -16'sd28672 && cap_l[1] === -16'sd24576 &&
              cap_l[2] === -16'sd20480 && cap_l[3] === -16'sd16384,
              "backpressure order");

        if (errors != 0) begin
            $display("tb_tf_wav_formats: FAIL errors=%0d", errors);
            $finish;
        end
        $display("PASS tb_tf_wav_formats");
        $finish;
    end
endmodule
