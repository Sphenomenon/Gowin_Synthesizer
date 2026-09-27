`timescale 1ns/1ps
module tb_tf_flac_pcm_decoder;
    reg clk = 1'b0;
    always #5 clk = ~clk;
    reg rst_n = 1'b0;
    reg restart = 1'b0;
    reg in_valid = 1'b0;
    reg [7:0] in_byte = 0;
    wire in_ready;
    wire format_ready;
    wire [19:0] sample_rate_hz;
    wire stereo;
    wire [5:0] bits_per_sample;
    wire pcm_valid;
    wire signed [15:0] pcm_left, pcm_right;
    wire unsupported, error;
    wire [15:0] frame_count;

    tf_flac_pcm_decoder dut (
        .clk(clk), .rst_n(rst_n), .restart(restart),
        .in_valid(in_valid), .in_byte(in_byte), .in_ready(in_ready),
        .format_ready(format_ready), .sample_rate_hz(sample_rate_hz),
        .stereo(stereo), .bits_per_sample(bits_per_sample),
        .pcm_valid(pcm_valid), .pcm_ready(1'b1),
        .pcm_left(pcm_left), .pcm_right(pcm_right),
        .unsupported(unsupported), .error(error), .frame_count(frame_count)
    );

    reg [7:0] data [0:73];
    integer i;
    integer got = 0;
    integer errors = 0;
    reg signed [15:0] expected [0:15];

    always @(negedge clk) begin
        if (rst_n && pcm_valid) begin
            if (got < 16) begin
                if (pcm_left !== expected[got] || pcm_right !== expected[got]) errors = errors + 1;
            end else errors = errors + 1;
            got = got + 1;
        end
    end

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
        data[0]=8'h66; data[1]=8'h4c; data[2]=8'h61; data[3]=8'h43;
        data[4]=8'h80; data[5]=8'h00; data[6]=8'h00; data[7]=8'h22;
        data[8]=8'h00; data[9]=8'h10; data[10]=8'h00; data[11]=8'h10;
        data[12]=8'h00; data[13]=8'h00; data[14]=8'h20; data[15]=8'h00;
        data[16]=8'h00; data[17]=8'h20; data[18]=8'h01; data[19]=8'hf4;
        data[20]=8'h00; data[21]=8'hf0; data[22]=8'h00; data[23]=8'h00;
        data[24]=8'h00; data[25]=8'h10; data[26]=8'hfc; data[27]=8'h1d;
        data[28]=8'h18; data[29]=8'h24; data[30]=8'h4d; data[31]=8'hbd;
        data[32]=8'h71; data[33]=8'h80; data[34]=8'hdd; data[35]=8'h45;
        data[36]=8'hd0; data[37]=8'hfb; data[38]=8'h87; data[39]=8'h00;
        data[40]=8'hb1; data[41]=8'hd1; data[42]=8'hff; data[43]=8'hf8;
        data[44]=8'h64; data[45]=8'h08; data[46]=8'h00; data[47]=8'h0f;
        data[48]=8'hce; data[49]=8'h10; data[50]=8'h07; data[51]=8'ha0;
        data[52]=8'h00; data[53]=8'h47; data[54]=8'hd0; data[55]=8'h8f;
        data[56]=8'h9e; data[57]=8'h3f; data[58]=8'hff; data[59]=8'h0f;
        data[60]=8'hff; data[61]=8'hf2; data[62]=8'h69; data[63]=8'h24;
        data[64]=8'hd2; data[65]=8'h40; data[66]=8'h00; data[67]=8'h2d;
        data[68]=8'h53; data[69]=8'hb2; data[70]=8'h91; data[71]=8'hc0;
        data[72]=8'h04; data[73]=8'h9b;
        expected[0]=0; expected[1]=1000; expected[2]=-1000; expected[3]=32767;
        expected[4]=-32768; expected[5]=1234; expected[6]=1234; expected[7]=0;
        expected[8]=1; expected[9]=-1; expected[10]=2; expected[11]=-2;
        expected[12]=3; expected[13]=-3; expected[14]=4; expected[15]=-4;
        repeat (4) @(posedge clk);
        rst_n = 1'b1;
        for (i=0; i<74; i=i+1) send_byte(data[i]);
        repeat (2000) @(posedge clk);
        if (!format_ready || sample_rate_hz !== 20'd8000 || stereo ||
            bits_per_sample !== 6'd16 || unsupported || error || got != 16 || errors != 0) begin
            $display("tb_tf_flac_pcm_decoder: FAIL got=%0d errors=%0d format=%0d rate=%0d unsupported=%0d error=%0d", got, errors, format_ready, sample_rate_hz, unsupported, error);
            $finish;
        end
        $display("PASS tb_tf_flac_pcm_decoder: FLAC fixed/Rice PCM16");
        $finish;
    end
endmodule
