`timescale 1ns/1ps
module tb_viterbi_first_alignment;
    reg clk=0,rst_n=0;
    wire score_valid,done,result_valid;
    wire [6:0] score_note,result_note;
    wire [15:0] result_conf,result_frame;
    integer got=0;
    reg [6:0] expected [0:2];
    always #10 clk=~clk;
    basic_pitch_viterbi #(.FRAMES(9),.USE_EXTERNAL_STATE(1'b0)) dut(
        .clk_i(clk),.rst_ni(rst_n),.start_i(1'b0),.active_i(1'b1),
        .note_valid_i(1'b0),.note_idx_i(7'd0),.note_q_i(16'd0),
        .onset_valid_i(1'b0),.onset_idx_i(7'd0),.onset_q_i(16'd0),
        .frame_valid_i(1'b0),.frame_last_i(1'b0),.frame_ready_o(),
        .result_valid_o(result_valid),.result_note_o(result_note),
        .result_conf_o(result_conf),.result_frame_o(result_frame),
        .score_valid_o(score_valid),.score_ready_i(1'b1),.score_note_o(score_note),
        .done_o(done),.busy_o(),.mem_req_o(),.mem_write_o(),.mem_byte_addr_o(),
        .mem_wdata_o(),.mem_ready_i(1'b0),.mem_rsp_valid_i(1'b0),.mem_rdata_i(16'd0));
    always @(posedge clk) if(rst_n && score_valid)begin
        if(got>=3 || score_note!==expected[got])
            $fatal(1,"score[%0d]=%0d expected=%0d",got,score_note,expected[got]);
        got=got+1;
    end
    initial begin
        expected[0]=49;expected[1]=62;expected[2]=60;
        repeat(3)@(negedge clk);rst_n=1;
        @(negedge clk);
        dut.path_mem[0]=15;dut.path_mem[1]=15;
        dut.path_mem[2]=28;dut.path_mem[3]=28;
        dut.path_mem[4]=41;dut.path_mem[5]=41;
        dut.path_mem[6]=88;dut.path_mem[7]=39;dut.path_mem[8]=39;
        for(integer n=0;n<9;n=n+1)
            if(dut.path_mem[n]!=88)
                dut.onset_hot_mem[n*88+dut.path_mem[n]]=0;
        dut.frame_cnt=8;dut.cmt_found=1;dut.cmt_note=28;
        dut.cmt_conf=16'h4000;dut.cmt_frame=2;dut.state=9;
        repeat(30)@(negedge clk);
        if(got!=3 || !done || !result_valid || result_note!=49 || result_frame!=2)
            $fatal(1,"first alignment got=%0d result=%0d frame=%0d",got,result_note,result_frame);
        $display("PASS first score target matches committed MIDI 49 at frame 2; later notes remain ordered");
        $finish;
    end
endmodule
