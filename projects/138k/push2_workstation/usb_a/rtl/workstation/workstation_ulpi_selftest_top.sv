module workstation_ulpi_selftest_top #(
    parameter integer POWER_ON_BITS = 10,
    parameter integer WINDOW_REF_CYCLES = 500000,
    parameter integer CLOCK_TIMEOUT_REF_CYCLES = 5000000,
    parameter integer EXIT_HOLD_REF_CYCLES = 500,
    parameter integer QUALIFY_EDGES = 8,
    parameter integer HEARTBEAT_WIDTH = 5,
    parameter integer STARTUP_CYCLES = 600,
    parameter integer TRANSACTION_TIMEOUT_CYCLES = 60000,
    parameter integer STAGE_TIMEOUT_CYCLES = 120000
)(
    input wire clk_50m,
    input wire usb2_ulpi_clk,
    input wire usb2_ulpi_dir,
    input wire usb2_ulpi_nxt,
    output wire usb2_ulpi_stp,
    inout wire [7:0] usb2_ulpi_data
);
    localparam integer WINDOW_WIDTH = WINDOW_REF_CYCLES < 2 ? 1 : $clog2(WINDOW_REF_CYCLES);
    reg [POWER_ON_BITS-1:0] power_count_q = 0;
    wire reset_n = &power_count_q;
    (* ASYNC_REG = "TRUE", syn_preserve = 1 *) reg [1:0] ulpi_release_q;
    wire ulpi_reset_n = ulpi_release_q[1];
    reg [23:0] ulpi_count_q;
    reg [23:0] ulpi_gray_q;
    wire [23:0] ulpi_count_next = ulpi_count_q + 1'b1;
    (* ASYNC_REG = "TRUE", syn_preserve = 1 *) reg [23:0] gray_meta_q, gray_sync_q;
    wire [23:0] observed_count;
    reg [23:0] previous_count_q;
    reg [WINDOW_WIDTH-1:0] window_timer_q;
    (* syn_preserve = 1 *) reg [23:0] window_edges_q;
    (* syn_preserve = 1 *) reg [31:0] window_count_q;
    (* syn_preserve = 1 *) reg [31:0] reference_cycles_q;
    (* ASYNC_REG = "TRUE", syn_preserve = 1 *) reg clock_input_meta_q, clock_input_sync_q;
    reg clock_input_seen_q;
    reg [WINDOW_WIDTH-1:0] input_toggle_count_q, input_high_count_q;
    wire [WINDOW_WIDTH-1:0] input_toggle_next = input_toggle_count_q + WINDOW_WIDTH'(clock_input_sync_q != clock_input_seen_q);
    wire [WINDOW_WIDTH-1:0] input_high_next = input_high_count_q + WINDOW_WIDTH'(clock_input_sync_q);
    (* syn_preserve = 1 *) reg [WINDOW_WIDTH-1:0] window_input_toggles_q, window_input_high_q;
    (* syn_preserve = 1 *) reg clock_seen_q;
    wire [7:0] link_data;
    wire link_oe, link_reset_n, phy_ready, clock_running, clock_present, clock_failed;
    wire [1:0] clock_failure;
    wire init_failed, link_fatal;
    wire [3:0] init_failure;
    wire [4:0] init_stage;
    wire [7:0] init_retries, init_last_data, function_control, interface_control, otg_control;
    wire [2:0] init_last_error;
    wire [15:0] vendor_id, product_id;
    wire [87:0] status_source = {otg_control, interface_control, function_control, product_id, vendor_id,
                                init_last_error, init_last_data, init_retries, init_failure, init_stage,
                                link_reset_n, link_fatal, init_failed, phy_ready};
    reg [87:0] status_held_q;
    reg request_q;
    (* ASYNC_REG = "TRUE", syn_preserve = 1 *) reg acknowledge_meta_q, acknowledge_sync_q;
    (* ASYNC_REG = "TRUE", syn_preserve = 1 *) reg request_meta_q, request_sync_q;
    reg acknowledge_q;
    (* syn_preserve = 1 *) reg [87:0] status_q;
    (* syn_preserve = 1 *) reg snapshot_valid_q;
    (* syn_preserve = 1 *) reg [31:0] snapshot_updates_q;
    (* syn_preserve = 1 *) reg [4:0] clock_flags_q;
    (* ASYNC_REG = "TRUE", syn_preserve = 1 *) reg [10:0] bus_meta_q, bus_sync_q;

    assign usb2_ulpi_data = link_oe ? link_data : 8'hzz;
    assign observed_count[23] = gray_sync_q[23];
    genvar gray_bit;
    generate
        for (gray_bit = 0; gray_bit < 23; gray_bit = gray_bit + 1) begin: decode_gray
            assign observed_count[gray_bit] = ^gray_sync_q[23:gray_bit];
        end
    endgenerate

    always @(posedge clk_50m)
        if (!reset_n) power_count_q <= power_count_q + 1'b1;

    always @(posedge usb2_ulpi_clk or negedge reset_n)
        if (!reset_n) ulpi_release_q <= 0;
        else ulpi_release_q <= {ulpi_release_q[0], 1'b1};

    always @(posedge usb2_ulpi_clk or negedge ulpi_reset_n) begin
        if (!ulpi_reset_n) begin
            ulpi_count_q <= 0;
            ulpi_gray_q <= 0;
            status_held_q <= 0;
            request_q <= 0;
            acknowledge_meta_q <= 0;
            acknowledge_sync_q <= 0;
        end else begin
            ulpi_count_q <= ulpi_count_next;
            ulpi_gray_q <= (ulpi_count_next >> 1) ^ ulpi_count_next;
            acknowledge_meta_q <= acknowledge_q;
            acknowledge_sync_q <= acknowledge_meta_q;
            if (request_q == acknowledge_sync_q) begin
                status_held_q <= status_source;
                request_q <= !request_q;
            end
        end
    end

    always @(posedge clk_50m or negedge reset_n) begin
        if (!reset_n) begin
            gray_meta_q <= 0;
            gray_sync_q <= 0;
            previous_count_q <= 0;
            window_timer_q <= 0;
            window_edges_q <= 0;
            window_count_q <= 0;
            reference_cycles_q <= 0;
            clock_input_meta_q <= 0;
            clock_input_sync_q <= 0;
            clock_input_seen_q <= 0;
            input_toggle_count_q <= 0;
            input_high_count_q <= 0;
            window_input_toggles_q <= 0;
            window_input_high_q <= 0;
            clock_seen_q <= 0;
            request_meta_q <= 0;
            request_sync_q <= 0;
            acknowledge_q <= 0;
            status_q <= 0;
            snapshot_valid_q <= 0;
            snapshot_updates_q <= 0;
            clock_flags_q <= 0;
            bus_meta_q <= 0;
            bus_sync_q <= 0;
        end else begin
            gray_meta_q <= ulpi_gray_q;
            gray_sync_q <= gray_meta_q;
            reference_cycles_q <= reference_cycles_q + 1'b1;
            clock_input_meta_q <= usb2_ulpi_clk;
            clock_input_sync_q <= clock_input_meta_q;
            clock_input_seen_q <= clock_input_sync_q;
            clock_flags_q <= {clock_failure, clock_failed, clock_present, clock_running};
            bus_meta_q <= {usb2_ulpi_stp, usb2_ulpi_dir, usb2_ulpi_nxt, usb2_ulpi_data};
            bus_sync_q <= bus_meta_q;
            if (observed_count != previous_count_q) clock_seen_q <= 1'b1;
            if (window_timer_q == WINDOW_WIDTH'(WINDOW_REF_CYCLES - 1)) begin
                window_timer_q <= 0;
                window_edges_q <= observed_count - previous_count_q;
                previous_count_q <= observed_count;
                window_count_q <= window_count_q + 1'b1;
                window_input_toggles_q <= input_toggle_next;
                window_input_high_q <= input_high_next;
                input_toggle_count_q <= 0;
                input_high_count_q <= 0;
            end else begin
                window_timer_q <= window_timer_q + 1'b1;
                input_toggle_count_q <= input_toggle_next;
                input_high_count_q <= input_high_next;
            end
            request_meta_q <= request_q;
            request_sync_q <= request_meta_q;
            if (request_sync_q != acknowledge_q) begin
                status_q <= status_held_q;
                acknowledge_q <= request_sync_q;
                snapshot_valid_q <= 1'b1;
                snapshot_updates_q <= snapshot_updates_q + 1'b1;
            end
        end
    end

    workstation_usb3300_host_link #(
        .HEARTBEAT_WIDTH(HEARTBEAT_WIDTH), .EXIT_HOLD_REF_CYCLES(EXIT_HOLD_REF_CYCLES),
        .QUALIFY_EDGES(QUALIFY_EDGES), .CLOCK_TIMEOUT_REF_CYCLES(CLOCK_TIMEOUT_REF_CYCLES),
        .STARTUP_CYCLES(STARTUP_CYCLES), .TRANSACTION_TIMEOUT_CYCLES(TRANSACTION_TIMEOUT_CYCLES),
        .STAGE_TIMEOUT_CYCLES(STAGE_TIMEOUT_CYCLES)
    ) u_phy (
        .clk_ref(clk_50m), .clk_ulpi(usb2_ulpi_clk), .reset_n(reset_n), .enable_i(1'b1),
        .ulpi_data_i(usb2_ulpi_data), .ulpi_dir_i(usb2_ulpi_dir), .ulpi_nxt_i(usb2_ulpi_nxt),
        .ulpi_data_o(link_data), .ulpi_data_oe_o(link_oe), .ulpi_stp_o(usb2_ulpi_stp),
        .link_reset_n_o(link_reset_n), .ready_o(phy_ready), .clock_running_o(clock_running),
        .clock_present_o(clock_present), .clock_failed_o(clock_failed), .clock_failure_code_o(clock_failure),
        .init_failed_o(init_failed), .init_failure_code_o(init_failure), .init_stage_o(init_stage),
        .init_retry_count_o(init_retries), .init_last_data_o(init_last_data), .init_last_error_o(init_last_error),
        .vendor_id_o(vendor_id), .product_id_o(product_id), .function_control_o(function_control),
        .interface_control_o(interface_control), .otg_control_o(otg_control),
        .csr_valid_i(1'b0), .csr_ready_o(), .csr_write_i(1'b0), .csr_address_i(6'd0), .csr_data_i(8'd0),
        .csr_response_valid_o(), .csr_response_ready_i(1'b1), .csr_response_data_o(), .csr_response_error_o(),
        .utmi_data_i(8'd0), .utmi_txvalid_i(1'b0), .utmi_tx_nopid_i(1'b0), .utmi_txready_o(),
        .utmi_data_o(), .utmi_rxvalid_o(), .utmi_rxactive_o(), .utmi_rxerror_o(), .utmi_txend_o(),
        .utmi_linestate_o(), .vbus_state_o(), .id_state_o(), .host_disconnect_o(), .tx_abort_o(),
        .link_fatal_o(link_fatal), .received_bytes_o(), .transmitted_bytes_o(), .rxcmd_count_o(),
        .rxcmd_valid_o()
    );
endmodule
