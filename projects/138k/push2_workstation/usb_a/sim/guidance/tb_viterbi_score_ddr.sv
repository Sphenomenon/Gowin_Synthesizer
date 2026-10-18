`timescale 1ns/1ps
`include "basic_pitch_ddr_map.svh"
module tb_viterbi_score_ddr;
    reg clk=0,rst_n=0,mem_rsp=0;
    reg [15:0] mem_data=0;
    wire mem_req,mem_write,score_valid,done;
    wire [31:0] mem_addr;
    wire [6:0] score_note;
    integer got=0,reads=0;
    reg [6:0] expected [0:3];
    always #10 clk=~clk;
    basic_pitch_viterbi #(.FRAMES(9),.USE_EXTERNAL_STATE(1'b1)) dut(
        .clk_i(clk),.rst_ni(rst_n),.start_i(1'b0),.active_i(1'b1),
        .note_valid_i(1'b0),.note_idx_i(7'd0),.note_q_i(16'd0),
        .onset_valid_i(1'b0),.onset_idx_i(7'd0),.onset_q_i(16'd0),
        .frame_valid_i(1'b0),.frame_last_i(1'b0),.frame_ready_o(),
        .result_valid_o(),.result_note_o(),.result_conf_o(),.result_frame_o(),
        .score_valid_o(score_valid),.score_ready_i(1'b1),.score_note_o(score_note),
        .done_o(done),.busy_o(),.mem_req_o(mem_req),.mem_write_o(mem_write),
        .mem_byte_addr_o(mem_addr),.mem_wdata_o(),.mem_ready_i(1'b1),
        .mem_rsp_valid_i(mem_rsp),.mem_rdata_i(mem_data));
    always @(posedge clk) if(rst_n)begin
        mem_rsp<=mem_req && !mem_write;
        if(mem_req)begin
            if(mem_write || mem_addr<`BP_DDR_ONSET_BYTE_BASE ||
               mem_addr>=`BP_DDR_ONSET_BYTE_BASE+32'h100000)
                $fatal(1,"unexpected DDR score read %h",mem_addr);
            reads=reads+1;
            mem_data<=mem_addr==`BP_DDR_ONSET_BYTE_BASE+((2*88+39)*2) ? 16'd1 : 16'd0;
        end
        if(score_valid)begin
            if(got>=4 || score_note!==expected[got])$fatal(1,"score[%0d]=%0d",got,score_note);
            got=got+1;
        end
    end
    initial begin
        expected[0]=60;expected[1]=60;expected[2]=62;expected[3]=60;
        repeat(3)@(negedge clk);rst_n=1;
        @(negedge clk);
        dut.path_mem[0]=39;dut.path_mem[1]=39;dut.path_mem[2]=39;
        dut.path_mem[3]=39;dut.path_mem[4]=41;dut.path_mem[5]=41;
        dut.path_mem[6]=88;dut.path_mem[7]=39;dut.path_mem[8]=39;
        dut.frame_cnt=8;dut.cmt_found=1;dut.cmt_note=39;dut.cmt_frame=0;dut.state=9;
        repeat(55)@(negedge clk);
        if(got!=4 || reads!=4 || !done)
            $fatal(1,"DDR score got=%0d reads=%0d done=%b",got,reads,done);
        $display("PASS DDR score: committed first note, 4 onset reads, 4 ordered steps including repeated note");
        $finish;
    end
endmodule
