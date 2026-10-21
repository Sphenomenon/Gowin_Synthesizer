`timescale 1ns/1ps
module tb_workstation_usb2_mac_25k #(
    parameter integer HIGH_SPEED = 1,
    parameter integer NATIVE_PORT = 0,
    parameter integer NATIVE_MMIO = 0
);
    reg clk = 0;
    always #8.333 clk = ~clk;
    reg clk_ref = 0;
    always #10 clk_ref = ~clk_ref;
    reg clk_cpu = 0;
    always #10.417 if (NATIVE_MMIO != 0) clk_cpu = ~clk_cpu;
    reg cpu_cs = 0, cpu_write = 0;
    reg [7:0] cpu_address = 0;
    reg [31:0] cpu_write_data = 0;
    wire [31:0] cpu_read_data;
    wire cpu_ack, cpu_error;
    reg board_reset_n = 0, board_enable = 1, attached = 1, stall_phy = 0, reset_request = 0;
    reg device_reset = 1, device_enable = 0, mac_reset_n = 0, running = 0;
    reg [1:0] negotiation_line = 1, packet_line = 1;
    reg packet_line_valid = 0;
    wire [7:0] host_txdata, device_txdata;
    wire host_txvalid, device_txvalid, host_txready, device_txready;
    wire device_rxactive;
    wire [1:0] device_line;
    wire [7:0] device_receive_data;
    wire device_receive_valid, device_receive_active;
    reg previous_host_txvalid = 0, previous_device_rxactive = 0;
    wire host_txend = previous_host_txvalid && !host_txvalid;
    integer byte_phase = 0, turnaround = 0, eop_timer = 0, cycle = 0;
    wire byte_enable = HIGH_SPEED != 0 || byte_phase == 0;
    wire device_hs, device_configured, device_usbreset, device_chirp;
    wire [2:0] device_hsstate;
    wire [6:0] device_address;
    wire [7:0] device_out_data;
    wire device_out_valid, device_in_accept;
    reg [7:0] loopback [0:2047];
    integer write_index = 0, read_index = 0, fifo_count = 0;
    wire loopback_valid = fifo_count != 0;
    wire loopback_push = device_out_valid;
    wire loopback_pop = loopback_valid && device_in_accept;
    wire [1:0] device_opmode, device_xcvr;
    wire device_term, device_dpdown, device_dmdown;
    integer checks = 0;

    usb_cdc_core #(.USB_SPEED_HS(HIGH_SPEED != 0 ? "True" : "False")) device (
        .clk_i(clk), .rst_i(device_reset), .enable_i(device_enable),
        .utmi_data_in_i(device_receive_data), .utmi_txready_i(device_txready),
        .utmi_rxvalid_i(device_receive_valid), .utmi_rxactive_i(device_receive_active),
        .utmi_rxerror_i(1'b0), .utmi_linestate_i(device_line),
        .inport_valid_i(loopback_valid), .inport_data_i(loopback[read_index]), .outport_accept_i(fifo_count <= 1536),
        .utmi_data_out_o(device_txdata), .utmi_txvalid_o(device_txvalid), .utmi_op_mode_o(device_opmode),
        .utmi_xcvrselect_o(device_xcvr), .utmi_termselect_o(device_term), .utmi_dppulldown_o(device_dpdown),
        .utmi_dmpulldown_o(device_dmdown), .inport_accept_o(device_in_accept), .outport_valid_o(device_out_valid),
        .outport_data_o(device_out_data), .hs_active_o(device_hs), .configured_o(device_configured),
        .usb_reset_o(device_usbreset), .chirp_active_o(device_chirp), .hs_state_o(device_hsstate),
        .device_address_o(device_address)
    );
    reg command_valid = 0, command_toggle = 0;
    wire command_ready;
    reg [7:0] command_pid = 0;
    reg [6:0] command_device = 0;
    reg [3:0] command_endpoint = 0;
    reg [9:0] command_length = 0;
    reg [7:0] upload_data = 0;
    reg upload_valid = 0, result_ready = 0, receive_ready = 0;
    wire upload_ready, result_valid, receive_valid, receive_last;
    wire [3:0] result_status, mac_state;
    wire [7:0] result_pid, receive_data;
    wire [9:0] result_length;
    wire mac_idle, mac_fatal;
    wire [31:0] sof_count;
    wire [15:0] missed_sof;
    wire [10:0] frame_number;
    wire [2:0] microframe;
    reg [7:0] payload [0:511];
    reg [7:0] received [0:511];
    reg [7:0] descriptor [0:17];
    integer received_length = 0;
    reg consume_enabled = 1;
    wire transaction_reset_n, traffic_enable, native_sof_enable, host_failed, host_connected, host_hs;
    wire phy_ready, phy_failed;
    wire [4:0] port_state;
    wire [3:0] port_failure;
    wire [31:0] normal_packets;
    localparam integer MAX_PAYLOAD = HIGH_SPEED != 0 ? 512 : 64;
    generate if (NATIVE_PORT == 0) begin : direct_channel
    assign device_line = running ? (HIGH_SPEED != 0 ?
                         ((host_txvalid || device_rxactive) ? 2'b01 : 2'b00) : packet_line) : negotiation_line;
    assign host_txready = running && !device_rxactive && byte_enable;
    assign device_rxactive = running && device_txvalid && turnaround == 0;
    assign device_txready = running ? (device_rxactive && byte_enable) : 1'b1;
    assign device_receive_data = host_txdata;
    assign device_receive_valid = running && host_txvalid && host_txready;
    assign device_receive_active = running && host_txvalid;
    workstation_usb2_host_mac mac (
        .clk_ulpi(clk), .reset_n(mac_reset_n), .fault_reset_n(mac_reset_n), .high_speed_i(HIGH_SPEED != 0),
        .sof_enable_i(running), .traffic_enable_i(running),
        .command_valid_i(command_valid), .command_ready_o(command_ready), .command_pid_i(command_pid),
        .command_device_i(command_device), .command_endpoint_i(command_endpoint), .command_toggle_i(command_toggle),
        .command_length_i(command_length), .transmit_data_i(upload_data), .transmit_valid_i(upload_valid),
        .transmit_ready_o(upload_ready), .result_valid_o(result_valid), .result_ready_i(result_ready),
        .result_status_o(result_status), .result_pid_o(result_pid), .result_length_o(result_length),
        .receive_data_o(receive_data), .receive_valid_o(receive_valid), .receive_ready_i(receive_ready),
        .receive_last_o(receive_last), .utmi_data_o(host_txdata), .utmi_txvalid_o(host_txvalid),
        .utmi_txready_i(host_txready), .tx_end_i(host_txend), .utmi_data_i(device_txdata),
        .utmi_rxvalid_i(device_rxactive && device_txready), .utmi_rxactive_i(device_rxactive),
        .utmi_rxerror_i(1'b0), .linestate_i(packet_line), .line_valid_i(packet_line_valid),
        .idle_o(mac_idle), .fatal_o(mac_fatal), .sof_count_o(sof_count), .missed_sof_o(missed_sof),
        .frame_number_o(frame_number), .microframe_o(microframe), .state_o(mac_state)
    );
    end else begin : native_channel
        wire [7:0] host_data, phy_data;
        wire host_oe, host_stp, phy_oe, phy_dir, phy_nxt;
        tri [7:0] physical_data;
        assign physical_data = host_oe ? host_data : 8'hzz;
        assign physical_data = phy_oe ? phy_data : 8'hzz;
        if (NATIVE_MMIO == 0) begin : transaction_interface
        workstation_usb2_host_controller #(.ATTACH_DEBOUNCE_US(100)) host (
            .clk_ref(clk_ref), .clk_ulpi(clk), .reset_n(board_reset_n), .enable_i(board_enable),
            .hs_enable_i(1'b1), .reset_request_i(reset_request),
            .ulpi_data_i(physical_data), .ulpi_dir_i(phy_dir), .ulpi_nxt_i(phy_nxt),
            .ulpi_data_o(host_data), .ulpi_data_oe_o(host_oe), .ulpi_stp_o(host_stp),
            .command_valid_i(command_valid), .command_ready_o(command_ready), .command_pid_i(command_pid),
            .command_device_i(command_device), .command_endpoint_i(command_endpoint), .command_toggle_i(command_toggle),
            .command_length_i(command_length), .transmit_data_i(upload_data), .transmit_valid_i(upload_valid),
            .transmit_ready_o(upload_ready), .result_valid_o(result_valid), .result_ready_i(result_ready),
            .result_status_o(result_status), .result_pid_o(result_pid), .result_length_o(result_length),
            .receive_data_o(receive_data), .receive_valid_o(receive_valid), .receive_ready_i(receive_ready),
            .receive_last_o(receive_last), .transaction_reset_n_o(transaction_reset_n),
            .connected_o(host_connected), .high_speed_o(host_hs), .sof_enable_o(native_sof_enable), .traffic_enable_o(traffic_enable),
            .session_reset_o(), .reset_active_o(), .unsupported_low_speed_o(), .failed_o(host_failed),
            .mac_failed_o(mac_fatal), .phy_failed_o(phy_failed), .phy_ready_o(phy_ready),
            .port_state_o(port_state), .port_failure_code_o(port_failure), .mac_state_o(mac_state),
            .sof_count_o(sof_count), .missed_sof_o(missed_sof), .frame_number_o(frame_number), .microframe_o(microframe),
            .vendor_id_o(), .product_id_o(), .function_o(), .init_failure_code_o(), .init_stage_o(),
            .clock_failure_code_o(), .received_bytes_o(), .transmitted_bytes_o()
        );
        end else begin : cpu_interface
            workstation_usb2_host_mmio #(.ATTACH_DEBOUNCE_US(100)) host (
                .clk_cpu(clk_cpu), .clk_ref(clk_ref), .clk_ulpi(clk), .reset_n(board_reset_n),
                .reg_cs_i(cpu_cs), .reg_wr_i(cpu_write), .reg_addr_i(cpu_address), .reg_wdata_i(cpu_write_data), .reg_be_i(4'hf),
                .reg_ack_o(cpu_ack), .reg_error_o(cpu_error), .reg_rdata_o(cpu_read_data), .irq_o(),
                .ulpi_data_i(physical_data), .ulpi_dir_i(phy_dir), .ulpi_nxt_i(phy_nxt),
                .ulpi_data_o(host_data), .ulpi_data_oe_o(host_oe), .ulpi_stp_o(host_stp),
                .transaction_reset_n_o(transaction_reset_n), .phy_ready_o(phy_ready), .failed_o(host_failed),
                .high_speed_o(host_hs), .traffic_enable_o(traffic_enable), .sof_count_o(sof_count)
            );
            assign mac_fatal = host.controller.mac_failed_o;
            assign phy_failed = host.controller.phy_failed_o;
            assign host_connected = host.controller.connected_o;
            assign native_sof_enable = host.controller.sof_enable_o;
            assign missed_sof = host.controller.missed_sof_o;
            assign mac_state = host.controller.mac_state_o;
            assign port_state = host.controller.port_state_o;
            assign port_failure = host.controller.port_failure_code_o;
            assign command_ready = 0;
            assign result_valid = 0;
            assign receive_valid = 0;
            assign receive_last = 0;
            assign receive_data = 0;
            assign result_status = 0;
            assign result_pid = 0;
            assign result_length = 0;
        end
        usb3300_host_model #(.HIGH_SPEED(HIGH_SPEED)) phy (
            .clk_ulpi(clk), .reset_n(board_reset_n), .runtime_i(transaction_reset_n), .attached_i(attached),
            .stall_i(stall_phy), .link_data_i(physical_data), .link_oe_i(host_oe), .link_stp_i(host_stp),
            .phy_data_o(phy_data), .phy_oe_o(phy_oe), .phy_dir_o(phy_dir), .phy_nxt_o(phy_nxt),
            .device_txdata_i(device_txdata), .device_txvalid_i(device_txvalid), .device_chirp_i(device_chirp),
            .device_xcvr_i(device_xcvr), .device_term_i(device_term), .device_txready_o(device_txready),
            .device_rxdata_o(device_receive_data), .device_rxvalid_o(device_receive_valid),
            .device_rxactive_o(device_receive_active), .device_line_o(device_line), .function_o(),
            .normal_packets_o(normal_packets)
        );
        always @(posedge clk) begin
            if (host_oe && phy_oe) $fatal(1, "native ULPI bus contention");
            if (NATIVE_MMIO == 0 && board_reset_n && !transaction_reset_n && (result_valid || receive_valid || command_ready))
                $fatal(1, "transaction escaped native reset boundary");
        end
    end endgenerate

    always @(posedge clk) begin
        cycle = cycle + 1;
        if (device_reset) begin write_index <= 0; read_index <= 0; fifo_count <= 0; end
        else begin
            if (loopback_push) begin loopback[write_index] <= device_out_data; write_index <= (write_index + 1) % 2048; end
            if (loopback_pop) read_index <= (read_index + 1) % 2048;
            case ({loopback_push, loopback_pop})
                2'b10: fifo_count <= fifo_count + 1;
                2'b01: fifo_count <= fifo_count - 1;
                default: begin end
            endcase
        end
        if (!mac_reset_n) begin previous_host_txvalid <= 0; previous_device_rxactive <= 0; end
        else begin previous_host_txvalid <= host_txvalid; previous_device_rxactive <= device_rxactive; end
    end
    always @(negedge clk) begin
        byte_phase = byte_phase == 39 ? 0 : byte_phase + 1;
        packet_line_valid = 0;
        if (!running) begin turnaround = 0; eop_timer = 0; packet_line = 1; end
        else begin
            if (host_txvalid) turnaround = HIGH_SPEED != 0 ? 8 : 32;
            else if (turnaround > 0) turnaround = turnaround - 1;
            if (HIGH_SPEED == 0) begin
                if (host_txend || (previous_device_rxactive && !device_rxactive)) begin
                    packet_line = 0; packet_line_valid = 1; eop_timer = 12;
                end else if (eop_timer != 0) begin
                    eop_timer = eop_timer - 1;
                    if (eop_timer == 0) begin packet_line = 1; packet_line_valid = 1; end
                end
            end
        end
    end

    task automatic wait_cycles(input integer count);
        begin repeat (count) @(negedge clk); end
    endtask
    task automatic check(input reg condition, input string message);
        begin checks = checks + 1; if (!condition) $fatal(1, "%s HS=%0d cycle=%0d MAC=%0d status=%0d PID=%02x device=%0d", message, HIGH_SPEED, cycle, mac_state, result_status, result_pid, device_hsstate); end
    endtask
    task automatic cpu_access(input reg write_enable, input [7:0] address, input [31:0] data, output reg [31:0] value);
        integer deadline;
        begin
            @(negedge clk_cpu); cpu_cs = 1; cpu_write = write_enable; cpu_address = address; cpu_write_data = data;
            deadline = 0; @(negedge clk_cpu);
            while (!cpu_ack && deadline < 16) begin deadline = deadline + 1; @(negedge clk_cpu); end
            check(cpu_ack && !cpu_error, $sformatf("native CPU MMIO %02x", address)); value = cpu_read_data;
            cpu_cs = 0; @(negedge clk_cpu);
        end
    endtask
    reg [31:0] cpu_value;
    task automatic transfer(input [7:0] pid, input integer endpoint, input reg toggle, input integer length, input integer expected_status);
        integer deadline;
        reg [31:0] value;
        begin
            if (NATIVE_MMIO != 0) begin
                if (pid != 8'h69 && pid != 8'hb4)
                    for (integer byte_index = 0; byte_index < length; byte_index = byte_index + 1)
                        cpu_access(1, 8'h10, {24'd0, payload[byte_index]}, value);
                cpu_access(1, 8'h0c, {2'd0, 10'(length), toggle, 4'(endpoint), command_device, pid}, value);
                deadline = cycle + 100000; value = 0;
                while (!value[18] && cycle < deadline) cpu_access(0, 8'h08, 0, value);
                check(value[18] && !value[17], "native CPU receives complete packet result");
                cpu_access(0, 8'h18, 0, value);
                check(value[31] && value[3:0] == 4'(expected_status), "native CPU result status");
                received_length = int'(value[25:16]);
                if (consume_enabled) begin
                    for (integer byte_index = 0; byte_index < received_length; byte_index = byte_index + 1) begin
                        cpu_access(0, 8'h14, 0, value); received[byte_index] = value[7:0];
                    end
                    cpu_access(1, 8'h1c, 1, value);
                end
            end else begin
            @(negedge clk); command_pid = pid; command_endpoint = endpoint;
            command_toggle = toggle; command_length = length; command_valid = 1;
            @(posedge clk); while (!command_ready) @(posedge clk);
            @(negedge clk); command_valid = 0;
            if (pid != 8'h69) begin
                for (integer byte_index = 0; byte_index < length; byte_index = byte_index + 1) begin
                    upload_valid = 1; upload_data = payload[byte_index];
                    @(posedge clk); while (!upload_ready) @(posedge clk);
                    @(negedge clk);
                end
                upload_valid = 0;
            end
            deadline = cycle + 100000;
            while (!result_valid && cycle < deadline) @(negedge clk);
            check(result_valid && result_status == expected_status, $sformatf("transfer %02x ep%0d expected status %0d", pid, endpoint, expected_status));
            received_length = result_length;
            if (consume_enabled) begin result_ready = 1; wait_cycles(1); result_ready = 0; end
            if (consume_enabled && received_length != 0) begin
                receive_ready = 1;
                for (integer byte_index = 0; byte_index < received_length; byte_index = byte_index + 1) begin
                    check(receive_valid && receive_last == (byte_index == received_length - 1), "receive stream boundary");
                    received[byte_index] = receive_data; wait_cycles(1);
                end
                receive_ready = 0;
            end
            end
        end
    endtask
    task automatic setup(input [7:0] request_type, input [7:0] request, input [15:0] value, input [15:0] length);
        begin
            payload[0] = request_type; payload[1] = request; payload[2] = value[7:0]; payload[3] = value[15:8];
            payload[4] = 0; payload[5] = 0; payload[6] = length[7:0]; payload[7] = length[15:8];
            transfer(8'h2d, 0, 0, 8, 0);
        end
    endtask
    task automatic get_descriptor;
        integer total;
        reg toggle;
        begin
            setup(8'h80, 6, 16'h0100, 18);
            total = 0; toggle = 1;
            while (total < 18) begin
                transfer(8'h69, 0, toggle, HIGH_SPEED != 0 ? 64 : 8, 0);
                check(received_length > 0 && received_length <= 18 - total, "descriptor fragment length");
                for (integer byte_index = 0; byte_index < received_length; byte_index = byte_index + 1)
                    descriptor[total + byte_index] = received[byte_index];
                total = total + received_length; toggle = !toggle;
            end
            check(descriptor[0] == 18 && descriptor[1] == 1 && descriptor[7] == (HIGH_SPEED != 0 ? 64 : 8), "real device descriptor bytes");
            check({descriptor[9], descriptor[8]} == 16'hfb9a && {descriptor[11], descriptor[10]} == 16'hfb9b, "real device identity");
            transfer(8'he1, 0, 1, 0, 0);
        end
    endtask

    integer sof_before;
    initial begin
        wait_cycles(10); device_reset = 0; device_enable = 1;
        if (NATIVE_PORT != 0) begin
            board_reset_n = 1;
            if (NATIVE_MMIO != 0) begin repeat (10) @(negedge clk_cpu); cpu_access(1, 4, 3, cpu_value); end
            wait (traffic_enable); wait_cycles(10);
            check(!host_failed && host_connected && host_hs == (HIGH_SPEED != 0) && device_hs == (HIGH_SPEED != 0), "native reset and device negotiation");
            check(sof_count >= (HIGH_SPEED != 0 ? 80 : 10), "recovery uses actual MAC SOF packets");
        end else if (HIGH_SPEED != 0) begin
            wait (device_hsstate == 1); wait_cycles(10); negotiation_line = 0;
            wait (device_chirp); wait (!device_chirp);
            for (integer chirp_index = 0; chirp_index < 6; chirp_index = chirp_index + 1) begin
                negotiation_line = chirp_index[0] ? 1 : 2; wait_cycles(3000);
            end
            check(device_hs, "real device HS negotiation"); negotiation_line = 0;
        end else begin
            negotiation_line = 0; wait_cycles(180000); negotiation_line = 1; wait_cycles(100);
            check(!device_hs, "FS partner");
        end
        if (NATIVE_PORT == 0) begin running = 1; mac_reset_n = 1; end
        wait_cycles(100);
        get_descriptor();
        setup(0, 5, 7, 0); transfer(8'h69, 0, 1, 0, 0);
        wait_cycles(30); check(device_address == 7, "SET_ADDRESS committed after actual host ACK"); command_device = 7;
        get_descriptor();
        setup(0, 9, 1, 0); transfer(8'h69, 0, 1, 0, 0); wait_cycles(30);
        check(device_configured, "real device configuration");
        for (integer byte_index = 0; byte_index < MAX_PAYLOAD; byte_index = byte_index + 1)
            payload[byte_index] = (byte_index * 37 + 19) & 255;
        transfer(8'he1, 1, 0, MAX_PAYLOAD, 0);
        wait_cycles(40); transfer(8'h69, 2, 0, MAX_PAYLOAD, 0);
        check(received_length == MAX_PAYLOAD, "real bulk packet length");
        for (integer byte_index = 0; byte_index < MAX_PAYLOAD; byte_index = byte_index + 1)
            check(received[byte_index] == ((byte_index * 37 + 19) & 255), "real device bulk loopback bytes");
        sof_before = sof_count; wait_cycles(HIGH_SPEED != 0 ? 190000 : 185000);
        check(device_hs == (HIGH_SPEED != 0) && device_address == 7 && device_configured && !device_usbreset, "real SOFs preserve attached device across idle");
        check(sof_count > sof_before + 2 && missed_sof == 0 && !mac_fatal, "real Host-generated SOF traffic without misses");
        get_descriptor();
        if (NATIVE_PORT != 0) begin
            setup(8'h80, 6, 16'h0100, 18); consume_enabled = 0;
            transfer(8'h69, 0, 1, HIGH_SPEED != 0 ? 64 : 8, 0);
            if (NATIVE_MMIO != 0) begin
                cpu_access(0, 8'h18, 0, cpu_value); check(cpu_value[31], "hold CPU result across native cancellation");
            end else check(result_valid && !receive_valid, "native held completion before cancellation");
            if (HIGH_SPEED != 0) begin
                if (NATIVE_MMIO != 0) cpu_access(1, 4, 7, cpu_value);
                else begin reset_request = 1; wait_cycles(1); reset_request = 0; end
            end
            else begin attached = 0; device_reset = 1; end
            wait (!transaction_reset_n); wait_cycles(200);
            if (NATIVE_MMIO != 0) begin
                cpu_access(0, 8'h08, 0, cpu_value);
                check(cpu_value[19] && !cpu_value[18] && !cpu_value[17], "native CPU observes cancellation without stale completion");
                cpu_access(1, 8'h1c, 4, cpu_value);
            end else check(!result_valid && !receive_valid && !command_ready, "native cancellation removes old completion and receive data");
            if (HIGH_SPEED == 0) begin device_reset = 0; attached = 1; end
            wait (traffic_enable); wait_cycles(10); consume_enabled = 1; command_device = 0;
            check(!device_configured && device_address == 0 && host_hs == (HIGH_SPEED != 0), "native reset/reconnect cleared device session");
            get_descriptor();
            check(normal_packets > (HIGH_SPEED != 0 ? 100 : 50) && !host_failed && missed_sof == 0, "same physical PHY and MAC carried reset through real packets");
            stall_phy = 1; wait (mac_fatal); wait_cycles(200);
            check(host_failed && !traffic_enable && !native_sof_enable, "MAC watchdog closes native traffic");
            if (NATIVE_MMIO != 0) begin
                cpu_access(0, 8'h08, 0, cpu_value);
                check(cpu_value[19] && !cpu_value[18] && !cpu_value[17] && !cpu_value[16], "native fault cancels CPU transaction channel");
            end else check(!command_ready && !result_valid && !receive_valid, "MAC watchdog closes native API");
            wait_cycles(12000);
            check(mac_fatal && host_failed && !transaction_reset_n, "MAC failure remains latched after PHY resets the MAC");
            board_enable = 0; wait_cycles(200); stall_phy = 0;
            if (NATIVE_MMIO != 0) begin cpu_access(1, 4, 2, cpu_value); wait_cycles(200); end
            check(!mac_fatal, "explicit disable clears native MAC failure latch");
            board_enable = 1;
            if (NATIVE_MMIO != 0) cpu_access(1, 4, 3, cpu_value);
            wait (!phy_ready); wait (phy_ready);
            check(!mac_fatal && !phy_failed, "explicit restart completes new PHY self-test");
        end
        $display("PASS workstation_usb2_mac_25k: HS=%0d native=%0d mmio=%0d, %0d checks, descriptors/address/config/%0d-byte bulk/real SOF", HIGH_SPEED, NATIVE_PORT, NATIVE_MMIO, checks, MAX_PAYLOAD);
        $finish;
    end
    initial begin
        if (NATIVE_PORT != 0) #300000000; else #40000000;
        $fatal(1, "dual MAC/device timeout: MAC=%0d device=%0d port=%0d failure=%0d", mac_state, device_hsstate, port_state, port_failure);
    end
endmodule
