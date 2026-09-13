`timescale 1ns/1ps
module tb_output_audio_analysis;
    reg clk=0,source_clk=0,reset_n=0;
    always #5 clk=~clk;
    always #11 source_clk=~source_clk;
    reg [31:0] pcm_pair=0;
    reg sample_valid=0,release_frame=0,rd_en=0;
    reg [8:0] column=0;
    reg [15:0] image_addr=0;
    wire ready,hit;
    wire [15:0] peak_l,peak_r;
    wire [2:0] gain;
    wire [31:0] seq,skipped;
    wire [7:0] spec_l,spec_r;
    output_audio_analysis dut(.clk(clk),.reset_n(reset_n),.source_clk(source_clk),.source_reset_n(reset_n),
        .pcm_pair(pcm_pair),.sample_valid(sample_valid),.release_frame(release_frame),.ready(ready),
        .peak_left(peak_l),.peak_right(peak_r),.image_gain(gain),.sequence_data(seq),.skipped_data(skipped),
        .display_read_enable(rd_en),.spectrum_column(column),.image_addr(image_addr),
        .spectrum_left(spec_l),.spectrum_right(spec_r),.image_hit(hit));
    integer n,l,r,mode,cycles,k,ink,off_axis,best_l,best_r,height_l,height_r;
    integer expected_l_peak,expected_r_peak;
    reg [7:0] stable_level;
    reg [31:0] expected[0:1023];
    localparam real PI=3.14159265358979323846;
    task send_block(input integer kind);
        begin
            expected_l_peak=0; expected_r_peak=0;
            for(n=0;n<1024;n=n+1) begin
                l=$rtoi(16384.0*$sin(2*PI*16*n/1024)); r=l;
                case(kind)
                    0:r=$rtoi(8192.0*$sin(2*PI*37*n/1024));
                    2:r=-l;
                    3:r=0;
                    4:begin r=l; l=0; end
                    5:begin l=0;r=0;end
                    6:begin l=n[0] ? 32767 : -32768;r=-32768;end
                    7:begin l=$rtoi(100.0*$sin(2*PI*16*n/1024));r=l;end
                    8:begin l=$rtoi(16384.0*$sin(2*PI*417*n/1024));r=$rtoi(8192.0*$sin(2*PI*417*n/1024));end
                endcase
                if((l<0?-l:l)>expected_l_peak) expected_l_peak=l<0?-l:l;
                if((r<0?-r:r)>expected_r_peak) expected_r_peak=r<0?-r:r;
                expected[n]={l[15:0],r[15:0]};
                @(negedge source_clk); sample_valid=1;pcm_pair=expected[n];
            end
            @(negedge source_clk);sample_valid=0;
            cycles=0;
            while(!ready) begin @(negedge clk);cycles=cycles+1;if(cycles>160000)$fatal(1,"analysis exceeded latency bound");end
            if(peak_l!==expected_l_peak || peak_r!==expected_r_peak) $fatal(1,"incorrect true PCM peaks");
            best_l=0;best_r=0;height_l=0;height_r=0;
            for(k=1;k<512;k=k+1) begin
                if(dut.levels_left[k]>height_l) begin best_l=k;height_l=dut.levels_left[k];end
                if(dut.levels_right[k]>height_r) begin best_r=k;height_r=dut.levels_right[k];end
            end
            if(kind==0 && (best_l!=16 || best_r!=37 || height_l<207 || height_l>209 || height_r<191 || height_r>193))
                $fatal(1,"independent FFT peaks/calibration: L bin=%0d h=%0d R bin=%0d h=%0d",best_l,height_l,best_r,height_r);
            if(kind==2 && (best_l!=16 || best_r!=16 || height_l<207 || height_r<207))
                $fatal(1,"anti-phase channels cancelled in FFT");
            if(kind==3 && height_r!=0 || kind==4 && height_l!=0 || kind==5 && (height_l!=0 || height_r!=0))
                $fatal(1,"silent channel has nonzero spectrum");
            ink=0;off_axis=0;
            for(k=0;k<65536;k=k+1) if(dut.image_pixels[k]) begin
                ink=ink+1;
                if((kind==1 || kind==7) && k%256!=128) off_axis=off_axis+1;
                if(kind==2 && k/256!=128) off_axis=off_axis+1;
                if(kind==3 && ((k%256)-(k/256)>1 || (k/256)-(k%256)>1)) off_axis=off_axis+1;
                if(kind==4 && ((k%256)+(k/256)<255 || (k%256)+(k/256)>256)) off_axis=off_axis+1;
            end
            if(off_axis || (kind==5 && ink!=0) || (kind!=5 && ink<2)) $fatal(1,"incorrect stereo image kind=%0d ink=%0d off_axis=%0d",kind,ink,off_axis);
            if(kind==7 && gain!=7) $fatal(1,"quiet signal auto gain incorrect");
            // Read ports and results remain stable while the frame is held.
            @(negedge clk);rd_en=1;column=235;image_addr=16'h8080;
            repeat(3) @(negedge clk);
            if(spec_l!==dut.display_left[dut.frequency_bin] || hit!==dut.image_pixels[image_addr]) $fatal(1,"display RAM read mismatch");
            if(kind==8) begin
                // The last two log endpoints are 414 and 419. Bin 417 is
                // invisible to point sampling, but must retain its peak.
                column=511; repeat(3) @(negedge clk);
                if(spec_l<207 || spec_l>209 || spec_r<191 || spec_r>193)
                    $fatal(1,"log-frequency pooling lost high-frequency tone: %0d/%0d",spec_l,spec_r);
            end
            stable_level=spec_l;repeat(20) @(negedge clk);
            if(!ready || spec_l!==stable_level) $fatal(1,"frame did not remain immutable");
            rd_en=0;release_frame=1;@(negedge clk);release_frame=0;repeat(10) @(negedge source_clk);
            $display("ANALYSIS case %0d: FFT bins L=%0d R=%0d levels=%0d/%0d image_points=%0d gain_shift=%0d latency=%0d",kind,best_l,best_r,height_l,height_r,ink,gain,cycles);
        end
    endtask
    initial begin
        repeat(4) @(negedge source_clk);reset_n=1;
        for(mode=0;mode<9;mode=mode+1) send_block(mode);
        reset_n=0;repeat(4) @(negedge clk);
        if(ready) $fatal(1,"analysis ready survived reset");
        $display("PASS final-output analysis: dual 1024-point Hann FFT, calibrated tones, anti-phase energy, mono/left/right/anti-phase images, silence clearing, signed full scale, quiet auto gain, immutable frame and reset");$finish;
    end
    initial begin #30000000;$fatal(1,"analysis test timeout");end
endmodule
