`timescale 1ns/1ps
`include "basic_pitch_ddr_map.svh"
module tb_cnn_demo_model_boot;
    reg clk=0,rstn=0,corrupt=0;
    always #10 clk=~clk;
    wire req,wr,done;
    wire [31:0] addr,expected,actual;
    wire [15:0] data;
    wire [3:0] status;
    wire [1:0] error;
    reg [15:0] memory[0:52238],oracle[0:52238];
    integer cycles=0,writes=0,reads=0,delay_count=0,pending=-1;
    reg rsp=0; reg [15:0] rdata=0;
    wire ready=rstn && cycles>64 && cycles%7>2 && pending<0 && !rsp;
    workstation_cnn_demo_model_loader dut(.clk_i(clk),.rst_ni(rstn),.serial_i(1'b1),
        .done_o(done),.status_o(status),.debug_expected_crc_o(expected),.debug_actual_crc_o(actual),
        .debug_error_stage_o(error),.mem_req_o(req),.mem_write_o(wr),.mem_byte_addr_o(addr),
        .mem_wdata_o(data),.mem_ready_i(ready),.mem_rsp_valid_i(rsp),.mem_rdata_i(rdata));
    always @(posedge clk) begin
        if(!rstn)begin cycles<=0;writes=0;reads=0;pending=-1;rsp<=0;end
        else begin
            cycles<=cycles+1;rsp<=0;
            if(pending>=0)begin
                if(delay_count==0)begin
                    rdata<=memory[pending] ^ ((corrupt && pending==123) ? 16'h1 : 16'h0);
                    rsp<=1;pending=-1;
                end else delay_count=delay_count-1;
            end
            if(req && ready)begin
                if(addr[0] || addr<`BP_DDR_NN_MODEL_BYTE_BASE ||
                   addr>=`BP_DDR_NN_MODEL_BYTE_BASE+104478)$fatal(1,"bad model address %h",addr);
                if(wr)begin
                    if(addr!=`BP_DDR_NN_MODEL_BYTE_BASE+2*writes || data!==oracle[writes])
                        $fatal(1,"model payload/ordering differs at %0d",writes);
                    memory[writes]=data;writes=writes+1;
                end else begin
                    if(writes!=52239 || addr!=`BP_DDR_NN_MODEL_BYTE_BASE+2*reads)
                        $fatal(1,"early or reordered DDR verification");
                    pending=reads;reads=reads+1;delay_count=cycles%5;
                end
            end
            if(done && (writes!=52239 || reads!=52239 || actual!=32'hAF01A61B))
                $fatal(1,"ready without full model CRC");
            if(cycles>2000000)$fatal(1,"model startup hung");
        end
    end
    wire [3:0] timeout_status;wire timeout_done;wire [1:0] timeout_error;
    workstation_cnn_demo_model_loader #(.WAIT_CYCLES(32)) stalled(
        .clk_i(clk),.rst_ni(rstn),.serial_i(1'b1),.done_o(timeout_done),.status_o(timeout_status),
        .debug_expected_crc_o(),.debug_actual_crc_o(),.debug_error_stage_o(timeout_error),
        .mem_req_o(),.mem_write_o(),.mem_byte_addr_o(),.mem_wdata_o(),
        .mem_ready_i(1'b0),.mem_rsp_valid_i(1'b0),.mem_rdata_i(16'd0));
    initial begin
        $readmemh("rtl/music/weights/cnn_ddr_blob.mem",oracle);
        repeat(8)@(negedge clk);rstn=1;
        wait(done || status==15);@(negedge clk);
        if(!done || actual!=32'hAF01A61B || expected!=32'hAF01A61B || error!=0)
            $fatal(1,"automatic boot failed CRC %h status %h",actual,status);
        if(timeout_status!=15 || timeout_done || timeout_error!=1)$fatal(1,"missing bounded startup failure");
        repeat(32)@(negedge clk);
        if(!done || req)$fatal(1,"verified model did not remain ready");
        rstn=0;corrupt=1;repeat(8)@(negedge clk);rstn=1;
        wait(done || status==15);@(negedge clk);
        if(done || status!=15 || error!=3 || actual==expected)$fatal(1,"DDR corruption accepted");
        $display("PASS embedded model: 52239 exact words, stalled DDR, full AF01A61B readback, corruption rejected, timeout, reset");
        $finish;
    end
endmodule
