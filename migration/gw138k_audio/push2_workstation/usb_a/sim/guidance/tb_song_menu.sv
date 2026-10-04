`timescale 1ns/1ps
module tb_song_menu;
    reg clk=0,rst=1,toggle=0,mode=0,prev=0,next=0,select_key=0;
    reg [4:0] track_count=3;
    wire chosen,launch;
    wire [3:0] browse,track;
    always #10 clk=~clk;
    push2_song_menu dut(.clk,.rst,.toggle,.mode,.prev,.next,.select_key,
        .track_count,.chosen,.browse_index(browse),.track_index(track),.launch);
    task pulse(input integer which);
        begin
            @(negedge clk);case(which)0:toggle=1;1:prev=1;2:next=1;3:select_key=1;endcase
            @(negedge clk);toggle=0;prev=0;next=0;select_key=0;
        end
    endtask
    initial begin
        repeat(3)@(negedge clk);rst=0;mode=1;
        pulse(0);pulse(1);
        if(browse!=0)$fatal(1,"previous underflow");
        pulse(2);pulse(2);pulse(2);
        if(browse!=2)$fatal(1,"next overflow %0d",browse);
        pulse(3);
        if(!chosen || track!=2 || !launch)$fatal(1,"selection failed");
        @(negedge clk);
        if(launch)$fatal(1,"launch not one cycle");
        pulse(3);
        if(chosen || browse!=2)$fatal(1,"return to list failed");
        pulse(1);pulse(3);
        if(!chosen || track!=1 || !launch)$fatal(1,"second selection failed");
        @(negedge clk);track_count=0;
        repeat(2)@(negedge clk);
        if(chosen || browse!=0 || track!=0 || launch)
            $fatal(1,"card removal retained stale selection");
        track_count=2;
        pulse(2);pulse(3);
        if(!chosen || track!=1 || !launch)$fatal(1,"selection after reinsertion failed");
        $display("PASS song menu bounds, invalidation, reinsertion");$finish;
    end
endmodule
