`timescale 1ns/1ps
module tb_tf_flac_pcm_decoder_limits;
    reg clk = 1'b0;
    always #5 clk = ~clk;

    reg rst_n = 1'b0;
    reg in_valid = 1'b0;
    reg [7:0] in_byte = 8'd0;
    wire in_ready;
    wire format_ready, pcm_valid, unsupported, error;
    integer i;
    reg [7:0] streaminfo [0:41];

    tf_flac_pcm_decoder #(.MAX_BLOCK_SAMPLES(8)) dut (
        .clk(clk), .rst_n(rst_n), .restart(1'b0),
        .in_valid(in_valid), .in_byte(in_byte), .in_ready(in_ready),
        .format_ready(format_ready), .sample_rate_hz(), .stereo(),
        .bits_per_sample(), .pcm_valid(pcm_valid), .pcm_ready(1'b1),
        .pcm_left(), .pcm_right(), .unsupported(unsupported),
        .error(error), .frame_count()
    );

    task automatic send_byte(input [7:0] value);
        begin
            @(negedge clk);
            while (!in_ready) @(negedge clk);
            in_byte = value;
            in_valid = 1'b1;
            @(negedge clk);
            in_valid = 1'b0;
        end
    endtask

    initial begin
        // STREAMINFO declares min/max block size 16, above this instance's
        // eight-sample storage limit.  No frame bytes are needed.
        streaminfo[0]=8'h66; streaminfo[1]=8'h4c; streaminfo[2]=8'h61; streaminfo[3]=8'h43;
        streaminfo[4]=8'h80; streaminfo[5]=8'h00; streaminfo[6]=8'h00; streaminfo[7]=8'h22;
        streaminfo[8]=8'h00; streaminfo[9]=8'h10; streaminfo[10]=8'h00; streaminfo[11]=8'h10;
        for (i = 12; i < 42; i = i + 1) streaminfo[i]=8'h00;

        repeat (4) @(posedge clk);
        rst_n = 1'b1;
        for (i = 0; i < 42; i = i + 1) send_byte(streaminfo[i]);
        repeat (20) @(posedge clk);
        if (!unsupported || error || format_ready || pcm_valid) begin
            $display("tb_tf_flac_pcm_decoder_limits: FAIL unsupported=%0d error=%0d format=%0d pcm=%0d",
                     unsupported, error, format_ready, pcm_valid);
            $finish;
        end
        $display("PASS tb_tf_flac_pcm_decoder_limits: oversized block rejected before PCM");
        $finish;
    end
endmodule
