`timescale 1ns/1ps
module tb_pitch_committed_glide;
    reg clk=0,rst=0,commit=0,lifecycle=0,ce=0,rate44=0;
    always #5 clk=~clk;
    reg [3:0] kind=2;
    reg [6:0] address=5,value=0;
    reg [21:0] target=1179648;
    wire [15:0] step;
    wire [20:0] coefficient;
    wire [21:0] ratio;
    workstation_parameters owner(
        .clk_i(clk),.rst_ni(rst),.commit_i(commit),.lifecycle_i(lifecycle),
        .mode_applied_i(1'b0),.kind_i(kind),.address_i(address),.value_i(value),.mode_i(2'd0),
        .legacy_active_i(32'd0),.vector_active_i(8'd0),.cue_running_i(1'b0),
        .glide_step_o(step),.glide_div147_o(coefficient)
    );
    workstation_rate_pitch_expression #(.COMMITTED_GLIDE_COEFFICIENT(1)) dut(
        .clk_i(clk),.rst_ni(rst),.sample_ce_i(ce),.rate_44k1_i(rate44),
        .target_ratio_q20_i(target),.glide_step_q20_i(step),.glide_div147_i(coefficient),
        .vibrato_depth_i(7'd0),.ratio_q20_o(ratio)
    );
    longint unsigned model=1048576,fraction=73,numerator,increment;
    integer samples=0,commits=0,expected_step=0;
    always @(posedge clk) begin
        if(!rst)begin model=1048576;fraction=73;end
        else begin
            if(ratio!==22'(model))$fatal(1,"committed pitch mismatch before sample=%0d",samples);
            if(ce)begin
                numerator=160*longint'(expected_step)+fraction;
                increment=rate44 ? numerator/147:longint'(expected_step);
                if(rate44 && expected_step!=0)fraction=numerator%147;
                if(expected_step==0)model=longint'(target);
                else if(longint'(target)>model)begin
                    if(longint'(target)-model>increment)model+=increment;else model=longint'(target);
                end else begin
                    if(model-longint'(target)>increment)model-=increment;else model=longint'(target);
                end
                samples++;
            end
            #1;
            if(ratio!==22'(model))$fatal(1,"committed pitch mismatch after sample=%0d",samples);
        end
    end
    initial begin
        repeat(4)@(negedge clk);rst=1;
        // All real CC5 values, both directions and rates. The parameter
        // commit is the very last edge before each first sample capture.
        for(integer r=0;r<3;r++)begin
            rate44=(r==1);
            for(integer cc=0;cc<128;cc++)begin
                value=7'(cc);address=5;kind=2;commit=1;
                @(negedge clk);commit=0;commits++;
                expected_step=cc==0 ? 0:256-2*cc;
                if(step!==16'(expected_step))$fatal(1,"CC5 application mismatch");
                if(147*int'(coefficient[20:8])+int'(coefficient[7:0])!=13*expected_step || coefficient[7:0]>=147)
                    $fatal(1,"coefficient not committed atomically with CC5");
                target=cc[0] ? 1179648:917504;
                ce=1;
                repeat(7)@(negedge clk);
                ce=0;address=1;value=37;commit=1;lifecycle=1;
                @(negedge clk);commit=0;lifecycle=0;
                if(step!==16'(expected_step) || 147*int'(coefficient[20:8])+int'(coefficient[7:0])!=13*expected_step)
                    $fatal(1,"unrelated/lifecycle changed committed glide");
                @(negedge clk);
            end
        end
        if(samples!=2688 || commits!=384)$fatal(1,"coverage missing");
        $display("PASS committed glide: commits=%0d samples=%0d all128_CC5 rates48_44_48 last_edge_commit",commits,samples);
        $finish;
    end
    initial begin #1000000;$fatal(1,"timeout");end
endmodule
