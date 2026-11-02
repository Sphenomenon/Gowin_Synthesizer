`timescale 1ns/1ps
module tb_cnn_demo_song_screen;
    reg clk=0,rst=1,chosen=0;
    reg [31:0] status=0;
    reg [9:0] x=96;
    reg [7:0] y=58;
    wire [15:0] pixel;
    integer i,j,lit;
    always #10 clk=~clk;
    push2_song_screen #(.CNN_DEMO_STATUS_ENABLE(1)) dut(
        .clk,.rst,.chosen,.name_write_valid(1'b0),.name_write_addr(8'd0),
        .name_write_data(8'd0),.browse_index(4'd0),.track_index(4'd0),
        .track_count(5'd0),.score_count(16'd0),.cursor(16'd0),
        .analysis_done(1'b0),.cnn_status_i(status),.effect_mask(3'd0),.x,.y,.pixel);
    initial begin
        #30;rst=0;#1;
        if(dut.state_text!="TF SCANNING     ")$fatal(1,"missing scan status on empty list");
        lit=0;
        for(j=58;j<72;j=j+1)for(i=96;i<288;i=i+1)begin
            x=i;y=j;#1;if(pixel==16'hffff)lit=lit+1;
        end
        if(lit==0)$fatal(1,"empty list status has no rendered pixels");
        status[14]=1;#1;
        if(dut.state_text!="NO MP3 IN ROOT  ")$fatal(1,"completed empty directory not distinguished");
        chosen=1;status=0;#1;
        if(dut.state_text!="AUTO MODEL LOAD ")$fatal(1,"obsolete manual UART instruction");
        status[3]=1;#1;
        if(dut.state_text!="MODEL FAILED    ")$fatal(1,"model failure missing");
        $display("PASS CNN-DEMO empty list renders TF state; automatic model/failure status");
        $finish;
    end
endmodule
