`timescale 1ns/1ps
// Ideal-wire throughput model. This cannot qualify a physical link budget.
module tb_task3_lcd_budget #(
    parameter integer PACKETS=1024,
    parameter bit BACKPRESSURE=0,
    parameter integer W_HALF_NS=11
);
    reg mc=0,wc=0,reset_n=0,enable=0,budget=0,run=0;
    always #10 mc=~mc; // M 50 MHz
    initial begin #3;forever #(W_HALF_NS) wc=~wc;end // separate clock/phase
    wire [1:0] clocks={wc,mc},live,business,fault,tx_ready,rx_valid,rx_ready;
    wire [1:0] req,ack,panic;
    wire [3:0] data[2],rx_channel[2],failure[2];
    wire [255:0] rx_payload[2];
    wire [5:0] rx_length[2];
    wire [31:0] tx_packets[2],rx_packets[2],crc_errors[2],sequence_errors[2];
    wire [31:0] congestion[2],max_rtt[2],probes[2],overflows[2];
    wire [31:0] sent[2],received[2];
    wire [63:0] finish_ns[2];
    time begin_ns;
    for(genvar i=0;i<2;i=i+1)begin:g_endpoint
        integer sent_count=0,received_count=0,cycles=0;
        time finish_time=0;
        assign sent[i]=32'(sent_count),received[i]=32'(received_count),finish_ns[i]=finish_time;
        wire [31:0] source_sequence=32'(sent_count);
        wire [255:0] payload={8{source_sequence}};
        assign rx_ready[i]=!BACKPRESSURE || cycles%7==0;
        workstation_task3_lcd_transport #(.EXPERIMENT_ENABLE(1),.ALLOW_BUSINESS(1)) link(
            .clk_i(clocks[i]),.reset_ni(reset_n),.enable_i(enable),.panic_i(1'b0),.budget_validated_i(budget),
            .local_boot_i(32'(i+1)),.peer_boot_i(32'(2-i)),.session_i(32'hc031),
            .tx_valid_i(run && sent[i]<PACKETS),.tx_ready_o(tx_ready[i]),
            .tx_channel_i(4'd1),.tx_payload_i(payload),.tx_length_i(6'd32),
            .rx_valid_o(rx_valid[i]),.rx_ready_i(rx_ready[i]),.rx_channel_o(rx_channel[i]),
            .rx_payload_o(rx_payload[i]),.rx_length_o(rx_length[i]),
            .link_ready_o(live[i]),.business_ready_o(business[i]),.pad_drive_o(),
            .fault_o(fault[i]),.failure_code_o(failure[i]),.peer_panic_o(),
            .phy_tx_data_o(data[i]),.phy_tx_req_o(req[i]),.phy_rx_ack_o(ack[i]),.phy_panic_o(panic[i]),
            .phy_rx_data_i(data[1-i]),.phy_rx_req_i(req[1-i]),.phy_tx_ack_i(ack[1-i]),.phy_peer_panic_i(panic[1-i]),
            .tx_packets_o(tx_packets[i]),.rx_packets_o(rx_packets[i]),.crc_errors_o(crc_errors[i]),
            .sequence_errors_o(sequence_errors[i]),.rejected_packets_o(),.overflow_count_o(overflows[i]),
            .congestion_cycles_o(congestion[i]),.last_rtt_cycles_o(),.max_rtt_cycles_o(max_rtt[i]),
            .probe_results_o(probes[i]),.link_timeouts_o());
        always @(posedge clocks[i])begin
            cycles<=cycles+1;
            if(run && sent_count<PACKETS && tx_ready[i])sent_count<=sent_count+1;
            if(rx_valid[i] && rx_ready[i])begin
                if(rx_channel[i]!=1 || rx_length[i]!=32 || rx_payload[i]!={8{32'(received[i])}})
                    $fatal(1,"duplex payload/order mismatch receiver=%0d sequence=%0d",i,received[i]);
                if(received[i]>=PACKETS)$fatal(1,"extra business packet receiver=%0d",i);
                received_count<=received_count+1;
                if(received_count==PACKETS-1)finish_time<=$time;
            end
            if(run && fault[i])$fatal(1,"model link fault endpoint=%0d code=%0d",i,failure[i]);
        end
    end
    initial begin
        repeat(5)@(negedge mc);reset_n=1;enable=1;
        wait(&live);@(negedge mc);budget=1;
        wait(&business);@(negedge mc);begin_ns=$time;run=1;
        wait(received[0]==PACKETS && received[1]==PACKETS);
        @(negedge mc);run=0;
        for(integer i=0;i<2;i=i+1)begin
            if(sent[i]!=PACKETS || crc_errors[i]!=0 || sequence_errors[i]!=0 || overflows[i]!=0)
                $fatal(1,"model counters not clean endpoint=%0d",i);
            $display("BUDGET_MODEL receiver=%0d packets=%0d payload_bytes=%0d elapsed_ns=%0t tx_packets=%0d rx_packets=%0d max_rtt_cycles=%0d probes=%0d congestion_cycles=%0d",
                i,received[i],received[i]*32,finish_ns[i]-begin_ns,tx_packets[i],rx_packets[i],max_rtt[i],probes[i],congestion[i]);
        end
        $display("PASS task3_lcd_budget backpressure=%0d physical_acceptance=0",BACKPRESSURE);
        $finish;
    end
    initial begin #100000000;$fatal(1,"budget model timeout");end
endmodule
