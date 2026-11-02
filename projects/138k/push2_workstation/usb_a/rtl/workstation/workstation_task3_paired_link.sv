`timescale 1ns/1ps
// Paired-only board composition. Probe eligibility and business authority are
// separate; no reset value drives the cable or grants a measured budget.
module workstation_task3_paired_link #(
    parameter bit ROLE_M=1'b1,
    parameter bit EXPERIMENT_ENABLE=1'b0,
    parameter bit ALLOW_BUSINESS=1'b0,
    parameter integer PANIC_HOLD_CYCLES=50000
)(
    input wire clk_i,reset_ni,pclk,preset_n,psel,penable,pwrite,external_panic_i,
    input wire [11:0] paddr,
    input wire [31:0] pwdata,
    input wire [3:0] pstrb,
    output wire pready,pslverr,
    output wire [31:0] prdata,
    output wire [31:0] local_boot_o,peer_boot_o,session_o,generation_o,
    output wire probe_enable_o,budget_validated_o,business_enable_o,
    output wire link_ready_o,panic_o,record_arm_o,record_cancel_o,
    input wire tx_valid_i,
    output wire tx_ready_o,
    input wire [3:0] tx_channel_i,
    input wire [255:0] tx_payload_i,
    input wire [5:0] tx_length_i,
    output wire rx_valid_o,
    input wire rx_ready_i,
    output wire [3:0] rx_channel_o,
    output wire [255:0] rx_payload_o,
    output wire [5:0] rx_length_o,
    inout wire [4:0] lcd_r,lcd_b,
    inout wire [5:0] lcd_g,
    inout wire lcd_pclk,lcd_hsync,lcd_vsync,lcd_de,lcd_bl,
    inout wire lcd_ctp_rst,lcd_ctp_sda,lcd_ctp_scl,lcd_ctp_int
);
    wire command_reset_n,command_valid,command_ready,command_write,response_error;
    wire [11:0] command_address;
    wire [31:0] command_data,response_data;
    wire [3:0] command_strobes;
    gw138k_apb_cdc config_cdc(
        .reset_n(reset_ni && preset_n),.pclk(pclk),.audio_clk(clk_i),
        .psel(psel),.penable(penable),.pwrite(pwrite),.paddr(paddr),.pwdata(pwdata),.pstrb(pstrb),
        .pready(pready),.pslverr(pslverr),.prdata(prdata),
        .command_reset_n(command_reset_n),.command_valid(command_valid),.command_ready(command_ready),
        .command_write(command_write),.command_address(command_address),.command_data(command_data),.command_strobes(command_strobes),
        .response_data(response_data),.response_error(response_error));
    wire probe_ready,transport_business_ready,transport_fault,pad_drive,transport_peer_panic,local_panic;
    wire [3:0] failure_code,tx_data,rx_data;
    wire tx_req,rx_req,rx_ack,tx_ack,peer_panic_pad;
    wire [31:0] tx_packets,rx_packets,crc_errors,sequence_errors,rejected_packets;
    wire [31:0] overflow_count,congestion_cycles,last_rtt,max_rtt,probe_results,link_timeouts;
    wire transport_tx_ready,transport_rx_valid;
    wire [3:0] transport_rx_channel;
    wire [255:0] transport_rx_payload;
    wire [5:0] transport_rx_length;
    // Independent synchronizer remains active while the transport is fenced.
    // The dedicated peer emergency signal never needs queue admission.
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] peer_panic_sync;
    reg [$clog2(PANIC_HOLD_CYCLES+1)-1:0] panic_hold;
    wire held_panic=panic_hold!=0;
    wire peer_panic=EXPERIMENT_ENABLE && probe_enable_o && peer_panic_sync[1];
    // Local performance PANIC always revokes endpoints. It may energize the
    // cable only after explicit probe authorization; standalone performance
    // PANIC must not turn a disabled LCD connector into an output.
    wire external_wire_panic=external_panic_i && probe_enable_o;
    initial if(PANIC_HOLD_CYCLES<16)$fatal(1,"PANIC hold must cross an asynchronous receiver");
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin peer_panic_sync<=0;panic_hold<=0;end
        else begin
            peer_panic_sync<={peer_panic_sync[0],peer_panic_pad};
            if(local_panic || external_wire_panic)panic_hold<=$clog2(PANIC_HOLD_CYCLES+1)'(PANIC_HOLD_CYCLES);
            else if(held_panic)panic_hold<=panic_hold-1'b1;
        end
    end
    assign panic_o=reset_ni && (local_panic || external_panic_i || held_panic || peer_panic);
    assign link_ready_o=business_enable_o && transport_business_ready && !panic_o;
    // Channel zero remains the probe-qualified generic control contract.
    // Apply the same admission predicate to BOTH sides of each handshake;
    // otherwise a masked valid with a visible ready silently consumes data.
    wire tx_open=!panic_o && (tx_channel_i==0 ? probe_ready : link_ready_o);
    wire rx_open=!panic_o && (transport_rx_channel==0 ? probe_ready : link_ready_o);
    assign tx_ready_o=transport_tx_ready && tx_open;
    assign rx_valid_o=transport_rx_valid && rx_open;
    assign rx_channel_o=transport_rx_channel;
    assign rx_payload_o=transport_rx_payload;
    assign rx_length_o=transport_rx_length;
    workstation_task3_pair_config_service #(.ALLOW_BUSINESS(ALLOW_BUSINESS)) config_owner(
        .clk_i(clk_i),.reset_ni(reset_ni),.owner_reset_ni(command_reset_n),
        .command_valid_i(command_valid),.command_write_i(command_write),.command_address_i(command_address),
        .command_data_i(command_data),.command_strobes_i(command_strobes),.command_ready_o(command_ready),
        .response_error_o(response_error),.response_data_o(response_data),
        .link_ready_i(probe_ready),.link_fault_i(transport_fault),.peer_panic_i(peer_panic || external_panic_i),.link_failure_code_i(failure_code),
        .tx_packets_i(tx_packets),.rx_packets_i(rx_packets),.crc_errors_i(crc_errors),.sequence_errors_i(sequence_errors),
        .rejected_packets_i(rejected_packets),.overflow_count_i(overflow_count),.congestion_cycles_i(congestion_cycles),
        .last_rtt_cycles_i(last_rtt),.max_rtt_cycles_i(max_rtt),.probe_results_i(probe_results),.link_timeouts_i(link_timeouts),
        .local_boot_o(local_boot_o),.peer_boot_o(peer_boot_o),.session_o(session_o),.generation_o(generation_o),
        .probe_enable_o(probe_enable_o),.budget_validated_o(budget_validated_o),.business_enable_o(business_enable_o),
        .record_arm_o(record_arm_o),.record_cancel_o(record_cancel_o),.panic_o(local_panic));
    workstation_task3_lcd_transport #(.EXPERIMENT_ENABLE(EXPERIMENT_ENABLE),.ALLOW_BUSINESS(ALLOW_BUSINESS)) transport(
        .clk_i(clk_i),.reset_ni(reset_ni),.enable_i(probe_enable_o),.panic_i(panic_o),
        .budget_validated_i(budget_validated_o && business_enable_o),
        .local_boot_i(local_boot_o),.peer_boot_i(peer_boot_o),.session_i(session_o),
        .tx_valid_i(tx_valid_i && tx_open),.tx_ready_o(transport_tx_ready),.tx_channel_i(tx_channel_i),
        .tx_payload_i(tx_payload_i),.tx_length_i(tx_length_i),.rx_valid_o(transport_rx_valid),.rx_ready_i(rx_ready_i && rx_open),
        .rx_channel_o(transport_rx_channel),.rx_payload_o(transport_rx_payload),.rx_length_o(transport_rx_length),
        .link_ready_o(probe_ready),.business_ready_o(transport_business_ready),.pad_drive_o(pad_drive),
        .fault_o(transport_fault),.failure_code_o(failure_code),.peer_panic_o(transport_peer_panic),
        .phy_tx_data_o(tx_data),.phy_tx_req_o(tx_req),.phy_rx_ack_o(rx_ack),.phy_panic_o(),
        .phy_rx_data_i(rx_data),.phy_rx_req_i(rx_req),.phy_tx_ack_i(tx_ack),.phy_peer_panic_i(peer_panic_pad),
        .tx_packets_o(tx_packets),.rx_packets_o(rx_packets),.crc_errors_o(crc_errors),.sequence_errors_o(sequence_errors),
        .rejected_packets_o(rejected_packets),.overflow_count_o(overflow_count),.congestion_cycles_o(congestion_cycles),
        .last_rtt_cycles_o(last_rtt),.max_rtt_cycles_o(max_rtt),.probe_results_o(probe_results),.link_timeouts_o(link_timeouts));
    // A local request survives the immediate config revocation for >=1 ms at
    // 50 MHz. This is an offered emergency level, not peer acceptance evidence.
    workstation_task3_lcd_pins #(.EXPERIMENT_ENABLE(EXPERIMENT_ENABLE),.ROLE_M(ROLE_M)) pins(
        .drive_enable_i(reset_ni && (pad_drive || held_panic || local_panic || external_wire_panic)),.tx_data_i(tx_data),.tx_req_i(tx_req),.rx_ack_i(rx_ack),
        .panic_i(local_panic || held_panic || external_wire_panic),.rx_data_o(rx_data),.rx_req_o(rx_req),.tx_ack_o(tx_ack),.peer_panic_o(peer_panic_pad),
        .lcd_r(lcd_r),.lcd_g(lcd_g),.lcd_b(lcd_b),.lcd_pclk(lcd_pclk),.lcd_hsync(lcd_hsync),.lcd_vsync(lcd_vsync),
        .lcd_de(lcd_de),.lcd_bl(lcd_bl),.lcd_ctp_rst(lcd_ctp_rst),.lcd_ctp_sda(lcd_ctp_sda),.lcd_ctp_scl(lcd_ctp_scl),.lcd_ctp_int(lcd_ctp_int));
endmodule
