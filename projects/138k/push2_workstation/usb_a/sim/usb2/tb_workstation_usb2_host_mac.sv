`timescale 1ns/1ps
module tb_workstation_usb2_host_mac #(
    parameter integer HIGH_SPEED = 1,
    parameter integer PHYSICAL_LINK = 0
);
    reg clk = 0;
    always #8.333 clk = ~clk;
    reg reset_n = 0, sof_enable = 0, traffic_enable = 1;
    reg fault_reset_n = 0;
    reg command_valid = 0;
    wire command_ready;
    reg [7:0] command_pid = 0;
    reg [9:0] command_length = 0;
    reg command_toggle = 0;
    reg [7:0] upload_data = 0;
    reg upload_valid = 0;
    wire upload_ready;
    wire result_valid;
    reg result_ready = 0, receive_ready = 0;
    wire [3:0] result_status, state;
    wire [7:0] result_pid, received_data, txdata;
    wire [9:0] result_length;
    wire receive_valid, receive_last, txvalid, idle, fatal;
    reg [7:0] rxdata = 0;
    reg rxvalid = 0, rxactive = 0, rxerror = 0;
    reg [1:0] line_state = 1;
    reg line_valid = 0;
    reg previous_txvalid = 0, previous_rxactive = 0;
    wire txend;
    integer cycle = 0, byte_phase = 0, eop_timer = 0;
    integer packet_length = 0, packet_count = 0, last_length = 0;
    integer checks = 0, last_start = -1000, last_end = -1000, receive_end_cycle = -1000;
    integer sof_packets = 0, last_sof_start = -1, first_sof_frame = -1;
    reg [7:0] packet [0:1023];
    reg [7:0] last_packet [0:1023];
    reg [7:0] reply [0:1023];
    reg [7:0] payload [0:511];
    reg stall_tx = 0;
    wire txready = !stall_tx && (HIGH_SPEED != 0 || byte_phase == 0);
    wire mac_txready;
    wire [7:0] mac_rxdata;
    wire mac_rxvalid, mac_rxactive, mac_rxerror, mac_line_valid;
    wire [1:0] mac_line;
    wire [31:0] sof_count;
    wire [15:0] missed_sof;
    wire [10:0] frame_number;
    wire [2:0] microframe;
    localparam integer MAX_PAYLOAD = HIGH_SPEED != 0 ? 512 : 64;

    workstation_usb2_host_mac #(.UPLOAD_TIMEOUT_CYCLES(1024), .PACKET_TIMEOUT_CYCLES(4096)) dut (
        .clk_ulpi(clk), .reset_n(reset_n), .fault_reset_n(fault_reset_n), .high_speed_i(HIGH_SPEED != 0),
        .sof_enable_i(sof_enable), .traffic_enable_i(traffic_enable),
        .command_valid_i(command_valid), .command_ready_o(command_ready), .command_pid_i(command_pid),
        .command_device_i(7'd7), .command_endpoint_i(4'd2), .command_toggle_i(command_toggle),
        .command_length_i(command_length), .transmit_data_i(upload_data), .transmit_valid_i(upload_valid),
        .transmit_ready_o(upload_ready), .result_valid_o(result_valid), .result_ready_i(result_ready),
        .result_status_o(result_status), .result_pid_o(result_pid), .result_length_o(result_length),
        .receive_data_o(received_data), .receive_valid_o(receive_valid), .receive_ready_i(receive_ready),
        .receive_last_o(receive_last), .utmi_data_o(txdata), .utmi_txvalid_o(txvalid),
        .utmi_txready_i(mac_txready), .tx_end_i(txend), .utmi_data_i(mac_rxdata), .utmi_rxvalid_i(mac_rxvalid),
        .utmi_rxactive_i(mac_rxactive), .utmi_rxerror_i(mac_rxerror), .linestate_i(mac_line), .line_valid_i(mac_line_valid),
        .idle_o(idle), .fatal_o(fatal), .sof_count_o(sof_count), .missed_sof_o(missed_sof),
        .frame_number_o(frame_number), .microframe_o(microframe), .state_o(state)
    );
    generate if (PHYSICAL_LINK != 0) begin : physical
        wire [7:0] host_data, phy_data;
        wire host_oe, host_stp, phy_dir, phy_nxt;
        wire link_fatal;
        workstation_ulpi_link link (
            .clk_ulpi(clk), .reset_n(reset_n), .ulpi_data_i(phy_data), .ulpi_dir_i(phy_dir), .ulpi_nxt_i(phy_nxt),
            .ulpi_data_o(host_data), .ulpi_data_oe_o(host_oe), .ulpi_stp_o(host_stp),
            .csr_valid_i(1'b0), .csr_ready_o(), .csr_write_i(1'b0), .csr_address_i(6'd0), .csr_data_i(8'd0),
            .csr_response_valid_o(), .csr_response_ready_i(1'b1), .csr_response_data_o(), .csr_response_error_o(),
            .utmi_data_i(txdata), .utmi_txvalid_i(txvalid), .utmi_tx_nopid_i(1'b0), .utmi_txready_o(mac_txready),
            .utmi_data_o(mac_rxdata), .utmi_rxvalid_o(mac_rxvalid), .utmi_rxactive_o(mac_rxactive),
            .utmi_rxerror_o(mac_rxerror), .utmi_linestate_o(mac_line), .vbus_state_o(), .id_state_o(),
            .host_disconnect_o(), .tx_abort_o(), .fatal_error_o(link_fatal), .received_bytes_o(), .transmitted_bytes_o(),
            .rxcmd_count_o(), .rxcmd_valid_o(mac_line_valid)
        );
        usb3300_packet_model #(.HIGH_SPEED(HIGH_SPEED)) phy (
            .clk(clk), .reset_n(reset_n), .link_data_i(host_data), .link_oe_i(host_oe), .link_stp_i(host_stp),
            .byte_ready_i(txready), .stall_i(stall_tx), .peer_data_i(rxdata), .peer_valid_i(rxvalid),
            .peer_active_i(rxactive), .peer_error_i(rxerror), .peer_line_i(line_state),
            .peer_disconnect_i(1'b0), .peer_ready_o(), .usb_txdata_o(), .usb_txvalid_o(), .usb_txactive_o(),
            .phy_data_o(phy_data), .phy_data_oe_o(), .phy_dir_o(phy_dir), .phy_nxt_o(phy_nxt)
        );
        assign txend = host_stp && reset_n;
        always @(posedge clk) if (reset_n && link_fatal && !fatal) $fatal(1, "unexpected physical link fatal");
    end else begin : logical
        assign mac_txready = txready;
        assign txend = previous_txvalid && !txvalid;
        assign mac_rxdata = rxdata;
        assign mac_rxvalid = rxvalid;
        assign mac_rxactive = rxactive;
        assign mac_rxerror = rxerror;
        assign mac_line = line_state;
        assign mac_line_valid = line_valid;
    end endgenerate

    function automatic [15:0] crc16(input integer length);
        reg [15:0] crc;
        integer byte_index, bit_index;
        begin
            crc = 16'hffff;
            for (byte_index = 0; byte_index < length; byte_index = byte_index + 1)
                for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1)
                    crc = (crc[0] ^ payload[byte_index][bit_index]) ? (crc >> 1) ^ 16'ha001 : crc >> 1;
            crc16 = ~crc;
        end
    endfunction

    function automatic reg token_crc_valid(input [15:0] token);
        reg [4:0] crc;
        begin
            crc = 5'h1f;
            for (integer bit_index = 0; bit_index < 11; bit_index = bit_index + 1)
                crc = (crc[0] ^ token[bit_index]) ? (crc >> 1) ^ 5'h14 : crc >> 1;
            token_crc_valid = token[15:11] == ~crc;
        end
    endfunction

    task automatic check(input reg condition, input string message);
        begin checks = checks + 1; if (!condition) $fatal(1, "%s: HS=%0d cycle=%0d state=%0d", message, HIGH_SPEED, cycle, state); end
    endtask

    task automatic wait_cycles(input integer count);
        begin repeat (count) @(negedge clk); end
    endtask

    always @(posedge clk) begin
        cycle = cycle + 1;
        if (!reset_n) begin
            previous_txvalid <= 0; previous_rxactive <= 0; packet_length = 0;
        end else begin
            previous_txvalid <= txvalid; previous_rxactive <= rxactive;
            if (previous_rxactive && !rxactive) receive_end_cycle = cycle;
            if (txvalid && !previous_txvalid) begin
                last_start = cycle;
                if (txdata == 8'hc3 || txdata == 8'h4b) begin
                    if (HIGH_SPEED != 0) check(cycle - last_end >= 15 && cycle - last_end <= 22, "HS token/data decision window");
                end
                if (txdata == 8'hd2 && HIGH_SPEED != 0)
                    check(cycle - receive_end_cycle >= 1 && cycle - receive_end_cycle <= 12, "HS receive/ACK decision window");
            end
            if (txvalid && mac_txready) begin
                packet[packet_length] = txdata; packet_length = packet_length + 1;
                check(packet_length <= 515, "host packet exceeded 512 bytes plus PID/CRC");
            end
            if (txend && packet_length != 0) begin
                last_length = packet_length;
                for (integer copy_index = 0; copy_index < packet_length; copy_index = copy_index + 1)
                    last_packet[copy_index] = packet[copy_index];
                packet_count = packet_count + 1; packet_length = 0; last_end = cycle;
                if (last_packet[0] == 8'ha5 || last_packet[0] == 8'he1 || last_packet[0] == 8'h69 ||
                    last_packet[0] == 8'h2d || last_packet[0] == 8'hb4) begin
                    check(last_length == 3 && token_crc_valid({last_packet[2], last_packet[1]}), "token CRC5");
                    if (last_packet[0] != 8'ha5)
                        check({last_packet[2][2:0], last_packet[1]} == {4'd2, 7'd7}, "token address and endpoint");
                end
                if (last_packet[0] == 8'ha5) begin
                    check(last_length == 3, "SOF token size");
                    if (last_sof_start >= 0) check(last_start - last_sof_start == (HIGH_SPEED != 0 ? 7500 : 60000), "real SOF cadence");
                    last_sof_start = last_start;
                    if (first_sof_frame < 0) first_sof_frame = {last_packet[2][2:0], last_packet[1]};
                    check({last_packet[2][2:0], last_packet[1]} == ((first_sof_frame + (HIGH_SPEED != 0 ? sof_packets / 8 : sof_packets)) & 2047), "frame increments once per millisecond");
                    sof_packets = sof_packets + 1;
                end
            end
        end
    end

    always @(negedge clk) begin
        byte_phase = byte_phase == 39 ? 0 : byte_phase + 1;
        line_valid = 0;
        if (!reset_n) begin line_state = 1; eop_timer = 0; end
        else if (HIGH_SPEED == 0) begin
            if (txend || (previous_rxactive && !rxactive)) begin
                eop_timer = 12; line_state = 0; line_valid = 1;
            end else if (eop_timer != 0) begin
                eop_timer = eop_timer - 1;
                if (eop_timer == 0) begin line_state = 1; line_valid = 1; end
            end
        end
    end

    task automatic submit(input [7:0] pid, input integer length, input reg toggle);
        begin
            @(negedge clk); command_pid = pid; command_length = length; command_toggle = toggle; command_valid = 1;
            @(posedge clk); while (!command_ready) @(posedge clk);
            @(negedge clk); command_valid = 0;
        end
    endtask

    task automatic upload(input integer length);
        begin
            for (integer byte_index = 0; byte_index < length; byte_index = byte_index + 1) begin
                upload_valid = 1; upload_data = payload[byte_index];
                @(posedge clk); while (!upload_ready) @(posedge clk);
                @(negedge clk);
            end
            upload_valid = 0;
        end
    endtask

    task automatic wait_packet(input integer previous_count, input [7:0] pid);
        integer deadline;
        begin
            deadline = cycle + 10000;
            while (packet_count == previous_count && cycle < deadline) @(negedge clk);
            check(packet_count == previous_count + 1, "host packet count");
            check(last_packet[0] == pid, $sformatf("host PID %02x expected %02x", last_packet[0], pid));
        end
    endtask

    task automatic send_reply(input integer length, input reg error);
        begin
            wait_cycles(HIGH_SPEED != 0 ? 8 : 32);
            rxactive = 1; rxerror = error;
            for (integer byte_index = 0; byte_index < length; byte_index = byte_index + 1) begin
                rxvalid = 1; rxdata = reply[byte_index]; wait_cycles(1); rxvalid = 0;
                if (HIGH_SPEED == 0) wait_cycles(39);
            end
            rxactive = 0; rxerror = 0; rxvalid = 0;
            if (HIGH_SPEED == 0) begin line_state = 0; line_valid = 1; eop_timer = 12; end
            wait_cycles(1);
        end
    endtask

    task automatic data_reply(input reg toggle, input integer length, input reg corrupt, input reg error);
        reg [15:0] crc;
        begin
            crc = crc16(length); reply[0] = toggle ? 8'h4b : 8'hc3;
            for (integer byte_index = 0; byte_index < length; byte_index = byte_index + 1)
                reply[byte_index + 1] = payload[byte_index];
            reply[length + 1] = crc[7:0] ^ (corrupt ? 8'h80 : 8'h00); reply[length + 2] = crc[15:8];
            send_reply(length + 3, error);
        end
    endtask

    task automatic expect_result(input integer status, input integer length);
        integer deadline;
        begin
            deadline = cycle + 10000;
            while (!result_valid && cycle < deadline) @(negedge clk);
            check(result_valid && result_status == status && result_length == length, $sformatf("result status=%0d length=%0d expected=%0d/%0d", result_status, result_length, status, length));
            check(!receive_valid && !command_ready, "no receive publication or next request before result acceptance");
            wait_cycles(4);
            check(result_valid && result_status == status && result_length == length, "held result is stable");
        end
    endtask

    task automatic consume_result;
        begin result_ready = 1; wait_cycles(1); result_ready = 0; end
    endtask

    integer previous_count, held_count;
    reg [15:0] expected_crc;
    initial begin
        for (integer byte_index = 0; byte_index < 512; byte_index = byte_index + 1) payload[byte_index] = (byte_index * 37 + 19) & 255;
        wait_cycles(5); fault_reset_n = 1; reset_n = 1; wait_cycles(3);
        previous_count = packet_count; submit(8'he1, MAX_PAYLOAD, 1); upload(MAX_PAYLOAD);
        wait_packet(previous_count, 8'he1); traffic_enable = 0;
        wait_packet(previous_count + 1, 8'h4b); check(last_length == MAX_PAYLOAD + 3, "OUT complete packet");
        expected_crc = crc16(MAX_PAYLOAD);
        for (integer byte_index = 0; byte_index < MAX_PAYLOAD; byte_index = byte_index + 1)
            check(last_packet[byte_index + 1] == payload[byte_index], "OUT bytes preserved");
        check({last_packet[MAX_PAYLOAD + 2], last_packet[MAX_PAYLOAD + 1]} == expected_crc, "OUT CRC16");
        reply[0] = 8'hd2; send_reply(1, 0); expect_result(0, 0); consume_result(); traffic_enable = 1;

        previous_count = packet_count; submit(8'h69, MAX_PAYLOAD, 1); wait_packet(previous_count, 8'h69);
        data_reply(1, MAX_PAYLOAD, 0, 0); wait_packet(previous_count + 1, 8'hd2); expect_result(0, MAX_PAYLOAD);
        consume_result(); wait_cycles(4); check(receive_valid && received_data == payload[0], "committed receive held under backpressure");
        receive_ready = 1;
        for (integer byte_index = 0; byte_index < MAX_PAYLOAD; byte_index = byte_index + 1) begin
            check(receive_valid && received_data == payload[byte_index] && receive_last == (byte_index == MAX_PAYLOAD - 1), "committed payload and last");
            wait_cycles(1);
        end
        receive_ready = 0; check(!receive_valid, "receive drained once");

        for (integer fault_index = 0; fault_index < 5; fault_index = fault_index + 1) begin
            previous_count = packet_count; submit(8'h69, fault_index == 2 ? 8 : 32, 1); wait_packet(previous_count, 8'h69);
            if (fault_index == 0) data_reply(1, 17, 1, 0);
            if (fault_index == 1) data_reply(0, 17, 0, 0);
            if (fault_index == 2) data_reply(1, 9, 0, 0);
            if (fault_index == 3) data_reply(1, 17, 0, 1);
            if (fault_index == 4) begin reply[0] = 8'hc4; send_reply(1, 0); end
            if (fault_index == 1) begin wait_packet(previous_count + 1, 8'hd2); expect_result(5, 0); end
            else begin
                expect_result(fault_index == 2 ? 6 : 4, 0);
                check(packet_count == previous_count + 1, "bad packet must not be ACKed or published");
            end
            consume_result();
        end
        for (integer handshake_index = 0; handshake_index < 3; handshake_index = handshake_index + 1) begin
            previous_count = packet_count; submit(8'h69, 0, 0); wait_packet(previous_count, 8'h69);
            if (handshake_index < 2) begin reply[0] = handshake_index == 0 ? 8'h5a : 8'h1e; send_reply(1, 0); end
            expect_result(handshake_index + 1, 0); consume_result();
        end
        previous_count = packet_count; submit(8'h69, 0, 0); wait_packet(previous_count, 8'h69);
        data_reply(0, 0, 0, 0); wait_packet(previous_count + 1, 8'hd2); expect_result(0, 0); consume_result();
        previous_count = packet_count; submit(8'he1, 0, 0); wait_packet(previous_count, 8'he1); wait_packet(previous_count + 1, 8'hc3);
        reply[0] = 8'h96; send_reply(1, 0); expect_result(HIGH_SPEED != 0 ? 9 : 4, 0); consume_result();
        previous_count = packet_count; submit(8'hb4, 0, 0);
        if (HIGH_SPEED != 0) begin wait_packet(previous_count, 8'hb4); reply[0] = 8'hd2; send_reply(1, 0); expect_result(0, 0); end
        else begin expect_result(8, 0); check(previous_count == packet_count, "FS rejects PING without bus activity"); end
        consume_result();
        previous_count = packet_count; submit(8'he1, 4, 0); upload(2); expect_result(7, 0);
        check(packet_count == previous_count, "partial upload never starts a transaction");
        sof_enable = 1; wait_cycles(HIGH_SPEED != 0 ? 65000 : 185000);
        check(result_valid && result_status == 7 && sof_count >= (HIGH_SPEED != 0 ? 9 : 4), "held result cannot stop SOF");
        check(missed_sof == 0 && !fatal, "no missed SOF or fatal");
        consume_result();
        held_count = sof_count; while (sof_count == held_count) wait_cycles(1);
        previous_count = packet_count; submit(8'h69, 8, 1); wait_packet(previous_count, 8'h69);
        data_reply(1, 8, 0, 0); wait_packet(previous_count + 1, 8'hd2); expect_result(0, 8); consume_result();
        held_count = sof_count; wait_cycles(HIGH_SPEED != 0 ? 16000 : 125000);
        check(receive_valid && received_data == payload[0] && !command_ready && sof_count >= held_count + 2, "unread committed packet cannot stop SOF");
        receive_ready = 1; wait_cycles(8); receive_ready = 0; check(!receive_valid, "held receive fully drained");
        held_count = sof_count; while (sof_count == held_count) wait_cycles(1);
        wait_cycles(HIGH_SPEED != 0 ? 6750 : 55500);
        previous_count = packet_count; submit(8'he1, 1, 0); upload(1);
        wait_packet(previous_count, 8'ha5); wait_packet(previous_count + 1, 8'he1);
        wait_packet(previous_count + 2, 8'hc3); reply[0] = 8'hd2; send_reply(1, 0); expect_result(0, 0); consume_result();
        check(missed_sof == 0 && !fatal, "frame-boundary admission preserves SOF deadline");
        sof_enable = 0; wait_cycles(100);
        previous_count = packet_count; stall_tx = 1; submit(8'h69, 0, 0); wait_cycles(4200);
        check(fatal && !txvalid && !result_valid && packet_count == previous_count, "stalled PHY requires reset, no false completion");
        reset_n = 0; wait_cycles(4);
        check(fatal, "transaction reset cannot erase the persistent MAC fault");
        stall_tx = 0; sof_enable = 1; reset_n = 1; wait_cycles(4);
        check(fatal && !command_ready && !txvalid, "persistent fault prevents scheduling after transaction reset");
        reset_n = 0; fault_reset_n = 0; sof_enable = 0; wait_cycles(4); fault_reset_n = 1; reset_n = 1; wait_cycles(4);
        check(!fatal && command_ready && !result_valid && !receive_valid, "reset cancels state without stale result");
        $display("PASS workstation_usb2_host_mac: HS=%0d physical=%0d, %0d checks, CRC/commit/duplicates/faults/SOF/backpressure", HIGH_SPEED, PHYSICAL_LINK, checks);
        $finish;
    end
    initial begin #20000000; $fatal(1, "MAC regression timed out state=%0d", state); end
endmodule
