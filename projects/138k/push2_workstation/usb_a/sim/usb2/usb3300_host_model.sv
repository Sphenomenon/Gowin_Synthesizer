module usb3300_host_model #(
    parameter integer HIGH_SPEED = 1
)(
    input wire clk_ulpi,
    input wire reset_n,
    input wire runtime_i,
    input wire attached_i,
    input wire stall_i,
    input wire [7:0] link_data_i,
    input wire link_oe_i,
    input wire link_stp_i,
    output wire [7:0] phy_data_o,
    output wire phy_oe_o,
    output wire phy_dir_o,
    output wire phy_nxt_o,
    input wire [7:0] device_txdata_i,
    input wire device_txvalid_i,
    input wire device_chirp_i,
    input wire [1:0] device_xcvr_i,
    input wire device_term_i,
    output wire device_txready_o,
    output wire [7:0] device_rxdata_o,
    output wire device_rxvalid_o,
    output wire device_rxactive_o,
    output wire [1:0] device_line_o,
    output wire [7:0] function_o,
    output wire [31:0] normal_packets_o
);
    wire [7:0] register_data, packet_data;
    wire register_oe, register_dir, register_nxt, packet_oe, packet_dir, packet_nxt;
    wire chirp_valid;
    wire [7:0] chirp_data;
    wire peer_ready;
    reg [5:0] byte_phase_q;
    reg [3:0] full_speed_eop_q;
    reg [5:0] response_gap_q;
    reg previous_packet_q;
    reg [31:0] normal_packets_q;
    reg previous_txactive_q;
    wire peer_active = runtime_i && attached_i && device_txvalid_i && response_gap_q == 0;
    wire active_packet = device_rxactive_o || peer_active;
    wire [1:0] runtime_line = !attached_i ? 2'b00 : HIGH_SPEED != 0 ?
                              (active_packet ? 2'b01 : 2'b00) :
                              (full_speed_eop_q != 0 ? 2'b00 : 2'b01);
    wire byte_ready = HIGH_SPEED != 0 || byte_phase_q == 0;
    wire peripheral_dp_pullup = device_term_i && (device_xcvr_i == 0 || device_xcvr_i == 1);

    assign phy_data_o = runtime_i ? packet_data : register_data;
    assign phy_oe_o = runtime_i ? packet_oe : register_oe;
    assign phy_dir_o = runtime_i ? packet_dir : register_dir;
    assign phy_nxt_o = runtime_i ? packet_nxt : register_nxt;
    assign device_txready_o = runtime_i ? peer_ready && attached_i && response_gap_q == 0 : 1'b1;
    assign device_line_o = !attached_i ? 2'b00 : runtime_i ? runtime_line :
                           chirp_valid ? (chirp_data == 0 ? 2'b10 : 2'b01) :
                           device_chirp_i ? 2'b10 :
                           ((function_o == 8'h45 || function_o == 8'h41) && peripheral_dp_pullup) ? 2'b01 : 2'b00;
    assign normal_packets_o = normal_packets_q;

    always @(posedge clk_ulpi or negedge reset_n) begin
        if (!reset_n) begin
            byte_phase_q <= 0; full_speed_eop_q <= 0; previous_packet_q <= 0;
            response_gap_q <= 0;
            normal_packets_q <= 0; previous_txactive_q <= 0;
        end else begin
            byte_phase_q <= byte_phase_q == 39 ? 6'd0 : byte_phase_q + 6'd1;
            previous_packet_q <= active_packet;
            previous_txactive_q <= device_rxactive_o;
            if (!runtime_i) response_gap_q <= 0;
            else if (device_rxactive_o) response_gap_q <= HIGH_SPEED != 0 ? 6'd8 : 6'd32;
            else if (response_gap_q != 0) response_gap_q <= response_gap_q - 6'd1;
            if (runtime_i && previous_txactive_q && !device_rxactive_o)
                normal_packets_q <= normal_packets_q + 32'd1;
            if (!runtime_i) full_speed_eop_q <= 0;
            else if (previous_packet_q && !active_packet) full_speed_eop_q <= 4'd12;
            else if (full_speed_eop_q != 0) full_speed_eop_q <= full_speed_eop_q - 4'd1;
        end
    end

    usb3300_register_model #(.HOST_PORT_MODEL(1)) registers (
        .clk_ulpi(clk_ulpi), .reset_n(reset_n), .fault_i(4'd0), .link_data_i(runtime_i ? 8'd0 : link_data_i),
        .link_data_oe_i(!runtime_i && link_oe_i), .link_stp_i(!runtime_i && link_stp_i),
        .phy_data_o(register_data), .phy_data_oe_o(register_oe), .phy_dir_o(register_dir), .phy_nxt_o(register_nxt),
        .completed_o(), .scratch_o(), .device_line_i(runtime_i ? 2'b00 : device_line_o),
        .function_o(function_o), .host_chirp_valid_o(chirp_valid), .host_chirp_data_o(chirp_data)
    );

    usb3300_packet_model #(.HIGH_SPEED(HIGH_SPEED)) packets (
        .clk(clk_ulpi), .reset_n(reset_n && runtime_i), .link_data_i(link_data_i),
        .link_oe_i(link_oe_i), .link_stp_i(link_stp_i), .byte_ready_i(byte_ready), .stall_i(stall_i),
        .peer_data_i(device_txdata_i), .peer_valid_i(peer_active && peer_ready),
        .peer_active_i(peer_active), .peer_error_i(1'b0), .peer_disconnect_i(!attached_i),
        .peer_line_i(runtime_line), .peer_ready_o(peer_ready), .usb_txdata_o(device_rxdata_o),
        .usb_txvalid_o(device_rxvalid_o), .usb_txactive_o(device_rxactive_o),
        .phy_data_o(packet_data), .phy_data_oe_o(packet_oe), .phy_dir_o(packet_dir), .phy_nxt_o(packet_nxt)
    );
endmodule
