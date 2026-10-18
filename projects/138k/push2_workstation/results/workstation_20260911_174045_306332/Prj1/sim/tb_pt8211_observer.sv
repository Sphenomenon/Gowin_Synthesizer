`timescale 1ns/1ps
module tb_pt8211_observer;
    reg clk=0;always #10 clk=~clk;
    reg reset_n=0,valid=0;
    reg actual_done=0;
    reg signed [31:0] sample=0;
    reg [31:0] reference=0;
    wire tick,bck,ws,din,observed_valid;
    wire [31:0] pair,observed_reference,frame_reference;
    pt8211_tx #(.BCK_HALF_CYCLES(2)) tx(.clk(clk),.reset_n(reset_n),.sample_data(sample),.sample_valid(valid),
        .sample_tick(tick),.hp_bck(bck),.hp_ws(ws),.hp_din(din),.pa_en(),.underrun_count(),.frame_count(),
        .sample_revision(reference[31:8]),.sample_nonzero_voices(32'd0),.trace_dac_done(),.trace_dac_revision(),.trace_dac_nonzero_voices(),
        .sample_trigger_reference(reference),.frame_trigger_reference(frame_reference));
    pt8211_observer observer(.clk(clk),.reset_n(reset_n),.bck(bck),.ws(ws),.din(din),
        .frame_reference(frame_reference),.pcm_pair(pair),.sample_valid(observed_valid),.trigger_reference(observed_reference));
    reg [31:0] pin_shift=0,expected_pair=0,expected_reference=0;
    integer bit_count=0,wire_frames=0,observed_frames=0,zeros=0,nonzeros=0;
    // Independent receiver reconstructs the physical pins at BCK edges.
    always @(posedge bck) if(reset_n) begin
        #1;
        if(ws !== (bit_count>=16)) $fatal(1,"physical slot polarity");
        pin_shift={pin_shift[30:0],din};
        if(bit_count==31) begin
            expected_pair={pin_shift[15:0],pin_shift[31:16]};expected_reference=frame_reference;
            wire_frames=wire_frames+1;
        end
        bit_count=(bit_count+1)%32;
    end
    always @(negedge clk) if(reset_n && observed_valid) begin
        if(wire_frames!=observed_frames+1 || pair!==expected_pair || observed_reference!==expected_reference)
            $fatal(1,"observer differs from final serial PCM or its frame tag");
        observed_frames=observed_frames+1;
        if(pair==0) zeros=zeros+1;else nonzeros=nonzeros+1;
    end
    integer n;
    initial begin
        repeat(4) @(negedge clk);reset_n=1;
        for(n=0;n<12;n=n+1) begin
            @(posedge tick);repeat(8) @(negedge clk);
            case(n%6)
                0:sample=32'h7fffffff;
                1:sample=32'h80000000;
                2:sample=32'h00008000;
                3:sample=32'hffff8000;
                4:sample=32'h12345678;
                5:sample=32'hffffffff;
            endcase
            reference={24'd100+n[23:0],8'h03};valid=1;
            @(negedge clk);valid=0;
        end
        repeat(4) @(posedge tick);repeat(5) @(negedge clk);
        if(zeros<3 || nonzeros<9 || observed_frames<14) $fatal(1,"missing rounded PCM/startup/underrun cases");
        actual_done=1;
    end
    reg synthetic_bck=0,synthetic_ws=1,synthetic_din=0;
    wire synthetic_valid;
    wire [31:0] synthetic_pair;
    reg [31:0] sent_pair;
    integer synthetic_count=0;
    pt8211_observer stereo(.clk(clk),.reset_n(reset_n),.bck(synthetic_bck),.ws(synthetic_ws),.din(synthetic_din),
        .frame_reference(32'd0),.pcm_pair(synthetic_pair),.sample_valid(synthetic_valid),.trigger_reference());
    always @(negedge clk) if(synthetic_valid) begin
        if(synthetic_pair!==sent_pair) $fatal(1,"left/right slot reconstruction or signed PCM incorrect");
        synthetic_count=synthetic_count+1;
    end
    task send_word(input [15:0] value,input bit left_slot);
        integer k;
        begin
            for(k=15;k>=0;k=k-1) begin
                @(negedge clk);synthetic_bck=0;synthetic_ws=left_slot;synthetic_din=value[k];
                repeat(2) @(negedge clk);synthetic_bck=1;
                repeat(2) @(negedge clk);
            end
        end
    endtask
    integer j;
    initial begin
        wait(reset_n);
        for(j=0;j<8;j=j+1) begin
            sent_pair={16'h8000+j[15:0],16'h7000-j[15:0]};
            send_word(sent_pair[15:0],0);send_word(sent_pair[31:16],1);
            repeat(3) @(negedge clk);
        end
        wait(actual_done);repeat(3) @(negedge clk);
        if(synthetic_count!=8) $fatal(1,"missing distinct stereo pairs");
        reset_n=0;repeat(3) @(negedge clk);
        if(observed_valid || synthetic_valid) $fatal(1,"observer valid survived reset");
        $display("PASS PT8211 final-output observer: %0d physical frames, exact rounded/saturated PCM, startup and underrun zeros, aligned trigger tags, 8 independent stereo pairs and reset",observed_frames);$finish;
    end
    initial begin #1000000;$fatal(1,"observer timeout");end
endmodule
