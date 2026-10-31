`timescale 1ns/1ps
module tb_ble_record_data_words;
    reg clk=0;always #5 clk=~clk;
    reg rst=0,owner_reset=1,valid=0,write=0,engine_done=0;
    reg [7:0] address=0;reg [31:0] data=0;reg [3:0] strobes=15;
    wire ready,error,start;wire [31:0] response;wire [127:0] active_payload;
    reg [383:0] engine_result=0,expected_result;
    reg [127:0] expected_payload;
    integer vector,word,lane,checks=0;
    workstation_ble_record_data_service dut(
        .clk_i(clk),.rst_ni(rst),.owner_reset_ni(owner_reset),
        .command_valid_i(valid),.command_write_i(write),.command_address_i(address),
        .command_data_i(data),.command_strobes_i(strobes),.command_ready_o(ready),
        .response_error_o(error),.response_data_o(response),.request_admitted_i(1'b0),
        .engine_idle_i(1'b1),.engine_start_o(start),.engine_payload_o(active_payload),
        .engine_done_i(engine_done),.engine_status_i(8'd0),.engine_length_i(7'd48),
        .engine_result_i(engine_result),.engine_time_ms_i(32'd0),.engine_block_crc_i(32'd0),
        .engine_block_crc_valid_i(1'b0),.engine_read_accepted_i(1'b0));
    task check(input condition,input [511:0] message);
        begin checks=checks+1;if(!condition)$fatal(1,"%0s",message);end
    endtask
    task wr(input [7:0] at,input [31:0] value,input expected_error);
        begin
            @(negedge clk);valid=1;write=1;address=at;data=value;#1;
            check(ready && error===expected_error,"write ABI preserves ready/error");
            @(posedge clk);#1;@(negedge clk);valid=0;write=0;
        end
    endtask
    initial begin
        repeat(3)@(posedge clk);@(negedge clk);rst=1;
        for(vector=0;vector<8;vector=vector+1)begin
            wr('h58,vector+1,0);wr('h60,8'h31,0);wr('h64,16,0);
            wr('h68,vector+1,0);wr('h6c,32'h87654321,0);wr('h70,32'h12345678,0);
            for(word=0;word<4;word=word+1)begin
                expected_payload[word*32+:32]=32'hfedcba98^(vector*32'h01020408)^(word*32'h12345679);
                wr('h74+word*4,expected_payload[word*32+:32],0);
                for(lane=1;lane<4;lane=lane+1)wr('h74+word*4+lane,0,1);
                strobes=7;wr('h74+word*4,0,1);strobes=15;
            end
            wr('h84,0,1);wr('h08,1,0);
            check(start && active_payload===expected_payload,"all four staging words reach one immutable descriptor");
            for(word=0;word<4;word=word+1)wr('h74+word*4,32'hbad00000+word,0);
            check(active_payload===expected_payload,"later staging cannot change active words");
            for(word=0;word<12;word=word+1)
                expected_result[word*32+:32]=32'h89abcdef^(vector*32'h01030507)^(word*32'h12345679);
            @(negedge clk);engine_result=expected_result;engine_done=1;
            @(posedge clk);#1;@(negedge clk);engine_done=0;engine_result=0;valid=1;write=0;
            for(word=0;word<12;word=word+1)begin
                address='h90+word*4;#1;
                check(ready && !error && response===expected_result[word*32+:32],
                    "all twelve immutable result words preserve order and every bit");
                for(lane=1;lane<4;lane=lane+1)begin
                    address='h90+word*4+lane;#1;check(ready && error,"every unaligned result address is rejected");
                end
            end
            address='h8f;#1;check(error,"result lower boundary rejects unaligned predecessor");
            address='hbd;#1;check(error,"result upper boundary rejects unaligned successor");valid=0;
        end
        $display("PASS physical payload word ABI: %0d checks",checks);$finish;
    end
    initial begin #100000;$fatal(1,"word ABI test timeout");end
endmodule
