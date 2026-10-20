`timescale 1ns/1ps
module tb_mmio_pipeline;
    reg clk=0,rn=0,sel=0,wr=0,stream=0,start=0,block_slave=0;
    always #5 clk=~clk;
    reg [7:0] addr=0;reg [31:0] wd=0;
    wire ready,msel,mwr,mready,pixel_read,active,done,push;
    wire [7:0] maddr,byte_data;wire [31:0] rd,mwd,mrd;
    integer cycles=0,commits=0,responses=0,pixel_index=0,bytes_seen=0;
    reg [31:0] memory[0:63];reg [31:0] want;
    reg [31:0] random_state=32'h9e3779b9;
    wire upstream=stream ? pixel_read : sel;
    assign mready=!block_slave && (cycles%11==0 || cycles%11>=5);
    assign mrd=stream ? {16'd0,16'(pixel_index*271+7)} : memory[maddr[7:2]];
    gw138k_mmio_pipeline dut(.clk(clk),.reset_n(rn),.select_i(upstream),.write_i(stream?1'b0:wr),
        .address_i(stream?8'h2c:addr),.wdata_i(wd),.ready_o(ready),.rdata_o(rd),
        .select_o(msel),.write_o(mwr),.address_o(maddr),.wdata_o(mwd),.ready_i(mready),.rdata_i(mrd));
    push2_screen_fifo_streamer screen(.clk(clk),.reset_n(rn),.start(start),
        .pixel_read(pixel_read),.pixel_ready(ready),.pixel_data(rd),
        .fifo_push(push),.fifo_data(byte_data),.active(active),.done(done));
    reg was_stalled=0,previous_wr;reg [7:0] previous_addr;reg [31:0] previous_wd;
    reg [15:0] encoded;
    always @(posedge clk)begin
        cycles<=cycles+1;
        if(!rn)begin was_stalled<=0;end
        else begin
            if(was_stalled && {msel,mwr,maddr,mwd}!=={1'b1,previous_wr,previous_addr,previous_wd})
                $fatal(1,"request changed during downstream stall");
            was_stalled<=msel && !mready;previous_wr<=mwr;previous_addr<=maddr;previous_wd<=mwd;
            if(msel && mready)begin
                commits<=commits+1;
                if(stream)begin
                    if(mwr || maddr!=8'h2c)$fatal(1,"bad screen request");
                    pixel_index<=pixel_index+1;
                end else if(mwr)memory[maddr[7:2]]<=mwd;
            end
            if(upstream && ready)responses<=responses+1;
            if(push)begin
                encoded=16'((bytes_seen/2)*271+7)^((bytes_seen/2)%2 ? 16'hffe7 : 16'hf3e7);
                if(byte_data!==(bytes_seen%2 ? encoded[15:8] : encoded[7:0]))$fatal(1,"screen byte %0d",bytes_seen);
                bytes_seen<=bytes_seen+1;
            end
        end
    end
    task automatic transaction;
        integer before_commit,before_response,waits;
        begin
            @(negedge clk);before_commit=commits;before_response=responses;
            random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
            sel=1;wr=random_state[0];addr={random_state[7:2],2'b00};wd=random_state;
            want=memory[addr[7:2]];waits=0;
            while(!ready)begin @(negedge clk);waits++;if(waits>20)$fatal(1,"bus timeout");end
            if(commits!=before_commit+1)$fatal(1,"missing or repeated downstream commit");
            if(!wr && rd!==want)$fatal(1,"read mismatch");
            @(negedge clk);sel=0;
            if(responses!=before_response+1)$fatal(1,"response repeated");
        end
    endtask
    integer i,commits_before_reset;
    initial begin
        for(i=0;i<64;i++)memory[i]=32'(i)*32'h10204081;
        repeat(6)@(negedge clk);rn=1;
        for(i=0;i<2500;i++)transaction();
        // Reset drops a captured request while the downstream is stalled.
        @(negedge clk);block_slave=1;sel=1;wr=1;addr=0;wd=32'hdeadbeef;
        commits_before_reset=commits;
        repeat(3)@(negedge clk);
        if(!msel || ready || commits!=commits_before_reset)$fatal(1,"missing stalled reset fixture");
        rn=0;sel=0;repeat(3)@(negedge clk);rn=1;block_slave=0;
        repeat(4)@(negedge clk);
        if(msel || ready || commits!=commits_before_reset)$fatal(1,"stale transaction after reset");
        @(negedge clk);stream=1;start=1;
        @(negedge clk);start=0;
        wait(done);@(negedge clk);
        if(bytes_seen!=512 || pixel_index!=256)$fatal(1,"incomplete screen block");
        repeat(5)@(negedge clk);
        if(commits!=responses)$fatal(1,"unpaired final transaction");
        $display("PASS mmio_pipeline: 2500 CPU reads/writes, random stalls, reset of pending request, stable request, exactly once commit/response, 256 pixels/512 encoded bytes");
        $finish;
    end
    initial begin #2000000;$fatal(1,"MMIO pipeline test timeout");end
endmodule
