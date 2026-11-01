`timescale 1ns/1ps
module tb_workstation_cnn_broker;
    reg clk=0,reset_n=0,backend=0,transport_fault=0;
    always #5 clk=~clk;
    reg cnn_valid=0,cnn_write=0,stage_valid=0,stage_write=0;
    reg [28:0] cnn_address=29'h0123450,stage_address=29'hc440000;
    reg [255:0] cnn_data=256'h11223344,stage_data=256'haabbccdd;
    reg [31:0] cnn_mask=32'hffff0000,stage_mask=32'h0000ffff;
    reg slot_ready=0,native_accept=0,response=0;
    wire cnn_ready,cnn_response,stage_ready,stage_response,slot_valid,write,clear,fault;
    wire [28:0] address;
    wire [255:0] data;
    wire [31:0] mask;
    integer checks=0;
    workstation_cnn_ddr_broker #(.TIMEOUT_CYCLES(32)) dut(
        .clk_i(clk),.reset_ni(reset_n),.backend_ready_i(backend),.transport_fault_i(transport_fault),
        .cnn_valid_i(cnn_valid),.cnn_write_i(cnn_write),.cnn_address_i(cnn_address),
        .cnn_data_i(cnn_data),.cnn_mask_i(cnn_mask),.cnn_ready_o(cnn_ready),.cnn_response_o(cnn_response),
        .stage_valid_i(stage_valid),.stage_write_i(stage_write),.stage_address_i(stage_address),
        .stage_data_i(stage_data),.stage_mask_i(stage_mask),.stage_ready_o(stage_ready),.stage_response_o(stage_response),
        .slot_valid_o(slot_valid),.write_o(write),.address_o(address),.data_o(data),.mask_o(mask),
        .slot_ready_i(slot_ready),.native_accept_i(native_accept),.response_i(response),.idle_o(clear),.fault_o(fault));
    task automatic check(input bit ok,input [767:0] message);
        begin checks=checks+1;if(!ok)$fatal(1,"%0s",message);end
    endtask
    task automatic ticks(input integer count);begin repeat(count)@(negedge clk);end endtask
    task automatic reset;
        begin reset_n=0;backend=0;transport_fault=0;cnn_valid=0;stage_valid=0;
            native_accept=0;response=0;slot_ready=0;ticks(3);reset_n=1;backend=1;ticks(2);
            check(clear && !fault,"common reset clears quarantine");
        end
    endtask
    task automatic submit(input bit stage,input bit wr);
        begin
            if(stage)begin stage_write=wr;stage_valid=1;end
            else begin cnn_write=wr;cnn_valid=1;end
            wait(slot_valid);@(negedge clk);
            check(address==(stage?stage_address:cnn_address) && write==wr &&
                  data==(stage?stage_data:cnn_data) && mask==(stage?stage_mask:cnn_mask),"captured native command retains selected owner payload");
            ticks(4);check(slot_valid && !cnn_ready && !stage_ready,"local slot stall never acknowledges producer");
            slot_ready=1;ticks(1);slot_ready=0;
            check(!cnn_ready && !stage_ready,"local slot admission is not native commitment");
            ticks(4);native_accept=1;#1;
            check(stage?(stage_ready && !cnn_ready):(cnn_ready && !stage_ready),"native acceptance acknowledges only selected owner");
            ticks(1);native_accept=0;
            if(stage)stage_valid=0;else cnn_valid=0;
            if(!wr)begin
                ticks(3);check(!clear && !cnn_response && !stage_response,"read remains owned until actual return");
                response=1;#1;
                check(stage?(stage_response && !cnn_response):(cnn_response && !stage_response),"read return routes exactly to accepted owner");
                ticks(1);response=0;
            end
            ticks(1);check(clear && !fault,"completed transaction releases one native slot");
        end
    endtask
    initial begin
        reset();backend=0;cnn_valid=1;ticks(5);check(!slot_valid && !cnn_ready,"backend gate suppresses dispatch");
        cnn_valid=0;backend=1;
        submit(0,0);submit(1,0);submit(0,1);submit(1,1);
        // Both producers hold stable valid until their own native acknowledgement.
        // The prior stage completion gives CNN first, then the priority rotates.
        cnn_valid=1;stage_valid=1;cnn_write=1;stage_write=1;
        for(integer k=0;k<8;k=k+1)begin
            wait(slot_valid);@(negedge clk);
            check(address==(k%2==0?cnn_address:stage_address),"bounded simultaneous sources alternate service");
            slot_ready=1;ticks(1);slot_ready=0;native_accept=1;#1;
            check(k%2==0?(cnn_ready&&!stage_ready):(stage_ready&&!cnn_ready),"simultaneous service ack preserves owner");
            ticks(1);native_accept=0;
        end
        cnn_valid=0;stage_valid=0;ticks(2);check(clear && !fault,"parallel stress drains cleanly");
        reset();stage_valid=1;wait(slot_valid);@(negedge clk);slot_ready=1;ticks(1);slot_ready=0;
        ticks(40);check(fault && !slot_valid && !stage_ready,"lost native commitment times out into sticky quarantine");
        native_accept=1;ticks(1);native_accept=0;ticks(2);check(fault && !stage_ready,"late native acceptance cannot reopen timed-out owner");
        reset();response=1;ticks(1);response=0;ticks(1);check(fault && !cnn_response && !stage_response,"unowned read return quarantines owner");
        reset();cnn_valid=1;cnn_write=0;wait(slot_valid);@(negedge clk);slot_ready=1;ticks(1);slot_ready=0;
        native_accept=1;ticks(1);native_accept=0;cnn_valid=0;
        transport_fault=1;response=1;#1;check(!cnn_response && !stage_response,"same-cycle transport fault suppresses old result");
        ticks(1);transport_fault=0;response=0;ticks(2);check(fault && !slot_valid,"transport quarantine requires coherent reset");
        $display("PASS CNN_native_broker checks=%0d",checks);$finish;
    end
    initial begin #100000;$fatal(1,"broker fixture deadline");end
endmodule
