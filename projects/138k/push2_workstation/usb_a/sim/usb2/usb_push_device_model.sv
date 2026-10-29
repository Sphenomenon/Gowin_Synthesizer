`timescale 1ns/1ps
module usb_push_device_model (
    input wire clk, reset, enable,
    input wire [7:0] utmi_rxdata,
    input wire utmi_rxvalid, utmi_rxactive,
    input wire [1:0] utmi_linestate,
    input wire utmi_txready,
    output wire [7:0] utmi_txdata,
    output wire utmi_txvalid,
    output wire [1:0] utmi_xcvr,
    output wire utmi_termsel, chirp, high_speed,
    input wire midi_valid_i,
    input wire [31:0] midi_data_i,
    output wire midi_ready_o,
    output reg configured,
    output reg [6:0] device_address,
    output reg [31:0] display_headers, display_bytes, midi_out_packets, midi_in_acked
);
    reg [14:0] se0_count;
    wire bus_reset, suspended;
    always @(posedge clk or posedge reset)
        if (reset) se0_count <= 0;
        else if (utmi_linestate != 0) se0_count <= 0;
        else if (!se0_count[14]) se0_count <= se0_count + 1'b1;
    midi_usb_hs_phy phy (
        .clk(clk), .reset(reset), .enable(enable), .se0_reset(se0_count[14]),
        .bus_active(utmi_rxactive || utmi_txvalid), .bus_reset(bus_reset), .suspended(suspended),
        .line_state(utmi_linestate), .opmode(), .xcvr(utmi_xcvr), .termsel(utmi_termsel),
        .dppd(), .dmpd(), .chirp(chirp), .high_speed(high_speed), .state()
    );
    wire [7:0] pid, rx_byte;
    wire [3:0] token_ep;
    wire token_valid, handshake_valid, rx_valid, rx_strb, rx_complete, rx_crc_error;
    midi_usbf_sie_rx receiver (
        .clk_i(clk), .rst_i(reset), .enable_i(enable && !bus_reset && !suspended && !chirp),
        .utmi_data_i(utmi_rxdata), .utmi_rxvalid_i(utmi_rxvalid), .utmi_rxactive_i(utmi_rxactive),
        .current_addr_i(device_address), .pid_o(pid), .frame_valid_o(), .frame_number_o(),
        .token_valid_o(token_valid), .token_addr_o(), .token_ep_o(token_ep), .token_crc_err_o(),
        .handshake_valid_o(handshake_valid), .data_valid_o(rx_valid), .data_strb_o(rx_strb),
        .data_o(rx_byte), .data_last_o(), .data_crc_err_o(rx_crc_error), .data_complete_o(rx_complete)
    );
    reg tx_request;
    reg [7:0] tx_pid;
    reg [3:0] tx_endpoint;
    reg [9:0] tx_index, tx_length;
    wire tx_accept, tx_byte_accept;
    wire data_packet = tx_pid == 8'hc3 || tx_pid == 8'h4b;
    reg [31:0] midi_pending_data;
    reg midi_pending;
    reg descriptor_config;
    function automatic [7:0] descriptor_byte(input bit config_descriptor, input [9:0] offset);
        if (config_descriptor) begin
            case (offset)
                0: descriptor_byte = 9;
                1: descriptor_byte = 2;
                2: descriptor_byte = 9;
                5: descriptor_byte = 1;
                7: descriptor_byte = 8'h80;
                8: descriptor_byte = 50;
                default: descriptor_byte = 0;
            endcase
        end else begin
            case (offset)
                0: descriptor_byte = 18;
                1: descriptor_byte = 1;
                3: descriptor_byte = 2;
                7: descriptor_byte = 64;
                8: descriptor_byte = 8'h82;
                9: descriptor_byte = 8'h29;
                10: descriptor_byte = high_speed ? 8'h67 : 8'h99;
                11: descriptor_byte = high_speed ? 8'h19 : 8'h99;
                13: descriptor_byte = 1;
                17: descriptor_byte = 1;
                default: descriptor_byte = 0;
            endcase
        end
    endfunction
    wire [7:0] tx_byte = tx_endpoint == 2 ? 8'(midi_pending_data >> (tx_index * 8)) :
                                            descriptor_byte(descriptor_config, tx_index);
    midi_usbf_sie_tx transmitter (
        .clk_i(clk), .rst_i(reset), .enable_i(enable && !bus_reset && !suspended), .chirp_i(chirp),
        .utmi_txready_i(utmi_txready), .tx_valid_i(tx_request), .tx_pid_i(tx_pid),
        .data_valid_i(data_packet), .data_strb_i(tx_length != 0), .data_i(tx_byte),
        .data_last_i(tx_length == 0 || tx_index + 1 >= tx_length), .utmi_data_o(utmi_txdata),
        .utmi_txvalid_o(utmi_txvalid), .tx_accept_o(tx_accept), .data_accept_o(tx_byte_accept)
    );
    reg [2:0] toggle_in, toggle_out;
    reg rx_wait, rx_setup, rx_overflow, decode_setup;
    reg [3:0] rx_endpoint;
    reg [9:0] rx_count;
    reg [63:0] setup_packet;
    reg [127:0] packet_prefix;
    reg control_read, control_status, control_stall;
    reg [1:0] control_action;
    reg [15:0] control_value;
    reg [9:0] control_length;
    reg ack_wait;
    reg [3:0] ack_endpoint;
    wire [7:0] request_type = setup_packet[7:0], request = setup_packet[15:8];
    wire [15:0] value = setup_packet[31:16], request_index = setup_packet[47:32];
    wire [15:0] requested = setup_packet[63:48];
    wire [9:0] max_packet = rx_endpoint == 0 || !high_speed ? 10'd64 : 10'd512;
    assign midi_ready_o = configured && !bus_reset && !midi_pending;

    always @(posedge clk or posedge reset) begin
        if (reset) begin
            configured <= 0; device_address <= 0;
            tx_request <= 0; tx_pid <= 0; tx_endpoint <= 0; tx_index <= 0; tx_length <= 0;
            midi_pending_data <= 0; midi_pending <= 0; descriptor_config <= 0;
            toggle_in <= 0; toggle_out <= 0; rx_wait <= 0; rx_setup <= 0; rx_overflow <= 0;
            rx_endpoint <= 0; rx_count <= 0; setup_packet <= 0; packet_prefix <= 0; decode_setup <= 0;
            control_read <= 0; control_status <= 0; control_stall <= 0;
            control_action <= 0; control_value <= 0; control_length <= 0; ack_wait <= 0; ack_endpoint <= 0;
            display_headers <= 0; display_bytes <= 0; midi_out_packets <= 0; midi_in_acked <= 0;
        end else if (bus_reset || !enable) begin
            configured <= 0; device_address <= 0; tx_request <= 0;
            midi_pending <= 0; toggle_in <= 0; toggle_out <= 0; rx_wait <= 0;
            decode_setup <= 0; control_read <= 0; control_status <= 0;
            control_stall <= 0; control_action <= 0; ack_wait <= 0;
            display_headers <= 0; display_bytes <= 0; midi_out_packets <= 0; midi_in_acked <= 0;
        end else begin
            decode_setup <= 0;
            if (tx_accept) tx_request <= 0;
            if (tx_byte_accept && data_packet && tx_length != 0) tx_index <= tx_index + 1'b1;
            if (midi_valid_i && midi_ready_o) begin
                midi_pending_data <= midi_data_i;
                midi_pending <= 1;
            end
            if (token_valid) begin
                ack_wait <= 0;
                if (pid == 8'he1 || pid == 8'h2d) begin
                    rx_wait <= 1; rx_endpoint <= token_ep; rx_count <= 0; rx_overflow <= 0;
                    rx_setup <= pid == 8'h2d && token_ep == 0;
                    packet_prefix <= 0;
                    if (pid == 8'h2d && token_ep == 0) begin
                        control_read <= 0; control_status <= 0; control_stall <= 0;
                        control_action <= 0; toggle_in[0] <= 1; toggle_out[0] <= 0; setup_packet <= 0;
                    end
                end else if (pid == 8'h69) begin
                    tx_endpoint <= token_ep; tx_index <= 0; tx_length <= 0; tx_request <= 1;
                    if (token_ep == 0 && !control_stall && (control_read || control_status)) begin
                        tx_pid <= toggle_in[0] ? 8'h4b : 8'hc3;
                        tx_length <= control_status ? 10'd0 : control_length;
                        ack_wait <= 1; ack_endpoint <= 0;
                    end else if (token_ep == 2 && configured && midi_pending) begin
                        tx_pid <= toggle_in[2] ? 8'h4b : 8'hc3; tx_length <= 4;
                        ack_wait <= 1; ack_endpoint <= 2;
                    end else tx_pid <= token_ep == 0 && control_stall ? 8'h1e : 8'h5a;
                end else if (pid == 8'hb4) begin
                    tx_request <= 1;
                    tx_pid <= configured && (token_ep == 1 || token_ep == 2) ? 8'hd2 : 8'h1e;
                end
            end
            if (rx_wait && rx_valid && rx_strb) begin
                if (rx_count >= max_packet) rx_overflow <= 1;
                if (rx_setup && rx_count < 8) setup_packet[rx_count*8 +: 8] <= rx_byte;
                if (rx_count < 16) packet_prefix[rx_count*8 +: 8] <= rx_byte;
                if (rx_count < 1023) rx_count <= rx_count + 1'b1;
            end
            if (rx_wait && rx_complete) begin
                rx_wait <= 0;
                if (rx_crc_error || rx_overflow || (pid != 8'hc3 && pid != 8'h4b))
                    $fatal(1, "Push peer invalid data ep=%0d count=%0d crc=%b", rx_endpoint, rx_count, rx_crc_error);
                tx_request <= 1;
                tx_pid <= 8'hd2;
                if (rx_setup) begin
                    if (rx_count != 8 || pid != 8'hc3) $fatal(1, "Push peer malformed setup");
                    decode_setup <= 1;
                end else if (rx_endpoint == 0) begin
                    if (rx_count != 0) $fatal(1, "Push peer nonzero status OUT");
                    control_read <= 0;
                end else if (!configured || (rx_endpoint != 1 && rx_endpoint != 2))
                    $fatal(1, "Push peer unexpected OUT endpoint");
                else if ((pid == 8'h4b) == toggle_out[rx_endpoint]) begin
                    toggle_out[rx_endpoint] <= !toggle_out[rx_endpoint];
                    if (rx_endpoint == 2) begin
                        if (rx_count == 0 || rx_count[1:0] != 0) $fatal(1, "Push peer partial MIDI OUT");
                        midi_out_packets <= midi_out_packets + 1;
                    end else if (rx_count == 16 && packet_prefix == 128'h88aaccff) begin
                        display_headers <= display_headers + 1;
                        display_bytes <= 0;
                    end else begin
                        if (display_headers == 0 || rx_count != max_packet || display_bytes + 32'(rx_count) > 327680)
                            $fatal(1, "Push peer display framing count=%0d bytes=%0d", rx_count, display_bytes);
                        display_bytes <= display_bytes + 32'(rx_count);
                    end
                end
            end
            if (handshake_valid && pid == 8'hd2 && ack_wait) begin
                ack_wait <= 0; toggle_in[ack_endpoint] <= !toggle_in[ack_endpoint];
                if (ack_endpoint == 2) begin
                    midi_pending <= 0; midi_in_acked <= midi_in_acked + 1;
                end else if (control_status) begin
                    control_status <= 0;
                    if (control_action == 1) device_address <= control_value[6:0];
                    if (control_action == 2) configured <= control_value[0];
                    control_action <= 0;
                end else control_read <= 0;
            end
            if (decode_setup) begin
                control_stall <= 1; control_read <= 0; control_status <= 0; control_action <= 0;
                control_value <= value;
                if (request_type == 8'h80 && request == 6 && request_index == 0 &&
                    (value == 16'h0100 || value == 16'h0200)) begin
                    descriptor_config <= value == 16'h0200;
                    control_length <= 10'(requested < (value == 16'h0200 ? 9 : 18) ? requested :
                                         (value == 16'h0200 ? 9 : 18));
                    control_read <= requested != 0; control_stall <= 0;
                end else if (request_type == 0 && request_index == 0 && requested == 0 &&
                             ((request == 5 && value <= 127) || (request == 9 && value <= 1))) begin
                    control_status <= 1; control_stall <= 0;
                    control_action <= request == 5 ? 2'd1 : 2'd2;
                end
            end
        end
    end
endmodule
