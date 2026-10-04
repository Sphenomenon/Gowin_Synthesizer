`timescale 1ns/1ps
module tb_playlist_hold;
    reg clk=0,rst=0;
    reg word_valid=0;
    reg [15:0] word=0;
    wire [4:0] track_count;
    always #10 clk=~clk;
    push2_playlist_hold #(.HOLD_CYCLES(27'd50)) dut(
        .clk(clk),.reset_n(rst),.word_valid(word_valid),.word(word),
        .track_count(track_count));
    task send(input [15:0] w);
        begin
            @(negedge clk);word_valid=1;word=w;
            @(negedge clk);word_valid=0;word=16'h0000;
        end
    endtask
    initial begin
        repeat(2) @(negedge clk);rst=1;
        repeat(2) @(negedge clk);
        if(track_count!=0) $fatal(1,"reset count not zero");
        send({8'hff,3'd0,5'd7});
        @(negedge clk);
        if(track_count!=5'd7) $fatal(1,"count word not adopted %0d",track_count);
        send(16'hff00);
        repeat(20) @(negedge clk);
        if(track_count!=5'd7)
            $fatal(1,"hold did not keep count during rescan %0d",track_count);
        send({8'hff,3'd0,5'd7});
        repeat(60) @(negedge clk);
        if(track_count!=5'd7)
            $fatal(1,"restored count was dropped after the hold window");
        send(16'hff00);
        repeat(45) @(negedge clk);
        if(track_count!=5'd7) $fatal(1,"count dropped before hold expired");
        repeat(15) @(negedge clk);
        if(track_count!=0) $fatal(1,"confirmed loss did not clear count");
        send({8'hff,3'd0,5'd0});
        repeat(10) @(negedge clk);
        if(track_count!=0) $fatal(1,"empty list grew a count");
        $display("PASS tb_playlist_hold");$finish;
    end
endmodule
