`timescale 1ns/1ps
module tb_cache_read_retime;
    parameter integer WORDS=7488;
    reg clk=0,rst_n=0,start=0;
    always #10 clk=~clk;
    reg [17:0] addr=0;
    wire signed [15:0] old_data,new_data;
    wire old_busy,new_busy,old_done,new_done,old_req,new_req,old_wr,new_wr;
    wire [31:0] old_addr,new_addr;
    wire [15:0] old_wdata,new_wdata;
    reg ready=0,rsp=0;
    reg [15:0] data=0;
    integer cycle=0,response=-1,reads=0;
    function automatic [15:0] value(input integer n);value=(n*7919)^16'ha53c;endfunction
    basic_pitch_weight_cache_old #(.MAX_WORDS(WORDS)) old_cache (
        .clk_i(clk),.rst_ni(rst_n),.start_i(start),.blob_word_base_i(15'd17),.word_count_i(WORDS[13:0]),
        .read_addr_i(addr),.read_data_o(old_data),.busy_o(old_busy),.done_o(old_done),
        .mem_req_o(old_req),.mem_write_o(old_wr),.mem_byte_addr_o(old_addr),.mem_wdata_o(old_wdata),
        .mem_ready_i(ready),.mem_rsp_valid_i(rsp),.mem_rdata_i(data));
    basic_pitch_weight_cache #(.MAX_WORDS(WORDS)) new_cache (
        .clk_i(clk),.rst_ni(rst_n),.start_i(start),.blob_word_base_i(15'd17),.word_count_i(WORDS[13:0]),
        .read_addr_i(addr),.read_data_o(new_data),.busy_o(new_busy),.done_o(new_done),
        .mem_req_o(new_req),.mem_write_o(new_wr),.mem_byte_addr_o(new_addr),.mem_wdata_o(new_wdata),
        .mem_ready_i(ready),.mem_rsp_valid_i(rsp),.mem_rdata_i(data));
    always @(negedge clk) begin
        cycle=cycle+1;ready=cycle%7>1;rsp=0;
        if(response>=0)begin
            if(response==0)begin rsp=1;response=-1;end
            else response=response-1;
        end
    end
    always @(posedge clk) if(rst_n)begin
        if({old_busy,old_done,old_req,old_wr,old_addr,old_wdata}!=={new_busy,new_done,new_req,new_wr,new_addr,new_wdata})
            $fatal(1,"cache request/control cadence changed");
        if(old_req && ready)begin
            if(old_addr!==32'h10100000+2*(17+reads%WORDS))$fatal(1,"bad model read address");
            data=value(reads%WORDS);reads=reads+1;response=cycle%5+1;
        end
    end
    task read_at(input integer a);
        begin @(negedge clk);addr=a;@(posedge clk);#1;
            if(old_data!==new_data)$fatal(1,"cache cycle/read differs addr%0d old%h new%h",a,old_data,new_data);
            if(new_data!==(a<WORDS ? value(a) : 16'd0))$fatal(1,"cache value/bounds wrong addr%0d",a);
        end
    endtask
    integer i;
    initial begin
        repeat(5)@(negedge clk);rst_n=1;start=1;@(negedge clk);start=0;
        wait(old_done);@(negedge clk);
        for(i=0;i<WORDS;i=i+1)read_at(i);
        read_at(WORDS);read_at(WORDS+1);read_at(8191);read_at(8192);read_at(262143);
        for(i=0;i<1000;i=i+1)read_at($urandom%262144);
        // Reset cancels load state without clearing RAM/output, just as before.
        @(negedge clk);rst_n=0;repeat(4)@(negedge clk);rst_n=1;
        read_at(0);read_at(WORDS-1);read_at(WORDS);
        $display("PASS cache read retiming words=%0d exact read/control cycles, range, reset; reads=%0d",WORDS,reads);$finish;
    end
    initial begin #10000000;$fatal(1,"cache timeout");end
endmodule
