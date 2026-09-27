`timescale 1ns/1ps
module tb_tf_flac_pcm_decoder_verbatim;
    reg clk=0; always #5 clk=~clk;
    reg rst_n=0, in_valid=0; reg [7:0] in_byte=0; wire in_ready;
    wire format_ready, stereo, pcm_valid, unsupported, error;
    wire [19:0] sample_rate_hz; wire [5:0] bits_per_sample; wire signed [15:0] pcm_left, pcm_right;
    wire [15:0] frame_count;
    tf_flac_pcm_decoder dut (
        .clk(clk), .rst_n(rst_n), .restart(1'b0), .in_valid(in_valid), .in_byte(in_byte), .in_ready(in_ready),
        .format_ready(format_ready), .sample_rate_hz(sample_rate_hz), .stereo(stereo),
        .bits_per_sample(bits_per_sample), .pcm_valid(pcm_valid), .pcm_ready(1'b1),
        .pcm_left(pcm_left), .pcm_right(pcm_right), .unsupported(unsupported), .error(error), .frame_count(frame_count));
    reg [7:0] data [0:83];
    reg signed [15:0] expected [0:15];
    integer i, got=0, errors=0;
    always @(negedge clk) if (rst_n && pcm_valid) begin
        if (got >= 16 || pcm_left !== expected[got] || pcm_right !== expected[got]) errors=errors+1;
        got=got+1;
    end
    task automatic send_byte(input [7:0] value);
        begin @(negedge clk); while (!in_ready) @(negedge clk); in_byte=value; in_valid=1; @(negedge clk); in_valid=0; end
    endtask
    initial begin
        data[0]=8'h66; data[1]=8'h4c; data[2]=8'h61; data[3]=8'h43; data[4]=8'h80; data[5]=0; data[6]=0; data[7]=8'h22;
        data[8]=0; data[9]=8'h10; data[10]=0; data[11]=8'h10; data[12]=0; data[13]=0; data[14]=8'h2a; data[15]=0;
        data[16]=0; data[17]=8'h2a; data[18]=1; data[19]=8'hf4; data[20]=0; data[21]=8'hf0; data[22]=0; data[23]=0;
        data[24]=0; data[25]=8'h10; data[26]=8'h3e; data[27]=8'h5f; data[28]=8'h5a; data[29]=8'hc3; data[30]=8'hdc; data[31]=8'hf0;
        data[32]=8'h2e; data[33]=4; data[34]=8'hf1; data[35]=8'hca; data[36]=8'he1; data[37]=8'h63; data[38]=8'h42; data[39]=8'he5;
        data[40]=8'hc4; data[41]=8'h42; data[42]=8'hff; data[43]=8'hf8; data[44]=8'h64; data[45]=8'h08; data[46]=0; data[47]=8'h0f;
        data[48]=8'hce; data[49]=8'h02; data[50]=8'hc4; data[51]=8'hcb; data[52]=8'ha0; data[53]=8'h4f; data[54]=2; data[55]=8'h98;
        data[56]=8'hbc; data[57]=8'h5f; data[58]=8'h7d; data[59]=8'ha9; data[60]=8'h66; data[61]=8'h23; data[62]=8'h71; data[63]=8'hca;
        data[64]=8'h42; data[65]=8'h5c; data[66]=8'heb; data[67]=8'h7f; data[68]=8'hb0; data[69]=8'he; data[70]=8'h79; data[71]=8'hc8;
        data[72]=8'h8e; data[73]=8'h83; data[74]=8'h47; data[75]=8'h95; data[76]=8'h5d; data[77]=8'h93; data[78]=8'h81; data[79]=8'h14;
        data[80]=8'h64; data[81]=8'h09; data[82]=8'h23; data[83]=8'hf4;
        expected[0]=-15157; expected[1]=-24497; expected[2]=664; expected[3]=-17313;
        expected[4]=32169; expected[5]=26147; expected[6]=29130; expected[7]=16988;
        expected[8]=-5249; expected[9]=-20466; expected[10]=31176; expected[11]=-29053;
        expected[12]=18325; expected[13]=23955; expected[14]=-32492; expected[15]=25609;
        repeat (4) @(posedge clk); rst_n=1;
        for (i=0; i<84; i=i+1) send_byte(data[i]);
        repeat (2000) @(posedge clk);
        if (!format_ready || sample_rate_hz !== 20'd8000 || stereo || bits_per_sample !== 6'd16 ||
            unsupported || error || got != 16 || errors != 0) begin
            $display("tb_tf_flac_pcm_decoder_verbatim: FAIL got=%0d errors=%0d format=%0d rate=%0d unsupported=%0d error=%0d", got, errors, format_ready, sample_rate_hz, unsupported, error);
            $finish;
        end
        $display("PASS tb_tf_flac_pcm_decoder_verbatim: FLAC verbatim PCM16");
        $finish;
    end
endmodule
