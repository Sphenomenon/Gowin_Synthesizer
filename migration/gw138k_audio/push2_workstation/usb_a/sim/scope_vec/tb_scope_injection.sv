`timescale 1ns/1ps
module tb_scope_injection;
    reg clk=0;always #5 clk=~clk;
    reg rst_n=0,clear=0,valid_in=0;
    reg signed [31:0] x=0,y=0,mono=0,pcm_l=0,pcm_r=0;
    wire ready,valid,clip;
    wire signed [31:0] left,right;
    integer i;
    stereo_effects #(.VECTOR_ENABLE(1),.DELAY_BITS(6),.ECHO_SAMPLES(17),.CHORUS_BASE(5),.CHORUS_DEPTH(2),.COMB_A(13),.COMB_B(19)) dut(
        .clk_i(clk),.rst_ni(rst_n),.clear_i(clear),.valid_i(valid_in),.synth_i(mono),
        .vector_left_i(x),.vector_right_i(y),.pcm_left_i(pcm_l),.pcm_right_i(pcm_r),
        .synth_gain_i(16'd32768),.pcm_gain_i(16'd32768),.effect_mask_i(3'd0),.effect_order_i(6'b10_01_00),
        .ready_o(ready),.valid_o(valid),.left_o(left),.right_o(right),.clip_o(clip));
    task automatic frame;
        begin
            while(!ready)@(negedge clk);
            valid_in=1;@(negedge clk);valid_in=0;
            while(!valid)@(negedge clk);
            if(clip)$fatal(1,"unexpected clipping");
            @(negedge clk);
        end
    endtask
    task automatic check(input integer wanted_l,wanted_r);
        begin frame();if(left!==wanted_l || right!==wanted_r)$fatal(1,"L/R mismatch actual %0d %0d expected %0d %0d",left,right,wanted_l,wanted_r);end
    endtask
    initial begin
        repeat(4)@(negedge clk);rst_n=1;
        repeat(256)frame(); // exact unity gains after P10 slew
        x=32'sd123456789;y=-32'sd23456789;repeat(32)check(123456789,-23456789); // DC
        x=0;y=0;check(0,0);
        x=32'sd1073741824;check(1073741824,0); // impulse only on X
        x=0;repeat(32)check(0,0);
        y=-32'sd1073741824;repeat(32)check(0,-1073741824); // Y step
        for(i=0;i<200;i=i+1)begin
            x=32'(i*1234567);y=-32'(i*765432);mono=12345;pcm_l=6789;pcm_r=-9876;
            check(x+mono+pcm_l,y+mono+pcm_r);
        end
        clear=1;@(negedge clk);clear=0;x=0;y=0;mono=0;pcm_l=0;pcm_r=0;check(0,0);
        $display("PASS scope_injection DC impulse step signed ramp exact dry stereo");$finish;
    end
endmodule
