`timescale 1ns/1ps
module tb_tf_flac_pcm_decoder_stereo;
    reg clk = 1'b0;
    always #5 clk = ~clk;

    reg rst_n = 1'b0;
    reg in_valid = 1'b0;
    reg [7:0] in_byte = 8'd0;
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
        .pcm_valid(pcm_valid), .pcm_ready(1'b1),
        .pcm_left(pcm_left), .pcm_right(pcm_right),
        .unsupported(unsupported), .error(error), .frame_count(frame_count)
    );

    reg [7:0] data [0:155];
    reg signed [15:0] expected_left [0:15];
    reg signed [15:0] expected_right [0:15];
    integer i;
    integer got = 0;
    integer errors = 0;

    always @(negedge clk) begin
        if (rst_n && pcm_valid) begin
            if (got >= 16 || pcm_left !== expected_left[got] ||
                pcm_right !== expected_right[got])
                errors = errors + 1;
            got = got + 1;
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
                $display("tb_tf_flac_pcm_decoder_stereo: FAIL input byte=%0d state=%0d bits=%0d target=%0d unsupported=%0d error=%0d",
                         i, dut.state, dut.bits_left, dut.field_target, unsupported, error);
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
        data[12]=8'h00; data[13]=8'h00; data[14]=8'h46; data[15]=8'h00;
        data[16]=8'h00; data[17]=8'h46; data[18]=8'h01; data[19]=8'hf4;
        data[20]=8'h02; data[21]=8'hf0; data[22]=8'h00; data[23]=8'h00;
        data[24]=8'h00; data[25]=8'h10; data[26]=8'h2c; data[27]=8'h8d;
        data[28]=8'ha9; data[29]=8'h85; data[30]=8'hc2; data[31]=8'h8d;
        data[32]=8'h77; data[33]=8'h53; data[34]=8'h7a; data[35]=8'h43;
        data[36]=8'he0; data[37]=8'h35; data[38]=8'he9; data[39]=8'h5f;
        data[40]=8'h54; data[41]=8'h03; data[42]=8'h84; data[43]=8'h00;
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
        data[92]=8'h6c; data[93]=8'h18; data[94]=8'h00; data[95]=8'h00;
        data[96]=8'h3f; data[97]=8'h5c; data[98]=8'h59; data[99]=8'h9c;
        data[100]=8'h3f; data[101]=8'h5e; data[102]=8'h03; data[103]=8'h5e;
        data[104]=8'hc4; data[105]=8'h2b; data[106]=8'h74; data[107]=8'h80;
        data[108]=8'h01; data[109]=8'h5b; data[110]=8'h9b; data[111]=8'hd8;
        data[112]=8'h75; data[113]=8'h6e; data[114]=8'h70; data[115]=8'h00;
        data[116]=8'hab; data[117]=8'h7c; data[118]=8'h7a; data[119]=8'hf8;
        data[120]=8'had; data[121]=8'hea; data[122]=8'h00; data[123]=8'h65;
        data[124]=8'h70; data[125]=8'h23; data[126]=8'h06; data[127]=8'h66;
        data[128]=8'h65; data[129]=8'h52; data[130]=8'h82; data[131]=8'h73;
        data[132]=8'h7e; data[133]=8'hc1; data[134]=8'h00; data[135]=8'h52;
        data[136]=8'h37; data[137]=8'h63; data[138]=8'hd2; data[139]=8'h20;
        data[140]=8'h9d; data[141]=8'h84; data[142]=8'hd8; data[143]=8'h2c;
        data[144]=8'hef; data[145]=8'h00; data[146]=8'h19; data[147]=8'he0;
        data[148]=8'hd8; data[149]=8'h47; data[150]=8'h62; data[151]=8'h22;
        data[152]=8'h16; data[153]=8'h3e; data[154]=8'h0f; data[155]=8'h1d;

        expected_left[0]=0; expected_right[0]=13107;
        expected_left[1]=16220; expected_right[1]=10900;
        expected_left[2]=22940; expected_right[2]=5019;
        expected_left[3]=16222; expected_right[3]=-2552;
        expected_left[4]=4; expected_right[4]=-9262;
        expected_left[5]=-16214; expected_right[5]=-12847;
        expected_left[6]=-22932; expected_right[6]=-12100;
        expected_left[7]=-16212; expected_right[7]=-7271;
        expected_left[8]=8; expected_right[8]=13;
        expected_left[9]=16228; expected_right[9]=7297;
        expected_left[10]=22947; expected_right[10]=12126;
        expected_left[11]=16230; expected_right[11]=12873;
        expected_left[12]=12; expected_right[12]=9288;
        expected_left[13]=-16207; expected_right[13]=2578;
        expected_left[14]=-22924; expected_right[14]=-4993;
        expected_left[15]=-16205; expected_right[15]=-10874;

        repeat (4) @(posedge clk);
        rst_n = 1'b1;
        for (i = 0; i < 156; i = i + 1) send_byte(data[i]);
        repeat (2000) @(posedge clk);
        if (!format_ready || sample_rate_hz !== 20'd8000 || !stereo ||
            bits_per_sample !== 6'd16 || unsupported || error ||
            frame_count == 0 || got != 16 || errors != 0) begin
            $display("tb_tf_flac_pcm_decoder_stereo: FAIL got=%0d errors=%0d format=%0d stereo=%0d unsupported=%0d error=%0d",
                     got, errors, format_ready, stereo, unsupported, error);
            $finish;
        end
        $display("PASS tb_tf_flac_pcm_decoder_stereo: independent stereo via synchronous BSRAM");
        $finish;
    end
endmodule
