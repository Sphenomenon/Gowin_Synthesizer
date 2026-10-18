`timescale 1ns/1ps
module tb_ddr_read_credit;
    parameter integer SEED=7;
    reg clk=0,rclk=0,rst=0,consume=0,auto_consume=0;
    always #5 clk=~clk;
    always #7 rclk=~rclk;
    reg req=0,wr=0;
    reg [31:0] addr=32'h10100000;
    reg [15:0] value=0;
    wire ready,rsp,credit,fifo_ready,rv;
    wire [15:0] result,received;
    wire dreq,dwrite;wire [28:0] daddr;wire [255:0] data;wire [31:0] mask;
    reg native_ready=1,native_response=0;
    reg [255:0] native_data=0;
    integer reads=0,writes=0,commits=0,consumed=0,wait_cycles=0;
    integer countdown=0,delay_cfg=1;
    reg [28:0] outstanding_addr=0;
    reg [15:0] expected[0:20000];
    reg [31:0] random_state=SEED;
    basic_pitch_ddr_read_credit guard(.clk_i(clk),.rst_ni(rst),
        .fifo_ready_i(fifo_ready),.read_accept_i(ready && !wr),
        .response_valid_i(rsp),.credit_o(credit));
    basic_pitch_ddr16_port port(.clk_i(clk),.rst_ni(rst),
        .req_valid_i(req && (wr || credit)),.req_write_i(wr),
        .req_byte_addr_i(addr),.req_wdata_i(value),.req_ready_o(ready),
        .rsp_valid_o(rsp),.rsp_rdata_o(result),.ddr_req_o(dreq),
        .ddr_write_o(dwrite),.ddr_address_o(daddr),.ddr_data_o(data),.ddr_mask_o(mask),
        .ddr_ready_i(native_ready),.ddr_response_i(native_response),.ddr_read_data_i(native_data));
    music_async_fifo #(.WIDTH(16),.ADDRESS_BITS(2)) fifo(
        .write_clk_i(clk),.write_rst_ni(rst),.write_valid_i(rsp),
        .write_ready_o(fifo_ready),.write_data_i(result),
        .read_clk_i(rclk),.read_rst_ni(rst),.read_valid_o(rv),
        .read_ready_i(consume),.read_data_o(received));
    always @(posedge clk) begin
        if(!rst)begin countdown<=0;native_response<=0;reads=0;writes=0;commits=0;end
        else begin
            native_response<=0;
            if(countdown>0)begin
                countdown<=countdown-1;
                if(countdown==1)begin
                    native_response<=1;
                    for(integer k=0;k<16;k=k+1)native_data[k*16+:16]<=((outstanding_addr<<1)+k)^16'h5a00;
                end
            end
            if(rsp)begin
                if(!fifo_ready)$fatal(1,"FIFO overflow despite reservation");
                commits=commits+1;
            end
            if(ready)begin
                if(!dreq || !native_ready)$fatal(1,"false acceptance");
                if(wr)begin
                    if(mask !== ~(32'd3 << (addr[4:1]*2)))$fatal(1,"write mask changed");
                    if(data[addr[4:1]*16+:16] !== value)$fatal(1,"write data changed");
                    writes=writes+1;
                end else begin
                    if(!credit || countdown!=0 || native_response)$fatal(1,"unreserved/concurrent read");
                    expected[reads]=addr[16:1]^16'h5a00;reads=reads+1;
                    countdown<=delay_cfg;outstanding_addr<=daddr;
                end
            end
        end
    end
    always @(posedge rclk)begin
        if(!rst)consumed=0;
        else if(rv && consume)begin
            if(consumed>=reads || received!==expected[consumed])$fatal(1,"response duplicated/lost/reordered at %0d got%h expected%h",consumed,received,expected[consumed]);
            consumed=consumed+1;
        end
    end
    task cycle;begin @(posedge clk);#1;end endtask
    task transact(input bit iswrite,input integer index);
        integer watchdog;
        begin
            @(negedge clk);req=1;wr=iswrite;addr=32'h10100000+index*2;value=index^16'ha55a;
            watchdog=0;
            do begin @(posedge clk);watchdog=watchdog+1;if(watchdog>20000)$fatal(1,"transaction stalled");end while(!ready);
            @(negedge clk);req=0;
        end
    endtask
    task reset_all;
        begin @(negedge clk);rst=0;req=0;consume=0;auto_consume=0;repeat(10)cycle();rst=1;repeat(5)cycle();end
    endtask
    initial begin
        reset_all();delay_cfg=1;
        for(integer k=0;k<4;k=k+1)transact(0,k);
        repeat(20)cycle();
        if(fifo_ready || credit || commits!=4 || consumed!=0)$fatal(1,"did not fill four-entry FIFO");
        @(negedge clk);req=1;wr=0;addr=32'h10100020;
        repeat(200)begin cycle();if(ready || dreq)$fatal(1,"read accepted into full return FIFO");end
        @(negedge clk);req=0;
        // Full return FIFO must still permit masked writes.
        for(integer k=0;k<16;k=k+1)transact(1,k);
        if(writes!=16)$fatal(1,"writes blocked by full response FIFO");
        consume=1;repeat(100)cycle();if(consumed!=4)$fatal(1,"full FIFO did not drain");
        auto_consume=1;
        for(integer k=0;k<4000;k=k+1)begin
            random_state=(random_state>>1)^({32{random_state[0]}}&32'h80200003);
            delay_cfg=1+(random_state[7:0]%47);
            transact(k%5==0,k*17);
        end
        auto_consume=0;consume=1;repeat(200)cycle();
        if(reads!=commits || reads!=consumed || reads!=3204 || writes!=816)$fatal(1,"final counts mismatch %0d %0d %0d %0d",reads,commits,consumed,writes);
        // Global reset while the return queue and native read are occupied.
        consume=0;transact(0,44);transact(0,45);delay_cfg=40;
        transact(0,46);repeat(3)cycle();reset_all();consume=1;
        for(integer k=0;k<100;k=k+1)transact(0,k+300);
        repeat(200)cycle();if(reads!=100 || commits!=100 || consumed!=100)$fatal(1,"reset recovery failed");
        $display("PASS DDR read credit seed=%0d 3204 reads+816 masked writes, FIFO-full read exclusion/write bypass,1..47-cycle native latency, asynchronous consumer, in-flight global reset",SEED);$finish;
    end
    // Independent native backpressure and downstream pauses.
    always @(negedge rclk)if(auto_consume)consume=(($time/14)%71)<43;
    always @(negedge clk)if(rst && reads>4)native_ready=(($time/10)%13)>3;else native_ready=1;
endmodule
