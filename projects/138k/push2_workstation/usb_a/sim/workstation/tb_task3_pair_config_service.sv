`timescale 1ns/1ps
module tb_task3_pair_config_service #(
    parameter bit TEST_ALLOW_BUSINESS=1'b1
);
    reg clk=0;always #10 clk=~clk;
    reg reset_n=0,owner_n=0,valid=0,write=0,link=0,fault=0,peer_panic=0;
    reg [11:0] address=0;reg [31:0] data=0;reg [3:0] strobes=15;
    wire ready,error,probe,budget,business,arm,cancel,panic;
    wire [31:0] response,local_boot,peer_boot,session,generation;
    integer checks=0,arms=0,cancels=0,panics=0,before_count;
    workstation_task3_pair_config_service #(.ALLOW_BUSINESS(TEST_ALLOW_BUSINESS)) dut(
        .clk_i(clk),.reset_ni(reset_n),.owner_reset_ni(owner_n),
        .command_valid_i(valid),.command_write_i(write),.command_address_i(address),.command_data_i(data),.command_strobes_i(strobes),
        .command_ready_o(ready),.response_error_o(error),.response_data_o(response),
        .link_ready_i(link),.link_fault_i(fault),.peer_panic_i(peer_panic),.link_failure_code_i(4'd6),
        .tx_packets_i(32'd11),.rx_packets_i(32'd12),.crc_errors_i(32'd13),.sequence_errors_i(32'd14),
        .rejected_packets_i(32'd15),.overflow_count_i(32'd16),.congestion_cycles_i(32'd17),
        .last_rtt_cycles_i(32'd18),.max_rtt_cycles_i(32'd19),.probe_results_i(32'd20),.link_timeouts_i(32'd21),
        .local_boot_o(local_boot),.peer_boot_o(peer_boot),.session_o(session),.generation_o(generation),
        .probe_enable_o(probe),.budget_validated_o(budget),.business_enable_o(business),
        .record_arm_o(arm),.record_cancel_o(cancel),.panic_o(panic));
    always @(posedge clk)if(reset_n)begin
        if(arm)arms=arms+1;if(cancel)cancels=cancels+1;if(panic)panics=panics+1;
    end
    task automatic require(input reg condition,input string message);
        begin checks=checks+1;if(!condition)$fatal(1,"config check%0d %s at%03x error%0d response%08x",checks,message,address,error,response);end
    endtask
    task automatic access(input reg wr,input [11:0] at,input [31:0] value,input [3:0] mask,input reg expected_error);
        begin
            @(negedge clk);valid=1;write=wr;address=at;data=value;strobes=mask;#1;
            require(ready && error==expected_error,"bounded immediate command response");
            @(posedge clk);@(negedge clk);valid=0;#1;
        end
    endtask
    task automatic put(input [11:0] at,input [31:0] value,input reg expected_error);
        begin access(1,at,value,15,expected_error);end
    endtask
    task automatic get(input [11:0] at,input [31:0] expected);
        begin access(0,at,0,0,0);require(response==expected,"readback matches actual state/diagnostic");end
    endtask
    task automatic setup(input [31:0] gen);
        begin
            fault=0;peer_panic=0;link=0;
            put('h010,32'h8badf001,0);put('h014,32'h5eedf002,0);
            put('h018,32'h73a90000+gen,0);put('h01c,gen,0);
            require(!probe&&!budget&&!business,"writing identities never grants outputs");
            put('h020,1,0);require(probe&&!budget&&!business,"probe independent of business and measurement budget");
        end
    endtask
    integer k;
    initial begin
        repeat(3)@(negedge clk);reset_n=1;owner_n=1;#1;
        require({local_boot,peer_boot,session,generation}==0 && !probe&&!budget&&!business&&!arm&&!cancel&&!panic,"all config and actions default zero");
        get('h000,32'h54335001);get('h008,{31'd0,TEST_ALLOW_BUSINESS});get('h038,0);
        access(1,'h011,32'hf,15,1);access(1,'h010,32'hf,7,1);access(0,'hffc,0,0,1);put('h000,1,1);
        put('h010,0,1);put('h020,1,1);put('h01c,0,1);
        put('h010,32'h8badf001,0);put('h014,32'h8badf001,0);put('h018,32'h73a90001,0);put('h01c,1,0);
        put('h020,1,1);require(!probe,"equal peer/local identities cannot activate");
        put('h014,32'h5eedf002,0);put('h020,1,0);
        repeat(4)@(negedge clk);require(probe&&!business,"startup without a previously live peer permits probe");
        put('h010,32'hbadd00d,1);put('h01c,2,1);put('h020,1,1);
        require(local_boot==32'h8badf001&&generation==1,"active identities are frozen");
        put('h024,1,1);put('h028,1,1);put('h02c,1,1);
        link=1;repeat(2)@(negedge clk);
        if(TEST_ALLOW_BUSINESS)begin
            put('h028,1,1);put('h024,1,0);require(budget&&!business,"measurement assertion does not itself enable business");
            put('h028,1,0);require(business,"both explicit grants required");
            before_count=arms;put('h02c,1,0);repeat(2)@(negedge clk);require(arms==before_count+1,"record arm is one request pulse");
            put('h024,0,0);require(!probe&&!budget&&!business&&local_boot==0,"budget withdrawal clears identity and all grants");
            get('h048,7);
        end else begin
            put('h024,1,1);put('h028,1,1);put('h02c,1,1);
            require(probe&&!budget&&!business,"compile deny cannot be bypassed with live peer");put('h020,0,0);
        end
        get('h038,1);put('h01c,1,1);put('h018,32'h73a90001,1);put('h020,1,1);
        setup(2);link=1;repeat(2)@(negedge clk);link=0;#1;require(!business,"link loss immediately closes business grant");
        repeat(2)@(negedge clk);require(!probe&&local_boot==0,"previously live link loss revokes probe and identities");get('h048,3);
        setup(3);fault=1;repeat(2)@(negedge clk);require(!probe,"transport fault revokes even before peer became live");fault=0;get('h048,4);
        setup(4);link=1;repeat(2)@(negedge clk);owner_n=0;#1;
        require(!probe&&!budget&&!business&&!arm,"CPU reset immediately closes grants");
        repeat(2)@(negedge clk);require(local_boot==0&&session==0&&generation==0,"CPU reset clears all staged identity");
        access(1,'h010,1,15,1);owner_n=1;get('h038,4);get('h048,1);put('h01c,4,1);put('h020,1,1);
        setup(5);peer_panic=1;repeat(2)@(negedge clk);require(!probe,"peer PANIC revokes");peer_panic=0;get('h048,5);
        setup(6);before_count=panics;put('h034,1,0);
        require(!probe&&!business&&panic,"PANIC action revokes locally and emits request");
        repeat(2)@(negedge clk);require(panics==before_count+1&&!panic,"PANIC request is one cycle");get('h048,6);
        setup(7);before_count=cancels;put('h030,1,0);repeat(2)@(negedge clk);
        require(probe&&cancels==before_count+1,"record cancel is one pulse and does not grant or rearm link");
        put('h020,0,0);require(!probe,"explicit disable revokes");get('h048,2);
        if(TEST_ALLOW_BUSINESS)begin
            setup(8);link=1;repeat(2)@(negedge clk);put('h024,1,0);put('h028,1,0);put('h028,0,0);
            require(!probe&&!budget&&!business,"business disable needs a new generation before rearm");get('h048,8);
        end
        for(k=0;k<11;k=k+1)get(12'('h050+k*4),32'(11+k));get('h07c,6);
        setup(32'hffffffff);put('h020,0,0);get('h038,32'hffffffff);put('h01c,0,1);put('h01c,32'hffffffff,1);
        put('h020,1,1);require(!probe&&!business,"generation cannot wrap or replay");
        require(ready,"no link state stalls command scheduling");
        $display("PASS task3_pair_config_service ALLOW=%0d checks=%0d",TEST_ALLOW_BUSINESS,checks);$finish;
    end
    initial begin #1000000;$fatal(1,"config test timeout");end
endmodule
