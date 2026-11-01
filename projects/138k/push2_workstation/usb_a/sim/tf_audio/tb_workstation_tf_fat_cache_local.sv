`timescale 1ns/1ps
module tb_workstation_tf_fat_cache_local;
    reg clk=0;always #5 clk=~clk;
    reg rst=0,invalidate=0,fill_start=0,byte_valid=0,fill_done=0,lookup_request=0;
    reg [31:0] fill_lba=0,lookup_lba=0;
    reg [8:0] byte_index=0;
    reg [7:0] value=0;
    reg [6:0] lookup_word=0;
    wire hit,result_valid;
    wire [31:0] result;
    integer checks=0,i;
    workstation_tf_fat_sector_cache_v1 dut(
        .clk_i(clk),.rst_ni(rst),.invalidate_i(invalidate),.fill_start_i(fill_start),
        .fill_lba_i(fill_lba),.fill_byte_valid_i(byte_valid),.fill_byte_index_i(byte_index),
        .fill_byte_i(value),.fill_done_i(fill_done),.lookup_lba_i(lookup_lba),
        .lookup_word_i(lookup_word),.lookup_request_i(lookup_request),
        .lookup_hit_o(hit),.lookup_valid_o(result_valid),.lookup_data_o(result));
    function automatic [7:0] pattern(input integer lba,index);
        pattern=8'(index*13+lba*7+49);
    endfunction
    function automatic [31:0] oracle(input integer lba,word_index);
        integer b;begin oracle=0;for(b=0;b<4;b=b+1)oracle[b*8+:8]=pattern(lba,word_index*4+b);end
    endfunction
    task step;@(negedge clk);endtask
    task check(input reg ok,input string text);begin checks=checks+1;if(!ok)$fatal(1,"%s",text);end endtask
    task begin_fill(input integer lba);begin
        fill_lba=32'(lba);fill_start=1;step();fill_start=0;
    end endtask
    task bytes(input integer lba,first,count);integer b;begin
        for(b=first;b<first+count;b=b+1)begin
            byte_valid=1;byte_index=9'(b);value=pattern(lba,b);step();
        end
        byte_valid=0;
    end endtask
    task finish_fill;begin fill_done=1;step();fill_done=0;end endtask
    task query(input integer lba,index,input reg expected_hit);begin
        lookup_lba=32'(lba);lookup_word=7'(index);lookup_request=1;#1;
        check(hit===expected_hit,"cache LBA hit mismatch");step();
        check(result_valid===expected_hit,"cache result validity mismatch");
        if(expected_hit)check(result===oracle(lba,index),"cache lookup oracle mismatch");
        lookup_request=0;step();check(!result_valid,"lookup result replayed");
    end endtask
    initial begin
        step();step();rst=1;step();
        begin_fill(1);bytes(1,0,512);lookup_lba=1;#1;
        check(!hit,"incomplete CRC-boundary publication");finish_fill();
        for(i=0;i<128;i=i+1)query(1,i,1);
        query(2,0,0);
        // A second miss evicts before any replacement byte; short and
        // out-of-order fills never become readable even after a done pulse.
        begin_fill(257);lookup_lba=1;#1;check(!hit,"replacement retained old valid key");
        bytes(257,0,511);finish_fill();lookup_lba=257;#1;
        check(!hit,"short fill published");
        begin_fill(257);bytes(257,0,5);bytes(257,6,506);finish_fill();#1;
        check(!hit,"unordered fill published");
        begin_fill(257);bytes(257,0,512);finish_fill();query(257,127,1);query(1,127,0);
        // Cancel a pending lookup and valid line on the same edge.
        lookup_lba=257;lookup_word=3;lookup_request=1;step();check(result_valid,"pending lookup absent");
        invalidate=1;#1;check(!hit && !result_valid,"lifecycle fence was not immediate");step();
        invalidate=0;lookup_request=0;step();query(257,3,0);
        // Cancel an in-flight fill; neither its late data nor done may revive it.
        begin_fill(2);bytes(2,0,255);invalidate=1;step();invalidate=0;
        bytes(2,255,257);finish_fill();query(2,0,0);
        // Error/new-task fence wins the complete-success publication edge.
        begin_fill(2);bytes(2,0,512);invalidate=1;fill_done=1;step();
        invalidate=0;fill_done=0;finish_fill();query(2,0,0);
        // A new fill wins an old completion pulse, requiring all new bytes.
        fill_lba=3;fill_start=1;fill_done=1;step();fill_start=0;fill_done=0;
        lookup_lba=3;#1;check(!hit,"late done authorized new fill");
        bytes(3,0,512);finish_fill();query(3,0,1);
        rst=0;step();rst=1;step();finish_fill();query(3,0,0);
        $display("PASS fat_cache_local checks=%0d",checks);$finish;
    end
    initial begin #1000000;$fatal(1,"local cache test timeout");end
endmodule
