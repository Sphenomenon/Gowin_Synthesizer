`timescale 1ns/1ps
// Unit test for the RIFF/WAVE chunk walker: canonical header, metadata chunks
// before fmt, 18- and 40-byte fmt chunks, an odd-sized chunk with its pad byte,
// and a non-PCM stream that must be rejected and not streamed.
module tb_tf_wav_chunk_parser;
    reg clk = 1'b0;
    always #5 clk = ~clk;

    reg rst_n = 1'b0;
    reg restart = 1'b0;
    reg inen = 1'b0;
    reg [7:0] inbyte = 8'h00;
    wire pcm_en;
    wire [7:0] pcm_byte;
    wire [19:0] rate;
    wire [3:0] channels;
    wire [5:0] bits;
    wire [15:0] audio_format;
    wire hv, uns;

    tf_wav_chunk_parser dut (
        .clk(clk), .rst_n(rst_n), .restart(restart),
        .inen(inen), .inbyte(inbyte),
        .pcm_en(pcm_en), .pcm_byte(pcm_byte),
        .sample_rate(rate), .channels(channels), .bits(bits),
        .audio_format(audio_format), .header_valid(hv),
        .unsupported(uns));

    integer errors = 0;
    integer ncap = 0;
    reg [7:0] cap [0:63];
    always @(posedge clk) if (rst_n && pcm_en) begin
        if (ncap < 64) cap[ncap] = pcm_byte;
        ncap = ncap + 1;
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
    task automatic clear_buf; begin len = 0; end endtask

    task automatic send(input [7:0] b);
        begin
            @(negedge clk);
            inbyte = b;
            inen   = 1'b1;
            @(negedge clk);
            inen   = 1'b0;
        end
    endtask

    task automatic run_buf;
        integer i;
        begin
            restart = 1'b1;
            @(negedge clk);
            restart = 1'b0;
            ncap    = 0;
            for (i = 0; i < len; i = i + 1) send(pkt[i]);
            repeat (4) @(posedge clk);
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

    integer i;
    initial begin
        repeat (4) @(posedge clk);
        rst_n = 1'b1;

        // ---- Case A: canonical 44-byte header, 4 PCM bytes ----------------
        clear_buf;
        tag("RIFF"); le32(36); tag("WAVE");
        tag("fmt "); le32(16);
        le16(1); le16(2); le32(44100); le32(176400); le16(4); le16(16);
        tag("data"); le32(4);
        push(8'h34); push(8'h12); push(8'hDC); push(8'hFE);
        run_buf;
        check(rate === 20'd44100, "A rate");
        check(channels === 4'd2, "A channels");
        check(bits === 6'd16, "A bits");
        check(audio_format === 16'd1, "A format");
        check(hv === 1'b1 && uns === 1'b0, "A flags");
        check(ncap == 4, "A pcm count");
        check(cap[0] === 8'h34 && cap[1] === 8'h12 && cap[2] === 8'hDC && cap[3] === 8'hFE, "A pcm bytes");

        // ---- Case B: LIST metadata chunk before fmt -----------------------
        clear_buf;
        tag("RIFF"); le32(60); tag("WAVE");
        tag("LIST"); le32(10);
        for (i = 0; i < 10; i = i + 1) push(8'hAA);
        tag("fmt "); le32(16);
        le16(1); le16(2); le32(48000); le32(192000); le16(4); le16(16);
        tag("data"); le32(4);
        push(8'h01); push(8'h02); push(8'h03); push(8'h04);
        run_buf;
        check(rate === 20'd48000, "B rate");
        check(channels === 4'd2 && bits === 6'd16 && uns === 1'b0, "B fmt");
        check(ncap == 4 && cap[0] === 8'h01, "B pcm");

        // ---- Case C: 18-byte fmt chunk (cbSize) ---------------------------
        clear_buf;
        tag("RIFF"); le32(38); tag("WAVE");
        tag("fmt "); le32(18);
        le16(1); le16(1); le32(22050); le32(44100); le16(2); le16(16); le16(0);
        tag("data"); le32(2);
        push(8'h10); push(8'h20);
        run_buf;
        check(rate === 20'd22050, "C rate");
        check(channels === 4'd1, "C channels");
        check(uns === 1'b0 && hv === 1'b1, "C flags");
        check(ncap == 2 && cap[0] === 8'h10, "C pcm");

        // ---- Case D: 40-byte WAVE_FORMAT_EXTENSIBLE with PCM sub-format ---
        clear_buf;
        tag("RIFF"); le32(60); tag("WAVE");
        tag("fmt "); le32(40);
        le16(16'hFFFE); le16(2); le32(48000); le32(192000); le16(4); le16(16);
        le16(22); le16(16); le32(3);                 // cbSize, valid bits, mask
        // KSDATAFORMAT_SUBTYPE_PCM GUID: 01 00 00 00 00 00 10 00 80 00 00 AA 00 38 9B 71
        push(8'h01); push(8'h00); push(8'h00); push(8'h00);
        push(8'h00); push(8'h00); push(8'h10); push(8'h00);
        push(8'h80); push(8'h00); push(8'h00); push(8'hAA);
        push(8'h00); push(8'h38); push(8'h9B); push(8'h71);
        tag("data"); le32(4);
        push(8'h55); push(8'h66); push(8'h77); push(8'h88);
        run_buf;
        check(audio_format === 16'd1, "D format normalised to PCM");
        check(rate === 20'd48000 && channels === 4'd2 && bits === 6'd16, "D fmt");
        check(uns === 1'b0 && ncap == 4 && cap[0] === 8'h55, "D pcm");

        // ---- Case E: odd-sized chunk with alignment pad -------------------
        clear_buf;
        tag("RIFF"); le32(54); tag("WAVE");
        tag("JUNK"); le32(5);
        for (i = 0; i < 5; i = i + 1) push(8'hEE);
        push(8'h00);                                  // alignment pad
        tag("fact"); le32(4); le32(1);
        tag("fmt "); le32(16);
        le16(1); le16(2); le32(44100); le32(176400); le16(4); le16(16);
        tag("data"); le32(4);
        push(8'hA1); push(8'hA2); push(8'hA3); push(8'hA4);
        run_buf;
        check(rate === 20'd44100 && channels === 4'd2, "E fmt after odd chunk");
        check(ncap == 4 && cap[0] === 8'hA1 && cap[3] === 8'hA4, "E pcm");

        // ---- Case F: non-PCM (IEEE float) must be rejected ----------------
        clear_buf;
        tag("RIFF"); le32(36); tag("WAVE");
        tag("fmt "); le32(16);
        le16(3); le16(2); le32(44100); le32(352800); le16(4); le16(32);
        tag("data"); le32(4);
        push(8'h00); push(8'h00); push(8'h80); push(8'h3F);
        run_buf;
        check(uns === 1'b1 && hv === 1'b1, "F unsupported flag");
        check(ncap == 0, "F no pcm streamed");

        // ---- Case G: data is bounded by its size -------------------------
        clear_buf;
        tag("RIFF"); le32(56); tag("WAVE");
        tag("fmt "); le32(16);
        le16(1); le16(2); le32(44100); le32(176400); le16(4); le16(16);
        tag("data"); le32(4);
        push(8'hB1); push(8'hB2); push(8'hB3); push(8'hB4);
        tag("JUNK"); le32(4);
        push(8'hCC); push(8'hCC); push(8'hCC); push(8'hCC);
        run_buf;
        check(ncap == 4 && cap[0] === 8'hB1 && cap[3] === 8'hB4,
              "G trailing chunk not streamed");

        // ---- Case H: zero-length chunks must not shift the parse ----------
        clear_buf;
        tag("RIFF"); le32(46); tag("WAVE");
        tag("JUNK"); le32(0);
        tag("fact"); le32(0);
        tag("fmt "); le32(16);
        le16(1); le16(2); le32(44100); le32(176400); le16(4); le16(16);
        tag("data"); le32(4);
        push(8'hC1); push(8'hC2); push(8'hC3); push(8'hC4);
        run_buf;
        check(rate === 20'd44100 && channels === 4'd2 && uns === 1'b0,
              "H parse survives zero-length chunks");
        check(ncap == 4 && cap[0] === 8'hC1 && cap[3] === 8'hC4, "H pcm");

        // ---- Case I: fmt shorter than 16 bytes is rejected ---------------
        clear_buf;
        tag("RIFF"); le32(30); tag("WAVE");
        tag("fmt "); le32(8);
        for (i = 0; i < 8; i = i + 1) push(8'h00);
        tag("data"); le32(4);
        push(8'hD1); push(8'hD2); push(8'hD3); push(8'hD4);
        run_buf;
        check(uns === 1'b1 && ncap == 0, "I short fmt rejected");

        // ---- Case J: data before fmt is rejected -------------------------
        clear_buf;
        tag("RIFF"); le32(52); tag("WAVE");
        tag("data"); le32(4);
        push(8'hE1); push(8'hE2); push(8'hE3); push(8'hE4);
        tag("fmt "); le32(16);
        le16(1); le16(2); le32(44100); le32(176400); le16(4); le16(16);
        run_buf;
        check(uns === 1'b1, "J data-before-fmt unsupported");
        check(ncap == 0, "J no pcm");

        if (errors != 0) begin
            $display("tb_tf_wav_chunk_parser: FAIL errors=%0d", errors);
            $finish;
        end
        $display("PASS tb_tf_wav_chunk_parser");
        $finish;
    end
endmodule
