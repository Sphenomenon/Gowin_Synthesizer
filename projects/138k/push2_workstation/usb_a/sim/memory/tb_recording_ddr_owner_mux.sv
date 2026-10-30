`timescale 1ns/1ps
module tb_recording_ddr_owner_mux;
    reg clk=0;always #5 clk=~clk;
    reg reset_n=0;
    reg [1:0] published=0,write_kind=0;
    reg [28:0] address0=1024,address1=2048;
    reg [255:0] data0=0,data1=0;
    reg [31:0] mask0=0,mask1=0;
    wire [1:0] slots,ready,native,response;
    wire [1:0] bridge_fault;
    wire valid,write_kind_o,busy,fault,transport_fault;
    wire [28:0] address;
    wire [255:0] data;
    wire [31:0] mask;
    reg slot_ready=0,native_commit=0,read_return=0,upstream_fault=0,channel_ready=0;
    wire [1:0] producer_commit;
    for(genvar i=0;i<2;i=i+1)begin:b
        workstation_recording_ddr_native_bridge bridge(
            .clk_i(clk),.rst_ni(reset_n),.published_valid_i(published[i]),
            .slot_ready_i(ready[i]),.native_accept_i(native[i]),.transport_fault_i(transport_fault),
            .slot_valid_o(slots[i]),.native_ready_o(producer_commit[i]),
            .transport_fault_o(bridge_fault[i]),.submitted_o(),.protocol_fault_o());
    end
    workstation_recording_ddr_owner_mux #(.FIRST0(1024),.LAST0(1087),.FIRST1(2048),.LAST1(2111),.BUDGET_CYCLES(12)) dut(
        .clk_i(clk),.rst_ni(reset_n),.channel_ready_i(channel_ready),.valid_i(slots),.write_i(write_kind),
        .address0_i(address0),.address1_i(address1),.data0_i(data0),.data1_i(data1),.mask0_i(mask0),.mask1_i(mask1),
        .ready_o(ready),.native_accept_o(native),.response_o(response),
        .valid_o(valid),.write_o(write_kind_o),.address_o(address),.data_o(data),.mask_o(mask),
        .ready_i(slot_ready),.native_accept_i(native_commit),.response_i(read_return),.transport_fault_i(upstream_fault),
        .transport_fault_o(transport_fault),.fault_o(fault),.busy_o(busy));
    integer checks=0,writes=0,reads=0,seed=32'h590ad8;
    task check(input bit condition,input [255:0] text);
        begin checks=checks+1;if(!condition)$fatal(1,"%s at %t",text,$time);end
    endtask
    task tick;begin @(posedge clk);#1;end endtask
    task edge_low;begin @(negedge clk);#1;end endtask
    task reset;
        begin
            edge_low();reset_n=0;published=0;native_commit=0;read_return=0;slot_ready=0;upstream_fault=0;channel_ready=0;
            address0=1024;address1=2048;repeat(2)tick();edge_low();reset_n=1;tick();
            edge_low();published=3;#1;check(!valid && ready==0,"external rearm required after reset");
            published=0;channel_ready=1;#1;
            check(!fault && !busy,"reset clears channel");
        end
    endtask
    task retire(input integer owner,input integer delay_cycles,input bit simultaneous);
        reg [1:0] target;
        begin
            target=2'b01<<owner;
            repeat(delay_cycles)begin tick();check(busy && !valid && producer_commit==0 && response==0,"slot is not native commit");end
            edge_low();native_commit=1;read_return=simultaneous && !write_kind[owner];#1;
            check(native==target && producer_commit==target,"native commit returns only to owner");
            check(response==(read_return ? target:2'b00),"same-cycle read response ownership");
            tick();edge_low();published[owner]=0;native_commit=0;read_return=0;
            if(!write_kind[owner] && !simultaneous)begin
                repeat(3)begin tick();check(busy && !valid && response==0,"read keeps ownership until response");end
                edge_low();read_return=1;#1;check(response==target && native==0,"delayed read response ownership");
                tick();edge_low();read_return=0;
            end
            if(write_kind[owner])writes=writes+1;else reads=reads+1;
            #1;check(!busy && !transport_fault && bridge_fault==0,"completed request is healthy");
        end
    endtask
    task enqueue(input integer owner);
        begin
            #1;check(valid && address==(owner ? address1:address0),"round-robin selects expected region");
            check(data==(owner ? data1:data0) && mask==(owner ? mask1:mask0),"data and mask belong to same owner");
            slot_ready=1;#1;check(ready==(2'b01<<owner),"only selected client accepts local slot");
            tick();edge_low();slot_ready=0;check(busy && !valid,"one slot outstanding");
        end
    endtask
    integer iteration;
    initial begin
        reset();
        for(iteration=0;iteration<80;iteration=iteration+1)begin
            edge_low();published=3;write_kind=$random(seed);
            address0=1024+8*(iteration%8);address1=2048+8*((iteration+3)%8);
            data0={8{32'h01234567^iteration}};data1={8{32'hf0e1d2c3^iteration}};
            mask0=32'hffff0000^iteration;mask1=32'h0000ffff^iteration;
            repeat(3)begin tick();check(valid && address==address0 && producer_commit==0,"backpressure preserves first offer");end
            edge_low();enqueue(0);retire(0,iteration%5,iteration%2);
            enqueue(1);retire(1,(iteration+1)%5,iteration%3==0);
        end
        // The just-served writer offers again while its peer is still queued.
        // Choosing the new request again would starve the other recording.
        edge_low();published=3;write_kind=3;
        enqueue(0);retire(0,1,0);edge_low();published[0]=1;
        enqueue(1);retire(1,1,0);enqueue(0);retire(0,1,0);
        // Accepted commands and read returns cannot be silently abandoned.
        reset();edge_low();published=1;write_kind=1;enqueue(0);
        repeat(13)tick();check(fault && transport_fault && !valid && native==0,"native timeout isolates");
        edge_low();native_commit=1;#1;check(native==0,"late commit after timeout is not delivered");tick();
        reset();edge_low();published=1;write_kind=0;enqueue(0);
        edge_low();native_commit=1;tick();edge_low();native_commit=0;published=0;
        repeat(13)tick();check(fault && response==0,"read timeout isolates");
        edge_low();read_return=1;#1;check(response==0,"late read after timeout cannot reach new client");
        reset();edge_low();read_return=1;tick();check(fault,"unowned response rejected");
        reset();edge_low();native_commit=1;tick();check(fault,"unowned native commit rejected");
        reset();edge_low();published=1;address0=2048;tick();check(fault && !valid,"cross-region command rejected");
        reset();edge_low();published=2;address1=2112;tick();check(fault,"end overrun rejected");
        reset();edge_low();published=1;address0=1025;tick();check(fault,"unaligned command rejected");
        reset();edge_low();published=1;write_kind=1;enqueue(0);channel_ready=0;#1;
        check(transport_fault && native==0 && response==0,"ready withdrawal isolates in-flight request");
        tick();check(fault,"ready withdrawal is sticky");
        reset();edge_low();channel_ready=0;read_return=1;tick();check(fault,"old return before rearm quarantines channel");
        reset();edge_low();published=3;upstream_fault=1;#1;check(!valid && ready==0,"transport fault blocks admission immediately");tick();
        check(fault,"transport fault remains sticky");edge_low();upstream_fault=0;tick();check(!valid,"fault requires common reset");
        $display("PASS recording owner mux: %0d checks, %0d writes, %0d reads",checks,writes,reads);$finish;
    end
    initial begin #1000000;$fatal(1,"test deadline");end
endmodule
