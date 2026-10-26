`timescale 1ns/1ps
module tb;
    parameter integer ADDRESS_BITS=9;
    parameter real WRITE_HALF=5.0, READ_HALF=7.3;
    localparam integer DEPTH=1<<ADDRESS_BITS;
    reg write_clk=0, read_clk=0, reset_n=0, write_valid=0, read_ready=0, random_mode=0;
    reg [31:0] write_random=32'h1927ab03, read_random=32'hf4c1a0b3;
    integer written=0, received=0, total=0, epoch=0;
    wire [64:0] write_data={1'(written%19==0),32'(epoch),32'(written^32'h9a5f3321)};
    wire write_ready, read_valid, reference_ready, reference_valid;
    wire [64:0] read_data, reference_data;
    reg [64:0] oracle[0:300000];
    always #(WRITE_HALF) write_clk=~write_clk;
    always #(READ_HALF) read_clk=~read_clk;
    music_async_fifo #(.WIDTH(65),.ADDRESS_BITS(ADDRESS_BITS)) reference_fifo (
        write_clk,reset_n,write_valid,reference_ready,write_data,
        read_clk,reset_n,reference_valid,read_ready,reference_data
    );
`ifdef MAPPED_FIFO
    GSR GSR(.GSRI(1'b1));
    workstation_fifo_bram_probe candidate (
        .write_clk(write_clk),.read_clk(read_clk),.reset_n(reset_n),
        .write_valid(write_valid),.read_ready(read_ready),.write_data(write_data),
        .write_ready(write_ready),.read_valid(read_valid),.read_data(read_data)
    );
`else
    music_async_fifo #(.WIDTH(65),.ADDRESS_BITS(ADDRESS_BITS),.RAM_STYLE("block_ram")) candidate (
        write_clk,reset_n,write_valid,write_ready,write_data,
        read_clk,reset_n,read_valid,read_ready,read_data
    );
`endif
    always @(posedge write_clk or negedge reset_n) begin
        if(!reset_n) written=0;
        else begin
            if(write_ready!==reference_ready) $fatal(1,"write acceptance changed");
            if(write_valid && write_ready) begin oracle[written]=write_data;written=written+1;end
        end
    end
    always @(posedge read_clk or negedge reset_n) begin
        if(!reset_n) received=0;
        else begin
            if(read_valid!==reference_valid) $fatal(1,"read visibility changed");
            if(read_valid && read_data!==reference_data) $fatal(1,"show-ahead head changed");
            if(read_valid && read_ready) begin
                if(received>=written || read_data!==oracle[received])
                    $fatal(1,"FIFO order/data changed at %0d",received);
                received=received+1;total=total+1;
            end
        end
    end
    always @(negedge write_clk) if(random_mode) begin
        write_random={write_random[30:0],write_random[31]^write_random[21]^write_random[1]^write_random[0]};
        write_valid=write_random[2:0]!=0;
    end
    always @(negedge read_clk) if(random_mode) begin
        read_random={read_random[30:0],read_random[31]^read_random[21]^read_random[1]^read_random[0]};
        read_ready=read_random[1:0]!=0;
    end
    task restart;
        begin
            reset_n=0;write_valid=0;read_ready=0;random_mode=0;epoch=epoch+1;
            repeat(6) @(negedge write_clk);reset_n=1;
        end
    endtask
    task drain;
        integer budget;
        begin
            random_mode=0;@(negedge write_clk);write_valid=0;@(negedge read_clk);read_ready=1;budget=0;
            while(received!=written) begin
                @(negedge read_clk);budget=budget+1;
                if(budget>DEPTH+100) $fatal(1,"drain timeout");
            end
            repeat(12) @(negedge read_clk);
            if(read_valid) $fatal(1,"not empty after drain");
            read_ready=0;
        end
    endtask
    initial begin
        restart;
        for(integer round_index=0;round_index<4;round_index=round_index+1) begin
            @(negedge write_clk);write_valid=1;read_ready=0;
            repeat(DEPTH+20) @(negedge write_clk);
            if(written-received!=DEPTH || write_ready) $fatal(1,"capacity or full flag changed");
            write_valid=0;drain;
        end
        random_mode=1;repeat(60000) @(negedge write_clk);drain;
        random_mode=1;repeat(5000) @(negedge write_clk);restart;
        random_mode=1;repeat(60000) @(negedge write_clk);drain;
        $display("PASS FIFO storage: depth=%0d transfers=%0d, exact readiness/visibility/head, wrap, stall and reset",DEPTH,total);
        $finish;
    end
    initial begin #10000000;$fatal(1,"timeout");end
endmodule
