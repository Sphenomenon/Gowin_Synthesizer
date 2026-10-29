module workstation_usb2_host_port #(
    parameter integer CYCLES_PER_US = 60,
    parameter integer ATTACH_DEBOUNCE_US = 100000,
    parameter integer ROOT_RESET_US = 50000,
    parameter integer RECOVERY_US = 10000,
    parameter integer RETAINED_HS_RECOVERY_US = 200000,
    parameter integer CSR_TIMEOUT_US = 1000
)(
    input wire clk_ulpi,
    input wire reset_n,
    input wire phy_ready_i,
    input wire phy_fatal_i,
    input wire hs_enable_i,
    input wire reset_request_i,
    input wire mac_idle_i,
    input wire [1:0] linestate_i,
    input wire rxcmd_valid_i,
    input wire host_disconnect_i,
    input wire tx_abort_i,
    output wire csr_valid_o,
    input wire csr_ready_i,
    output wire csr_write_o,
    output wire [5:0] csr_address_o,
    output wire [7:0] csr_data_o,
    input wire csr_response_valid_i,
    output wire csr_response_ready_o,
    input wire [7:0] csr_response_data_i,
    input wire [2:0] csr_response_error_i,
    output wire [7:0] chirp_data_o,
    output wire chirp_valid_o,
    input wire chirp_ready_i,
    output wire connected_o,
    output wire high_speed_o,
    output wire sof_enable_o,
    output wire traffic_enable_o,
    output wire reset_active_o,
    output wire owns_tx_o,
    output reg session_reset_o,
    output wire unsupported_low_speed_o,
    output wire failed_o,
    output reg [3:0] failure_code_o,
    output wire [4:0] state_o,
    output reg [7:0] last_function_o,
    output reg [7:0] last_response_o,
    output reg [7:0] csr_retries_o,
    output reg [15:0] chirp_count_o
);
    localparam [4:0] WAIT_PHY = 0;
    localparam [4:0] WRITE_REQUEST = 1;
    localparam [4:0] WRITE_RESPONSE = 2;
    localparam [4:0] READ_REQUEST = 3;
    localparam [4:0] READ_RESPONSE = 4;
    localparam [4:0] DEBUG_REQUEST = 5;
    localparam [4:0] DEBUG_RESPONSE = 6;
    localparam [4:0] WAIT_ATTACH = 7;
    localparam [4:0] DEBOUNCE = 8;
    localparam [4:0] DEVICE_CHIRP = 9;
    localparam [4:0] FULL_SPEED_RESET = 10;
    localparam [4:0] CHIRP_START = 11;
    localparam [4:0] CHIRP_STREAM = 12;
    localparam [4:0] CHIRP_DRAIN = 13;
    localparam [4:0] HIGH_SPEED_TAIL = 14;
    localparam [4:0] RECOVERY = 15;
    localparam [4:0] ACTIVE = 16;
    localparam [4:0] LOW_SPEED = 17;
    localparam [4:0] FAILED = 18;
    localparam integer DEBOUNCE_CYCLES = ATTACH_DEBOUNCE_US * CYCLES_PER_US;
    localparam integer RESET_CYCLES = ROOT_RESET_US * CYCLES_PER_US;
    localparam integer RECOVERY_CYCLES = RECOVERY_US * CYCLES_PER_US;
    localparam integer RETAINED_HS_RECOVERY_CYCLES = RETAINED_HS_RECOVERY_US * CYCLES_PER_US;
    localparam integer CSR_CYCLES = CSR_TIMEOUT_US * CYCLES_PER_US;
    localparam integer FILTER_CYCLES = (5 * CYCLES_PER_US + 1) / 2;
    localparam integer CHIRP_CYCLES = 50 * CYCLES_PER_US;
    localparam integer CHIRP_END_CYCLES = 7000 * CYCLES_PER_US;
    localparam integer CHIRP_STOP_CYCLES = (ROOT_RESET_US - 300) * CYCLES_PER_US;
    localparam integer TURN_TIMEOUT_CYCLES = 90 * CYCLES_PER_US;
    reg [4:0] state_q;
    reg [4:0] config_return_q;
    reg [4:0] debug_return_q;
    reg [7:0] config_data_q;
    reg [1:0] line_q;
    reg connected_q;
    reg high_speed_q;
    reg hs_allowed_q;
    reg root_active_q;
    reg reset_pending_q;
    reg qualified_k_q;
    reg retained_recovery_tried_q;
    reg chirp_j_q;
    reg [31:0] wait_q;
    reg [31:0] root_q;
    reg [31:0] csr_elapsed_q;
    reg [31:0] quiesce_q;
    reg [31:0] filter_q;
    reg [31:0] chirp_q;
    reg [1:0] operation_retries_q;
    wire csr_active = state_q >= WRITE_REQUEST && state_q <= DEBUG_RESPONSE;
    (* syn_preserve = 1 *) reg enabled_state_q;
    (* syn_preserve = 1 *) reg chirp_active_q;
    wire enabled_state = enabled_state_q;
    wire disconnect_event = enabled_state && (host_disconnect_i ||
                            (!high_speed_q && line_q == 2'b00 && filter_q >= 32'(FILTER_CYCLES - 1)));
    wire runtime_reset = enabled_state && (reset_pending_q || reset_request_i);

    assign state_o = state_q;
    assign connected_o = phy_ready_i && connected_q;
    assign high_speed_o = phy_ready_i && high_speed_q;
    assign sof_enable_o = reset_n && phy_ready_i && enabled_state && !runtime_reset && !disconnect_event;
    assign traffic_enable_o = sof_enable_o && state_q == ACTIVE;
    assign reset_active_o = phy_ready_i && root_active_q;
    assign owns_tx_o = phy_ready_i && !enabled_state;
    assign unsupported_low_speed_o = phy_ready_i && state_q == LOW_SPEED;
    assign failed_o = phy_ready_i && state_q == FAILED;
    assign csr_valid_o = reset_n && phy_ready_i && !phy_fatal_i &&
                         (state_q == WRITE_REQUEST || state_q == READ_REQUEST || state_q == DEBUG_REQUEST);
    assign csr_write_o = state_q == WRITE_REQUEST;
    assign csr_address_o = state_q == DEBUG_REQUEST || state_q == DEBUG_RESPONSE ? 6'h15 : 6'h04;
    assign csr_data_o = config_data_q;
    assign csr_response_ready_o = reset_n && phy_ready_i &&
                                  (state_q == WRITE_RESPONSE || state_q == READ_RESPONSE || state_q == DEBUG_RESPONSE);
    assign chirp_valid_o = reset_n && phy_ready_i && !phy_fatal_i &&
                           chirp_active_q;
    assign chirp_data_o = chirp_j_q ? 8'hff : 8'h00;

    task automatic change_state(input [4:0] next_state);
        begin
            state_q <= next_state;
            enabled_state_q <= next_state == RECOVERY || next_state == ACTIVE;
            chirp_active_q <= next_state == CHIRP_START || next_state == CHIRP_STREAM;
        end
    endtask

    task automatic configure_phy(input [7:0] function_value, input [4:0] return_state);
        begin
            config_data_q <= function_value;
            config_return_q <= return_state;
            change_state(WRITE_REQUEST);
            csr_elapsed_q <= 0;
            operation_retries_q <= 0;
        end
    endtask

    task automatic fail_port(input [3:0] failure);
        begin
            change_state(FAILED);
            failure_code_o <= failure;
            connected_q <= 1'b0;
            high_speed_q <= 1'b0;
            root_active_q <= 1'b0;
            session_reset_o <= connected_q;
        end
    endtask

    task automatic retry_or_fail(input [4:0] request_state);
        begin
            if (csr_response_error_i == 3'd2 && operation_retries_q != 3) begin
                operation_retries_q <= operation_retries_q + 1'b1;
                if (csr_retries_o != 8'hff)
                    csr_retries_o <= csr_retries_o + 1'b1;
                change_state(request_state);
            end else
                fail_port(4'd2);
        end
    endtask

    task automatic begin_reset;
        begin
            hs_allowed_q <= hs_enable_i;
            high_speed_q <= 1'b0;
            reset_pending_q <= 1'b0;
            quiesce_q <= 0;
            qualified_k_q <= 1'b0;
            filter_q <= 0;
            chirp_q <= 0;
            chirp_j_q <= 1'b0;
            chirp_count_o <= 0;
            session_reset_o <= 1'b1;
            configure_phy(8'h50, DEVICE_CHIRP);
        end
    endtask

    always @(posedge clk_ulpi or negedge reset_n) begin
        if (!reset_n) begin
            change_state(WAIT_PHY);
            config_return_q <= WAIT_ATTACH;
            debug_return_q <= WAIT_ATTACH;
            config_data_q <= 8'h45;
            line_q <= 0;
            connected_q <= 1'b0;
            high_speed_q <= 1'b0;
            hs_allowed_q <= 1'b0;
            root_active_q <= 1'b0;
            reset_pending_q <= 1'b0;
            qualified_k_q <= 1'b0;
            retained_recovery_tried_q <= 1'b0;
            chirp_j_q <= 1'b0;
            wait_q <= 0;
            root_q <= 0;
            csr_elapsed_q <= 0;
            quiesce_q <= 0;
            filter_q <= 0;
            chirp_q <= 0;
            operation_retries_q <= 0;
            session_reset_o <= 1'b0;
            failure_code_o <= 0;
            last_function_o <= 0;
            last_response_o <= 0;
            csr_retries_o <= 0;
            chirp_count_o <= 0;
        end else begin
            session_reset_o <= 1'b0;
            if (rxcmd_valid_i)
                line_q <= linestate_i;
            if (root_active_q && root_q < 32'(RESET_CYCLES))
                root_q <= root_q + 1'b1;
            if (csr_active)
                csr_elapsed_q <= csr_elapsed_q + 1'b1;
            if (csr_response_valid_i && csr_response_ready_o)
                last_response_o <= csr_response_data_i;
            if (enabled_state && reset_request_i)
                reset_pending_q <= 1'b1;

            if (!phy_ready_i) begin
                change_state(WAIT_PHY);
                connected_q <= 1'b0;
                high_speed_q <= 1'b0;
                root_active_q <= 1'b0;
                reset_pending_q <= 1'b0;
                wait_q <= 0;
                filter_q <= 0;
                quiesce_q <= 0;
                failure_code_o <= 0;
                session_reset_o <= connected_q;
            end else if (state_q != FAILED && (phy_fatal_i || tx_abort_i)) begin
                fail_port(4'd1);
            end else if (csr_active && csr_elapsed_q >= 32'(CSR_CYCLES - 1)) begin
                fail_port(4'd3);
            end else if (disconnect_event) begin
                connected_q <= 1'b0;
                high_speed_q <= 1'b0;
                reset_pending_q <= 1'b0;
                filter_q <= 0;
                wait_q <= 0;
                session_reset_o <= 1'b1;
                debug_return_q <= WAIT_ATTACH;
                configure_phy(8'h45, DEBUG_REQUEST);
            end else if (runtime_reset && mac_idle_i) begin
                begin_reset();
            end else if (runtime_reset) begin
                if (quiesce_q >= 32'(CSR_CYCLES - 1))
                    fail_port(4'd10);
                else
                    quiesce_q <= quiesce_q + 1'b1;
            end else begin
                case (state_q)
                    WAIT_PHY: begin
                        debug_return_q <= WAIT_ATTACH;
                        configure_phy(8'h45, DEBUG_REQUEST);
                    end
                    WRITE_REQUEST: if (csr_valid_o && csr_ready_i) change_state(WRITE_RESPONSE);
                    WRITE_RESPONSE: begin
                        if (csr_response_valid_i && csr_response_ready_o) begin
                            if (csr_response_error_i != 0)
                                retry_or_fail(WRITE_REQUEST);
                            else begin
                                if (config_data_q == 8'h50) begin
                                    root_active_q <= 1'b1;
                                    root_q <= 0;
                                    line_q <= 0;
                                end else if (config_data_q == 8'h45)
                                    root_active_q <= 1'b0;
                                change_state(READ_REQUEST);
                                csr_elapsed_q <= 0;
                                operation_retries_q <= 0;
                            end
                        end
                    end
                    READ_REQUEST: if (csr_valid_o && csr_ready_i) change_state(READ_RESPONSE);
                    READ_RESPONSE: begin
                        if (csr_response_valid_i && csr_response_ready_o) begin
                            if (csr_response_error_i != 0)
                                retry_or_fail(READ_REQUEST);
                            else begin
                                last_function_o <= csr_response_data_i;
                                if (csr_response_data_i != config_data_q)
                                    fail_port(4'd4);
                                else begin
                                    change_state(config_return_q);
                                    wait_q <= 0;
                                    filter_q <= 0;
                                    csr_elapsed_q <= 0;
                                    operation_retries_q <= 0;
                                    if (config_data_q == 8'h40)
                                        high_speed_q <= 1'b1;
                                end
                            end
                        end
                    end
                    DEBUG_REQUEST: if (csr_valid_o && csr_ready_i) change_state(DEBUG_RESPONSE);
                    DEBUG_RESPONSE: begin
                        if (csr_response_valid_i && csr_response_ready_o) begin
                            if (csr_response_error_i != 0)
                                retry_or_fail(DEBUG_REQUEST);
                            else begin
                                line_q <= csr_response_data_i[1:0];
                                change_state(debug_return_q);
                                wait_q <= 0;
                                if (debug_return_q == RECOVERY && csr_response_data_i[1:0] != 2'b01) begin
                                    connected_q <= 1'b0;
                                    session_reset_o <= 1'b1;
                                    change_state(WAIT_ATTACH);
                                end else if (debug_return_q == RECOVERY) begin
                                    connected_q <= 1'b1;
                                end
                            end
                        end
                    end
                    WAIT_ATTACH: begin
                        if (line_q == 2'b01) begin
                            wait_q <= 0;
                            change_state(DEBOUNCE);
                        end else if (line_q == 2'b10) begin
                            wait_q <= 0;
                            change_state(LOW_SPEED);
                        end else if (RETAINED_HS_RECOVERY_US > 0 && hs_enable_i &&
                                     !retained_recovery_tried_q && line_q == 2'b00) begin
                            if (wait_q >= 32'(RETAINED_HS_RECOVERY_CYCLES - 1)) begin
                                retained_recovery_tried_q <= 1'b1;
                                begin_reset();
                            end else
                                wait_q <= wait_q + 1'b1;
                        end else
                            wait_q <= 0;
                    end
                    DEBOUNCE: begin
                        if (line_q != 2'b01) begin
                            wait_q <= 0;
                            change_state(WAIT_ATTACH);
                        end else if (wait_q >= 32'(DEBOUNCE_CYCLES - 1)) begin
                            connected_q <= 1'b1;
                            begin_reset();
                        end else
                            wait_q <= wait_q + 1'b1;
                    end
                    DEVICE_CHIRP: begin
                        if (!hs_allowed_q || root_q >= 32'(CHIRP_END_CYCLES))
                            change_state(FULL_SPEED_RESET);
                        else if (line_q == 2'b10) begin
                            if (filter_q >= 32'(FILTER_CYCLES - 1))
                                qualified_k_q <= 1'b1;
                            else
                                filter_q <= filter_q + 1'b1;
                        end else begin
                            filter_q <= 0;
                            if (qualified_k_q && line_q == 2'b00) begin
                                connected_q <= 1'b1;
                                change_state(CHIRP_START);
                                wait_q <= 0;
                            end else
                                qualified_k_q <= 1'b0;
                        end
                    end
                    FULL_SPEED_RESET: begin
                        if (root_q >= 32'(RESET_CYCLES)) begin
                            debug_return_q <= RECOVERY;
                            configure_phy(8'h45, DEBUG_REQUEST);
                        end
                    end
                    CHIRP_START: begin
                        if (chirp_ready_i) begin
                            change_state(CHIRP_STREAM);
                            chirp_q <= 1;
                        end else if (wait_q >= 32'(TURN_TIMEOUT_CYCLES - 1))
                            fail_port(4'd5);
                        else
                            wait_q <= wait_q + 1'b1;
                    end
                    CHIRP_STREAM: begin
                        if (!chirp_ready_i)
                            fail_port(4'd6);
                        else if (chirp_q >= 32'(CHIRP_CYCLES - 1)) begin
                            if (chirp_count_o != 16'hffff)
                                chirp_count_o <= chirp_count_o + 1'b1;
                            chirp_q <= 0;
                            if (chirp_j_q && root_q >= 32'(CHIRP_STOP_CYCLES)) begin
                                change_state(CHIRP_DRAIN);
                                wait_q <= 0;
                            end else
                                chirp_j_q <= !chirp_j_q;
                        end else
                            chirp_q <= chirp_q + 1'b1;
                    end
                    CHIRP_DRAIN: begin
                        if (rxcmd_valid_i && linestate_i == 2'b00)
                            configure_phy(8'h40, HIGH_SPEED_TAIL);
                        else if (wait_q >= 32'(TURN_TIMEOUT_CYCLES - 1))
                            fail_port(4'd7);
                        else
                            wait_q <= wait_q + 1'b1;
                    end
                    HIGH_SPEED_TAIL: begin
                        if (root_q >= 32'(RESET_CYCLES)) begin
                            root_active_q <= 1'b0;
                            change_state(RECOVERY);
                            wait_q <= 0;
                        end
                    end
                    RECOVERY, ACTIVE: begin
                        if (!high_speed_q && line_q == 0)
                            filter_q <= filter_q + 1'b1;
                        else
                            filter_q <= 0;
                        quiesce_q <= 0;
                        if (state_q == RECOVERY) begin
                            if (wait_q >= 32'(RECOVERY_CYCLES - 1))
                                change_state(ACTIVE);
                            else
                                wait_q <= wait_q + 1'b1;
                        end
                    end
                    LOW_SPEED: if (line_q != 2'b10) change_state(WAIT_ATTACH);
                    FAILED: begin end
                    default: fail_port(4'd9);
                endcase
            end
        end
    end
endmodule
