module workstation_ulpi_link #(
    parameter integer TRANSACTION_TIMEOUT_CYCLES = 60000,
    parameter integer NOPID_TIMEOUT_CYCLES = 3600000
)(
    input wire clk_ulpi,
    input wire reset_n,
    input wire [7:0] ulpi_data_i,
    input wire ulpi_dir_i,
    input wire ulpi_nxt_i,
    output reg [7:0] ulpi_data_o,
    output wire ulpi_data_oe_o,
    output wire ulpi_stp_o,
    input wire csr_valid_i,
    output wire csr_ready_o,
    input wire csr_write_i,
    input wire [5:0] csr_address_i,
    input wire [7:0] csr_data_i,
    output reg csr_response_valid_o,
    input wire csr_response_ready_i,
    output reg [7:0] csr_response_data_o,
    output reg [2:0] csr_response_error_o,
    input wire [7:0] utmi_data_i,
    input wire utmi_txvalid_i,
    input wire utmi_tx_nopid_i,
    output wire utmi_txready_o,
    output reg [7:0] utmi_data_o,
    output reg utmi_rxvalid_o,
    output reg utmi_rxactive_o,
    output reg utmi_rxerror_o,
    output reg [1:0] utmi_linestate_o,
    output reg [1:0] vbus_state_o,
    output reg id_state_o,
    output reg host_disconnect_o,
    output reg tx_abort_o,
    output reg fatal_error_o,
    output reg [31:0] received_bytes_o,
    output reg [31:0] transmitted_bytes_o,
    output reg [15:0] rxcmd_count_o,
    output reg rxcmd_valid_o
);
    localparam [3:0] IDLE = 0;
    localparam [3:0] REGISTER_COMMAND = 1;
    localparam [3:0] REGISTER_DATA = 2;
    localparam [3:0] REGISTER_STOP = 3;
    localparam [3:0] READ_WAIT = 4;
    localparam [3:0] READ_DATA = 5;
    localparam [3:0] READ_RELEASE = 6;
    localparam [3:0] TRANSMIT_COMMAND = 7;
    localparam [3:0] TRANSMIT_DATA = 8;
    localparam integer MAX_TIMEOUT_CYCLES = TRANSACTION_TIMEOUT_CYCLES > NOPID_TIMEOUT_CYCLES ?
                                            TRANSACTION_TIMEOUT_CYCLES : NOPID_TIMEOUT_CYCLES;
    localparam integer TIMER_WIDTH = MAX_TIMEOUT_CYCLES < 2 ? 1 : $clog2(MAX_TIMEOUT_CYCLES);
    localparam [TIMER_WIDTH-1:0] TIMEOUT_LIMIT = TIMER_WIDTH'(TRANSACTION_TIMEOUT_CYCLES - 1);
    localparam [TIMER_WIDTH-1:0] NOPID_LIMIT = TIMER_WIDTH'(NOPID_TIMEOUT_CYCLES - 1);
    reg [3:0] state_q;
    reg direction_q;
    reg register_write_q;
    reg [5:0] register_address_q;
    reg [7:0] register_data_q;
    reg [7:0] read_data_q;
    reg [3:0] transmit_pid_q;
    reg transmit_nopid_q;
    reg [TIMER_WIDTH-1:0] elapsed_q;
    wire bus_free = !ulpi_dir_i && !direction_q;
    wire register_active = state_q >= REGISTER_COMMAND && state_q <= READ_RELEASE;
    wire transmit_active = state_q == TRANSMIT_COMMAND || state_q == TRANSMIT_DATA;
    wire register_read = state_q == READ_WAIT || state_q == READ_DATA || state_q == READ_RELEASE;
    wire packet_end = state_q == TRANSMIT_DATA && !utmi_txvalid_i;
    wire [TIMER_WIDTH-1:0] active_limit = transmit_active && transmit_nopid_q ? NOPID_LIMIT : TIMEOUT_LIMIT;

    assign ulpi_data_oe_o = reset_n && bus_free;
    assign ulpi_stp_o = !reset_n || (bus_free && (state_q == REGISTER_STOP || packet_end));
    assign csr_ready_o = reset_n && bus_free && !fatal_error_o && state_q == IDLE &&
                         !csr_response_valid_o && !utmi_rxactive_o;
    assign utmi_txready_o = reset_n && bus_free && !fatal_error_o && ulpi_nxt_i &&
                            utmi_txvalid_i && (state_q == TRANSMIT_DATA ||
                            (state_q == TRANSMIT_COMMAND && !transmit_nopid_q));

    always @* begin
        ulpi_data_o = 8'h00;
        case (state_q)
            REGISTER_COMMAND: ulpi_data_o = {register_write_q ? 2'b10 : 2'b11, register_address_q};
            REGISTER_DATA: ulpi_data_o = register_data_q;
            TRANSMIT_COMMAND: ulpi_data_o = {2'b01, 2'b00, transmit_nopid_q ? 4'h0 : transmit_pid_q};
            TRANSMIT_DATA: ulpi_data_o = utmi_txvalid_i ? utmi_data_i : 8'h00;
            default: begin end
        endcase
    end

    always @(posedge clk_ulpi or negedge reset_n) begin
        if (!reset_n) begin
            state_q <= IDLE;
            direction_q <= 1'b0;
            register_write_q <= 1'b0;
            register_address_q <= 6'h00;
            register_data_q <= 8'h00;
            read_data_q <= 8'h00;
            transmit_pid_q <= 4'h0;
            transmit_nopid_q <= 1'b0;
            elapsed_q <= {TIMER_WIDTH{1'b0}};
            csr_response_valid_o <= 1'b0;
            csr_response_data_o <= 8'h00;
            csr_response_error_o <= 3'd0;
            utmi_data_o <= 8'h00;
            utmi_rxvalid_o <= 1'b0;
            utmi_rxactive_o <= 1'b0;
            utmi_rxerror_o <= 1'b0;
            utmi_linestate_o <= 2'b00;
            vbus_state_o <= 2'b00;
            id_state_o <= 1'b0;
            host_disconnect_o <= 1'b0;
            tx_abort_o <= 1'b0;
            fatal_error_o <= 1'b0;
            received_bytes_o <= 32'h00000000;
            transmitted_bytes_o <= 32'h00000000;
            rxcmd_count_o <= 16'h0000;
            rxcmd_valid_o <= 1'b0;
        end else begin
            direction_q <= ulpi_dir_i;
            utmi_rxvalid_o <= 1'b0;
            host_disconnect_o <= 1'b0;
            tx_abort_o <= 1'b0;
            rxcmd_valid_o <= 1'b0;
            if (csr_response_valid_o && csr_response_ready_i)
                csr_response_valid_o <= 1'b0;
            if (utmi_txready_o && transmitted_bytes_o != 32'hffffffff)
                transmitted_bytes_o <= transmitted_bytes_o + 1'b1;

            if (fatal_error_o || !ulpi_dir_i) begin
                utmi_rxactive_o <= 1'b0;
                utmi_rxerror_o <= 1'b0;
            end else if (!register_read) begin
                if (!direction_q) begin
                    if (ulpi_nxt_i) begin
                        utmi_rxactive_o <= 1'b1;
                        utmi_rxerror_o <= 1'b0;
                    end
                end else if (ulpi_nxt_i) begin
                    utmi_data_o <= ulpi_data_i;
                    utmi_rxvalid_o <= 1'b1;
                    utmi_rxactive_o <= 1'b1;
                    if (received_bytes_o != 32'hffffffff)
                        received_bytes_o <= received_bytes_o + 1'b1;
                end else begin
                    rxcmd_valid_o <= 1'b1;
                    utmi_linestate_o <= ulpi_data_i[1:0];
                    vbus_state_o <= ulpi_data_i[3:2];
                    id_state_o <= ulpi_data_i[6];
                    if (rxcmd_count_o != 16'hffff)
                        rxcmd_count_o <= rxcmd_count_o + 1'b1;
                    case (ulpi_data_i[5:4])
                        2'b00: begin utmi_rxactive_o <= 1'b0; utmi_rxerror_o <= 1'b0; end
                        2'b01: begin utmi_rxactive_o <= 1'b1; utmi_rxerror_o <= 1'b0; end
                        2'b11: begin utmi_rxactive_o <= 1'b1; utmi_rxerror_o <= 1'b1; end
                        2'b10: begin
                            host_disconnect_o <= 1'b1;
                            utmi_rxactive_o <= 1'b0;
                            utmi_rxerror_o <= 1'b0;
                        end
                    endcase
                end
            end

            if (register_active || transmit_active)
                elapsed_q <= elapsed_q + 1'b1;
            else
                elapsed_q <= {TIMER_WIDTH{1'b0}};

            if ((register_active || transmit_active) && elapsed_q == active_limit) begin
                state_q <= IDLE;
                fatal_error_o <= 1'b1;
                if (register_active) begin
                    csr_response_valid_o <= 1'b1;
                    csr_response_data_o <= 8'h00;
                    csr_response_error_o <= 3'd1;
                end else begin
                    tx_abort_o <= 1'b1;
                end
            end else begin
                case (state_q)
                    IDLE: begin
                        if (csr_valid_i && csr_ready_o) begin
                            register_write_q <= csr_write_i;
                            register_address_q <= csr_address_i;
                            register_data_q <= csr_data_i;
                            state_q <= REGISTER_COMMAND;
                        end else if (reset_n && bus_free && !fatal_error_o && !utmi_rxactive_o && utmi_txvalid_i) begin
                            transmit_pid_q <= utmi_data_i[3:0];
                            transmit_nopid_q <= utmi_tx_nopid_i;
                            state_q <= TRANSMIT_COMMAND;
                        end
                    end
                    REGISTER_COMMAND: begin
                        if (ulpi_dir_i) begin
                            state_q <= IDLE;
                            csr_response_valid_o <= 1'b1;
                            csr_response_data_o <= 8'h00;
                            csr_response_error_o <= 3'd2;
                        end else if (bus_free && ulpi_nxt_i) begin
                            state_q <= register_write_q ? REGISTER_DATA : READ_WAIT;
                        end
                    end
                    REGISTER_DATA: begin
                        if (ulpi_dir_i) begin
                            state_q <= IDLE;
                            fatal_error_o <= 1'b1;
                            csr_response_valid_o <= 1'b1;
                            csr_response_data_o <= 8'h00;
                            csr_response_error_o <= 3'd2;
                        end else if (bus_free && ulpi_nxt_i) begin
                            state_q <= REGISTER_STOP;
                        end
                    end
                    REGISTER_STOP: begin
                        state_q <= IDLE;
                        csr_response_valid_o <= 1'b1;
                        csr_response_data_o <= 8'h00;
                        csr_response_error_o <= ulpi_dir_i ? 3'd2 : 3'd0;
                        if (ulpi_dir_i)
                            fatal_error_o <= 1'b1;
                    end
                    READ_WAIT: begin
                        if (ulpi_dir_i)
                            state_q <= READ_DATA;
                    end
                    READ_DATA: begin
                        if (ulpi_dir_i && direction_q) begin
                            read_data_q <= ulpi_data_i;
                            state_q <= READ_RELEASE;
                        end else if (!ulpi_dir_i) begin
                            state_q <= IDLE;
                            fatal_error_o <= 1'b1;
                            csr_response_valid_o <= 1'b1;
                            csr_response_data_o <= 8'h00;
                            csr_response_error_o <= 3'd3;
                        end
                    end
                    READ_RELEASE: begin
                        if (bus_free) begin
                            state_q <= IDLE;
                            csr_response_valid_o <= 1'b1;
                            csr_response_data_o <= read_data_q;
                            csr_response_error_o <= 3'd0;
                        end
                    end
                    TRANSMIT_COMMAND: begin
                        if (ulpi_dir_i) begin
                            state_q <= IDLE;
                        end else if (!utmi_txvalid_i) begin
                            state_q <= IDLE;
                            fatal_error_o <= 1'b1;
                            tx_abort_o <= 1'b1;
                        end else if (bus_free && ulpi_nxt_i) begin
                            state_q <= TRANSMIT_DATA;
                        end
                    end
                    TRANSMIT_DATA: begin
                        if (ulpi_dir_i) begin
                            state_q <= IDLE;
                            fatal_error_o <= 1'b1;
                            tx_abort_o <= 1'b1;
                        end else if (bus_free && !utmi_txvalid_i) begin
                            state_q <= IDLE;
                        end
                    end
                    default: begin
                        state_q <= IDLE;
                        fatal_error_o <= 1'b1;
                    end
                endcase
            end
        end
    end
endmodule
