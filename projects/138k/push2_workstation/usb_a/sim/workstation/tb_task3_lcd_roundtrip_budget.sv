`timescale 1ns/1ps
// Existing channel-0 diagnostic frames only. This is not a reverb wire format.
// Zero wire delay and immediate echo exclude effect compute and owner queues.
module tb_task3_lcd_roundtrip_budget #(
    parameter integer W_HALF_NS=10,
    parameter integer W_PHASE_NS=3,
    parameter integer REQUESTS=4
);
    reg mc=0,wc=0,reset_n=0,enable=0,run=0;
    always #10 mc=~mc;
    initial begin #(W_PHASE_NS);forever #(W_HALF_NS)wc=~wc;end
    wire [1:0] clocks;
    assign clocks={wc,mc};
    wire [1:0] live,business,fault,tx_ready,rx_valid,rx_ready;
    wire [1:0] req,ack,panic;
    wire [3:0] data[0:1],rx_channel[0:1],failure[0:1];
    wire [255:0] rx_payload[0:1],payload[0:1];
    wire [5:0] rx_length[0:1];
    wire [31:0] crc_errors[0:1],sequence_errors[0:1],overflows[0:1];
    reg outstanding=0,echo_pending=0;
    reg [255:0] echo_payload=0;
    integer sent=0,received=0;
    time offered_time;
    assign payload[0]={8{32'hb1370000 | 32'(sent)}};
    assign payload[1]=echo_payload;
    assign rx_ready[0]=1'b1,rx_ready[1]=!echo_pending;
    for(genvar endpoint=0;endpoint<2;endpoint=endpoint+1)begin:g_endpoint
        workstation_task3_lcd_transport #(.EXPERIMENT_ENABLE(1),.ALLOW_BUSINESS(0)) link(
            .clk_i(clocks[endpoint]),.reset_ni(reset_n),.enable_i(enable),.panic_i(1'b0),.budget_validated_i(1'b0),
            .local_boot_i(32'(endpoint+1)),.peer_boot_i(32'(2-endpoint)),.session_i(32'hf406),
            .tx_valid_i(endpoint==0 ? run && !outstanding && sent<REQUESTS : echo_pending),
            .tx_ready_o(tx_ready[endpoint]),.tx_channel_i(4'd0),.tx_payload_i(payload[endpoint]),.tx_length_i(6'd32),
            .rx_valid_o(rx_valid[endpoint]),.rx_ready_i(rx_ready[endpoint]),.rx_channel_o(rx_channel[endpoint]),
            .rx_payload_o(rx_payload[endpoint]),.rx_length_o(rx_length[endpoint]),
            .link_ready_o(live[endpoint]),.business_ready_o(business[endpoint]),.pad_drive_o(),
            .fault_o(fault[endpoint]),.failure_code_o(failure[endpoint]),.peer_panic_o(),
            .phy_tx_data_o(data[endpoint]),.phy_tx_req_o(req[endpoint]),.phy_rx_ack_o(ack[endpoint]),.phy_panic_o(panic[endpoint]),
            .phy_rx_data_i(data[1-endpoint]),.phy_rx_req_i(req[1-endpoint]),.phy_tx_ack_i(ack[1-endpoint]),.phy_peer_panic_i(panic[1-endpoint]),
            .tx_packets_o(),.rx_packets_o(),.crc_errors_o(crc_errors[endpoint]),
            .sequence_errors_o(sequence_errors[endpoint]),.rejected_packets_o(),.overflow_count_o(overflows[endpoint]),
            .congestion_cycles_o(),.last_rtt_cycles_o(),.max_rtt_cycles_o(),
            .probe_results_o(),.link_timeouts_o());
        always @(posedge clocks[endpoint])if(run)begin
            if(fault[endpoint])$fatal(1,"diagnostic link fault endpoint=%0d code=%0d",endpoint,failure[endpoint]);
            if(business[endpoint])$fatal(1,"diagnostic granted business permission");
        end
    end
    always @(posedge mc)if(reset_n && run)begin
        if(!outstanding && sent<REQUESTS && tx_ready[0])begin
            offered_time<=$time;outstanding<=1;sent<=sent+1;
        end
        if(rx_valid[0])begin
            if(!outstanding || rx_channel[0]!=0 || rx_length[0]!=32 ||
                rx_payload[0]!={8{32'hb1370000 | 32'(received)}})
                $fatal(1,"diagnostic response identity/order mismatch");
            $display("LCD_ECHO request=%0d elapsed_ns=%0d",received,$time-offered_time);
            received<=received+1;outstanding<=0;
        end
    end
    always @(posedge wc)if(reset_n)begin
        if(echo_pending && tx_ready[1])echo_pending<=0;
        if(rx_valid[1] && rx_ready[1])begin
            if(rx_channel[1]!=0 || rx_length[1]!=32)$fatal(1,"diagnostic request malformed");
            echo_payload<=rx_payload[1];echo_pending<=1;
        end
    end
    initial begin
        repeat(5)@(negedge mc);reset_n=1;enable=1;
        wait(&live);repeat(4)@(negedge mc);run=1;
        wait(received==REQUESTS);@(negedge mc);run=0;
        for(integer i=0;i<2;i=i+1)
            if(crc_errors[i]!=0 || sequence_errors[i]!=0 || overflows[i]!=0)
                $fatal(1,"diagnostic counters not clean");
        $display("PASS task3_lcd_roundtrip_budget requests=%0d physical_acceptance=0",received);
        $finish;
    end
    initial begin #2000000;$fatal(1,"diagnostic roundtrip timeout");end
endmodule
