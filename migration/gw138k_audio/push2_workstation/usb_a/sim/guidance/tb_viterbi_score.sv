`timescale 1ns/1ps
module tb_viterbi_score;
    reg clk=0,rst_n=0,score_ready=0;
    wire score_valid,done;
    wire [6:0] score_note;
    wire [6:0] result_note;
    wire [15:0] result_conf,result_frame;
    wire result_valid;
    integer got=0;
    reg [6:0] expected [0:3];
    always #10 clk=~clk;
    basic_pitch_viterbi #(.FRAMES(9),.USE_EXTERNAL_STATE(1'b0)) dut(
        .clk_i(clk),.rst_ni(rst_n),.start_i(1'b0),.active_i(1'b1),
        .note_valid_i(1'b0),.note_idx_i(7'd0),.note_q_i(16'd0),
        .onset_valid_i(1'b0),.onset_idx_i(7'd0),.onset_q_i(16'd0),
        .frame_valid_i(1'b0),.frame_last_i(1'b0),.frame_ready_o(),
        .result_valid_o(result_valid),.result_note_o(result_note),
        .result_conf_o(result_conf),.result_frame_o(result_frame),
        .score_valid_o(score_valid),.score_ready_i(score_ready),.score_note_o(score_note),
        .done_o(done),.busy_o(),.mem_req_o(),.mem_write_o(),.mem_byte_addr_o(),
        .mem_wdata_o(),.mem_ready_i(1'b0),.mem_rsp_valid_i(1'b0),.mem_rdata_i(16'd0));
    always @(posedge clk) if(rst_n && score_valid && score_ready)begin
        if(got>=4 || score_note!==expected[got])$fatal(1,"score[%0d]=%0d",got,score_note);
        got=got+1;
    end
    initial begin
        expected[0]=60;expected[1]=60;expected[2]=62;expected[3]=60;
        repeat(3)@(negedge clk);rst_n=1;
        @(negedge clk);
        dut.path_mem[0]=39;dut.path_mem[1]=39;dut.path_mem[2]=39;
        dut.path_mem[3]=39;dut.path_mem[4]=41;dut.path_mem[5]=41;
        dut.path_mem[6]=88;dut.path_mem[7]=39;dut.path_mem[8]=39;
        for(integer n=0;n<9;n=n+1)
            dut.onset_hot_mem[n*88+dut.path_mem[n]]=0;
        dut.onset_hot_mem[2*88+39]=1;
        dut.frame_cnt=8;dut.cmt_found=1;dut.cmt_note=39;
        dut.cmt_conf=16'h4000;dut.cmt_frame=0;dut.state=9;
        repeat(4)@(negedge clk);
        if(!score_valid || score_note!=60 || got!=0)
            $fatal(1,"score did not hold during FIFO backpressure");
        score_ready=1;
        repeat(30)@(negedge clk);
        if(got!=4 || !done || !result_valid || result_note!=60)
            $fatal(1,"score/result count=%0d result=%0d",got,result_note);
        $display("PASS Viterbi path: ordered 60,60,62,60; onset repeat; FIFO backpressure; first result retained");
        $finish;
    end
endmodule
