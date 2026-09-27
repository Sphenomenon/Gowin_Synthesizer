`timescale 1ns/1ps
module tb_tf_flac_pcm_decoder_constant_stereo;
    reg clk = 1'b0;
    always #5 clk = ~clk;

    reg rst_n = 1'b0;
    reg in_valid = 1'b0;
    reg [7:0] in_byte = 8'd0;
    reg pcm_ready = 1'b0;
    wire in_ready;
    wire format_ready, stereo, pcm_valid, unsupported, error;
    wire [19:0] sample_rate_hz;
    wire [5:0] bits_per_sample;
    wire signed [15:0] pcm_left, pcm_right;
    wire [15:0] frame_count;

    tf_flac_pcm_decoder dut (
        .clk(clk), .rst_n(rst_n), .restart(1'b0),
        .in_valid(in_valid), .in_byte(in_byte), .in_ready(in_ready),
        .format_ready(format_ready), .sample_rate_hz(sample_rate_hz),
        .stereo(stereo), .bits_per_sample(bits_per_sample),
        .pcm_valid(pcm_valid), .pcm_ready(pcm_ready),
        .pcm_left(pcm_left), .pcm_right(pcm_right),
        .unsupported(unsupported), .error(error), .frame_count(frame_count)
    );

    reg [7:0] data [0:100];
    integer i;
    integer cycles = 0;
    integer got = 0;
    integer errors = 0;

    always @(posedge clk) begin
        if (rst_n && pcm_valid && pcm_ready) begin
            if (pcm_left !== 16'sd123 || pcm_right !== -16'sd45)
                errors = errors + 1;
            got = got + 1;
        end
    end

    // Insert regular output stalls, including during the one-sample-per-cycle
    // constant subframe, to exercise the synchronous channel-memory prefetch.
    always @(negedge clk) begin
        if (!rst_n) begin
            cycles = 0;
            pcm_ready = 1'b0;
        end else begin
            cycles = cycles + 1;
            pcm_ready = (cycles % 3) != 0;
        end
    end

    task automatic send_byte(input [7:0] value);
        integer wait_cycles;
        begin
            @(negedge clk);
            wait_cycles = 0;
            while (!in_ready && wait_cycles < 2000) begin
                wait_cycles = wait_cycles + 1;
                @(negedge clk);
            end
            if (!in_ready) begin
                $display("tb_tf_flac_pcm_decoder_constant_stereo: FAIL input byte=%0d state=%0d unsupported=%0d error=%0d",
                         i, dut.state, unsupported, error);
                $finish;
            end
            in_byte = value;
            in_valid = 1'b1;
            @(negedge clk);
            in_valid = 1'b0;
        end
    endtask

    initial begin
        data[0]=8'h66; data[1]=8'h4c; data[2]=8'h61; data[3]=8'h43;
        data[4]=8'h00; data[5]=8'h00; data[6]=8'h00; data[7]=8'h22;
        data[8]=8'h00; data[9]=8'h10; data[10]=8'h00; data[11]=8'h10;
        data[12]=8'h00; data[13]=8'h00; data[14]=8'h0f; data[15]=8'h00;
        data[16]=8'h00; data[17]=8'h0f; data[18]=8'h01; data[19]=8'hf4;
        data[20]=8'h02; data[21]=8'hf0; data[22]=8'h00; data[23]=8'h00;
        data[24]=8'h00; data[25]=8'h10; data[26]=8'h4e; data[27]=8'h13;
        data[28]=8'h75; data[29]=8'h2a; data[30]=8'hf3; data[31]=8'h32;
        data[32]=8'hb1; data[33]=8'h41; data[34]=8'h40; data[35]=8'h12;
        data[36]=8'hc8; data[37]=8'hbe; data[38]=8'h9f; data[39]=8'had;
        data[40]=8'h76; data[41]=8'h2a; data[42]=8'h84; data[43]=8'h00;
        data[44]=8'h00; data[45]=8'h28; data[46]=8'h20; data[47]=8'h00;
        data[48]=8'h00; data[49]=8'h00; data[50]=8'h72; data[51]=8'h65;
        data[52]=8'h66; data[53]=8'h65; data[54]=8'h72; data[55]=8'h65;
        data[56]=8'h6e; data[57]=8'h63; data[58]=8'h65; data[59]=8'h20;
        data[60]=8'h6c; data[61]=8'h69; data[62]=8'h62; data[63]=8'h46;
        data[64]=8'h4c; data[65]=8'h41; data[66]=8'h43; data[67]=8'h20;
        data[68]=8'h31; data[69]=8'h2e; data[70]=8'h35; data[71]=8'h2e;
        data[72]=8'h30; data[73]=8'h20; data[74]=8'h32; data[75]=8'h30;
        data[76]=8'h32; data[77]=8'h35; data[78]=8'h30; data[79]=8'h32;
        data[80]=8'h31; data[81]=8'h31; data[82]=8'h00; data[83]=8'h00;
        data[84]=8'h00; data[85]=8'h00; data[86]=8'hff; data[87]=8'hf8;
        data[88]=8'h64; data[89]=8'h18; data[90]=8'h00; data[91]=8'h0f;
        data[92]=8'h6c; data[93]=8'h00; data[94]=8'h00; data[95]=8'h7b;
        data[96]=8'h00; data[97]=8'hff; data[98]=8'hd3; data[99]=8'heb;
        data[100]=8'h54;

        repeat (4) @(posedge clk);
        rst_n = 1'b1;
        for (i = 0; i < 101; i = i + 1) send_byte(data[i]);
        repeat (2000) @(posedge clk);
        if (!format_ready || sample_rate_hz !== 20'd8000 || !stereo ||
            bits_per_sample !== 6'd16 || unsupported || error ||
            frame_count == 0 || got != 16 || errors != 0) begin
            $display("tb_tf_flac_pcm_decoder_constant_stereo: FAIL got=%0d errors=%0d frame=%0d unsupported=%0d error=%0d",
                     got, errors, frame_count, unsupported, error);
            $finish;
        end
        $display("PASS tb_tf_flac_pcm_decoder_constant_stereo: constant stereo with backpressure");
        $finish;
    end
endmodule
