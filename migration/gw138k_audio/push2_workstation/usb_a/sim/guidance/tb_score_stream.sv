`timescale 1ns/1ps
module tb_score_stream;
    reg clk=0,rst=1,score_valid=0,toggle=0,played_valid=0,clear_i=0;
    reg [6:0] score_note=0,played_note=0;
    wire score_ready,mode,target_valid;
    wire [6:0] target_note;
    wire [15:0] score_count,cursor,wrong_count;
    wire [63:0] guide_mask;
    always #10 clk=~clk;
    push2_score_guide dut(.clk,.rst,.score_valid,.score_ready,.score_note,
        .toggle,.selected_i(1'b1),.clear_i,.played_valid,.played_note,
        .mode,.target_valid,.target_note,.score_count,.cursor,.wrong_count,.guide_mask);
    function automatic [6:0] note_at(input integer i);
        note_at=7'(36+(i%64));
    endfunction
    task automatic put(input integer i);
        @(negedge clk);
        if (!score_ready) $fatal(1,"unexpected full at %0d",i);
        score_note=note_at(i);score_valid=1;
        @(negedge clk);score_valid=0;
    endtask
    task automatic play(input integer i);
        @(negedge clk);
        if (!target_valid || target_note!==note_at(i))
            $fatal(1,"target[%0d] got=%0d valid=%b",i,target_note,target_valid);
        played_note=note_at(i);played_valid=1;
        @(negedge clk);played_valid=0;
    endtask
    initial begin
        repeat(3) @(negedge clk);rst=0;
        @(negedge clk);toggle=1;
        @(negedge clk);toggle=0;
        for(integer i=0;i<172;i=i+1) put(i);
        if(score_ready || score_count!=172 || cursor!=0)
            $fatal(1,"queue did not stop at 172");
        for(integer i=0;i<88;i=i+1) begin
            play(i);
            put(i+172);
        end
        if(score_ready || score_count!=260 || cursor!=88)
            $fatal(1,"queue did not wrap count=%0d cursor=%0d",score_count,cursor);
        for(integer i=88;i<260;i=i+1) play(i);
        if(!score_ready || target_valid || cursor!=260 || score_count!=260)
            $fatal(1,"final cursor/count incorrect");
        @(negedge clk);clear_i=1;
        @(negedge clk);clear_i=0;
        if(target_valid || score_count!=0 || cursor!=0)
            $fatal(1,"new song retained stale targets");
        @(negedge clk);score_note=7'd61;score_valid=1;
        @(negedge clk);score_valid=0;
        if(!target_valid || target_note!=7'd61)
            $fatal(1,"new song target incorrect");
        $display("PASS score stream: 260 ordered targets, wrap, backpressure and new-song clear");
        $finish;
    end
endmodule
