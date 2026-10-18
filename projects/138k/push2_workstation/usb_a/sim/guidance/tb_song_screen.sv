`timescale 1ns/1ps
module tb_song_screen;
    reg clk=0,rst=0,name_write_valid=0,chosen=0;
    reg [7:0] name_write_addr=0,name_write_data=0;
    reg [9:0] x=0;
    reg [7:0] y=0;
    wire [15:0] pixel;
    integer i,j,lit;
    always #10 clk=~clk;
    push2_song_screen dut(.clk,.rst,.name_write_valid,.name_write_addr,
        .name_write_data,.chosen,.browse_index(4'd0),.track_index(4'd0),
        .track_count(5'd1),.score_count(16'd3),.cursor(16'd1),
        .analysis_done(1'b1),
        .effect_mask(3'd0),.x,.y,.pixel);
    initial begin
        @(negedge clk);name_write_valid=1;name_write_data="A";
        @(negedge clk);name_write_valid=0;
        lit=0;
        for(j=28;j<42;j=j+1) for(i=32;i<44;i=i+1) begin
            x=i;y=j;#1;if(pixel==16'hffff)lit=lit+1;
        end
        if(lit==0)$fatal(1,"playlist filename not rendered");
        chosen=1;lit=0;
        for(j=32;j<46;j=j+1) for(i=96;i<108;i=i+1) begin
            x=i;y=j;#1;if(pixel==16'hffff)lit=lit+1;
        end
        if(lit==0)$fatal(1,"selected song filename not rendered");
        $display("PASS song filename on list and performance pages");$finish;
    end
endmodule
