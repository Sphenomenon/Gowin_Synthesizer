`timescale 1ns/1ps
module tb_cnn_staging_retirement #(parameter RESET_MIDFLIGHT=0);
    reg control_clk=0,memory_clk=0,reset_n=0;
    always #10 control_clk=~control_clk;
    always #7 memory_clk=~memory_clk;
    integer sent=0,received=0,native_count=0,cycles=0,control_cycles=0;
    wire request_write_ready,request_valid,request_retire;
    wire [317:0] request_data;
    wire [317:0] input_data={sent[0],29'(sent*8),{8{32'(sent+32'h1234)}},32'h0};
    music_async_fifo #(.WIDTH(318),.ADDRESS_BITS(2)) requests(
        .write_clk_i(control_clk),.write_rst_ni(reset_n),.write_valid_i(sent<64),
        .write_ready_o(request_write_ready),.write_data_i(input_data),
        .read_clk_i(memory_clk),.read_rst_ni(reset_n),.read_valid_o(request_valid),
        .read_ready_i(request_retire),.read_data_o(request_data));
    wire completion_valid,completion_ready,retire_busy,retire_fault,completion_read_valid;
    wire [256:0] completion_data,completed_data;
    wire completion_read_ready=(control_cycles%17>=12);
    music_async_fifo #(.WIDTH(257),.ADDRESS_BITS(2)) completions(
        .write_clk_i(memory_clk),.write_rst_ni(reset_n),.write_valid_i(completion_valid),
        .write_ready_o(completion_ready),.write_data_i(completion_data),
        .read_clk_i(control_clk),.read_rst_ni(reset_n),.read_valid_o(completion_read_valid),
        .read_ready_i(completion_read_ready),.read_data_o(completed_data));
    wire commit,response,stage_response,slot_valid,write_cmd,broker_fault;
    wire [28:0] address;
    wire [255:0] data;
    wire [31:0] mask;
    reg submitted=0,read_pending=0;
    reg held_write=0;
    reg [28:0] held_address=0;
    reg [255:0] held_data=0,response_data=0;
    integer read_timer=0;
    reg response_pulse=0;
    wire slot_ready=!submitted && !read_pending && cycles%5!=0;
    wire native_accept=submitted && cycles%7<3;
    assign response=response_pulse;
    workstation_cnn_ddr_broker #(.TIMEOUT_CYCLES(1000)) broker(
        .clk_i(memory_clk),.reset_ni(reset_n),.backend_ready_i(1'b1),.transport_fault_i(1'b0),
        .cnn_valid_i(1'b0),.cnn_write_i(1'b0),.cnn_address_i(29'd0),
        .cnn_data_i(256'd0),.cnn_mask_i(32'd0),.cnn_ready_o(),.cnn_response_o(),
        .stage_valid_i(request_valid && completion_ready && !retire_busy),
        .stage_write_i(request_data[317]),.stage_address_i(request_data[316:288]),
        .stage_data_i(request_data[287:32]),.stage_mask_i(request_data[31:0]),
        .stage_ready_o(commit),.stage_response_o(stage_response),
        .slot_valid_o(slot_valid),.write_o(write_cmd),.address_o(address),.data_o(data),.mask_o(mask),
        .slot_ready_i(slot_ready),.native_accept_i(native_accept),.response_i(response),
        .idle_o(),.fault_o(broker_fault));
    workstation_cnn_staging_retirement dut(
        .clk_i(memory_clk),.reset_ni(reset_n),.commit_i(commit),.write_i(request_data[317]),
        .response_i(stage_response),.response_data_i(response_data),.completion_ready_i(completion_ready),
        .request_retire_o(request_retire),.completion_valid_o(completion_valid),
        .completion_data_o(completion_data),.busy_o(retire_busy),.fault_o(retire_fault));
    always @(posedge memory_clk)begin
        if(!reset_n)begin cycles<=0;native_count<=0;submitted<=0;read_pending<=0;response_pulse<=0;end
        else begin
            cycles<=cycles+1;response_pulse<=0;
            if(broker_fault || retire_fault)$fatal(1,"healthy native flow faulted");
            if(slot_valid && slot_ready)begin
                submitted<=1;held_write<=write_cmd;held_address<=address;held_data<=data;
                if(mask!==0)$fatal(1,"command mask changed");
            end
            if(native_accept)begin
                if(!commit || held_address!==29'(native_count*8) || held_write!==native_count[0] ||
                   held_data!=={8{32'(native_count+32'h1234)}})
                    $fatal(1,"native command duplicate/lost/corrupt index=%0d address=%h",native_count,held_address);
                submitted<=0;native_count<=native_count+1;
                if(!held_write)begin read_pending<=1;read_timer<=3+(native_count%4);end
            end
            if(read_pending)begin
                if(read_timer!=0)read_timer<=read_timer-1;
                else begin
                    response_data<={8{32'(held_address)^32'hcafebabe}};
                    response_pulse<=1;read_pending<=0;
                end
            end
            if(cycles>10000)$fatal(1,"native flow stalled");
        end
    end
    always @(posedge control_clk)begin
        if(!reset_n)begin sent<=0;received<=0;control_cycles<=0;end
        else begin
            control_cycles<=control_cycles+1;
            if(sent<64 && request_write_ready)sent<=sent+1;
            if(completion_read_valid && completion_read_ready)begin
                if(completed_data[256]!==received[0] ||
                   (!received[0] && completed_data[255:0]!=={8{32'(received*8)^32'hcafebabe}}))
                    $fatal(1,"completion duplicate/lost/corrupt index=%0d",received);
                received<=received+1;
                if(received==63)begin
                    if(native_count!=64)$fatal(1,"completion preceded native commit");
                    $display("PASS registered CNN retirement native=64 completion=64 reads=32 writes=32 asynchronous_stalls=1");
                    $finish;
                end
            end
        end
    end
    initial begin
        #31;reset_n=1;
        if(RESET_MIDFLIGHT)begin
            wait(native_count==15);@(negedge memory_clk);reset_n=0;
            #43;reset_n=1;
        end
    end
endmodule
