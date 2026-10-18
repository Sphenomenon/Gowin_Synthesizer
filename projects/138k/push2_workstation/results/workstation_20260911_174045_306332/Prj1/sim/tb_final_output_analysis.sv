`timescale 1ns/1ps
// Final-chain integration: real DAC serialization -> pin observer -> CDC
// capture -> both FFTs and the image. No direct synth tap feeds analysis.
module tb_final_output_analysis;
    reg source_clk=0,clk=0,reset_n=0;
    always #10 source_clk=~source_clk;always #5 clk=~clk;
    reg signed [31:0] sample=0;
    reg valid=0;
    wire tick,bck,ws,din,pcm_valid,ready;
    wire [31:0] pair,ref_word;
    wire [15:0] peak_l,peak_r;
    pt8211_tx #(.BCK_HALF_CYCLES(2)) tx(.clk(source_clk),.reset_n(reset_n),.sample_data(sample),.sample_valid(valid),
        .sample_tick(tick),.hp_bck(bck),.hp_ws(ws),.hp_din(din),.pa_en(),.underrun_count(),.frame_count(),
        .sample_revision(24'd0),.sample_nonzero_voices(32'd1),.trace_dac_done(),.trace_dac_revision(),.trace_dac_nonzero_voices(),
        .sample_trigger_reference(32'd0),.frame_trigger_reference(ref_word));
    pt8211_observer observer(.clk(source_clk),.reset_n(reset_n),.bck(bck),.ws(ws),.din(din),
        .frame_reference(ref_word),.pcm_pair(pair),.sample_valid(pcm_valid),.trigger_reference());
    output_audio_analysis analysis(.clk(clk),.reset_n(reset_n),.source_clk(source_clk),.source_reset_n(reset_n),
        .pcm_pair(pair),.sample_valid(pcm_valid),.release_frame(1'b0),.ready(ready),.peak_left(peak_l),.peak_right(peak_r),
        .image_gain(),.sequence_data(),.skipped_data(),.display_read_enable(1'b0),.spectrum_column(9'd0),.image_addr(16'd0),
        .spectrum_left(),.spectrum_right(),.image_hit());
    integer n=0,k,best=0,height=0,ink=0,observations=0;
    always @(posedge source_clk) if(reset_n && pcm_valid) begin
        if(pair[31:16]!==pair[15:0]) $fatal(1,"mono final output was not identical in L/R");
        observations=observations+1;
    end
    initial begin
        repeat(4) @(negedge source_clk);reset_n=1;
        forever begin
            @(posedge tick);repeat(8) @(negedge source_clk);
            sample=$rtoi(1073741824.0*$sin(6.283185307179586*16*n/1024));valid=1;n=n+1;
            @(negedge source_clk);valid=0;
        end
    end
    initial begin
        wait(ready);#1;
        if(peak_l!=16384 || peak_r!=16384 || observations<1024) $fatal(1,"final PCM peak/cadence incorrect");
        for(k=1;k<512;k=k+1) begin
            if(analysis.levels_left[k]!==analysis.levels_right[k]) $fatal(1,"mono spectra differ");
            if(analysis.levels_left[k]>height) begin height=analysis.levels_left[k];best=k;end
        end
        if(best!=16 || height<207 || height>209) $fatal(1,"serialized-output spectrum incorrect");
        for(k=0;k<65536;k=k+1) if(analysis.image_pixels[k]) begin
            ink=ink+1;if(k%256!=128) $fatal(1,"mono physical output fabricated stereo width");
        end
        if(ink<10) $fatal(1,"no final-output stereo image");
        $display("PASS final output chain: real PT8211 serial PCM -> observer -> asynchronous 1024-pair capture -> calibrated dual FFT and true mono centre image (%0d observed frames)",observations);$finish;
    end
    initial begin #10000000;$fatal(1,"final output analysis timeout");end
endmodule
