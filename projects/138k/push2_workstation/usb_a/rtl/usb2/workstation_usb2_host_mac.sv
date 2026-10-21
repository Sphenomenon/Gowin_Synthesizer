module workstation_usb2_host_mac #(
    parameter integer UPLOAD_TIMEOUT_CYCLES = 60000,
    parameter integer PACKET_TIMEOUT_CYCLES = 60000
)(
    input wire clk_ulpi,
    input wire reset_n,
    input wire fault_reset_n,
    input wire high_speed_i,
    input wire sof_enable_i,
    input wire traffic_enable_i,
    input wire command_valid_i,
    output wire command_ready_o,
    input wire [7:0] command_pid_i,
    input wire [6:0] command_device_i,
    input wire [3:0] command_endpoint_i,
    input wire command_toggle_i,
    input wire [9:0] command_length_i,
    input wire [7:0] transmit_data_i,
    input wire transmit_valid_i,
    output wire transmit_ready_o,
    output reg result_valid_o,
    input wire result_ready_i,
    output reg [3:0] result_status_o,
    output reg [7:0] result_pid_o,
    output reg [9:0] result_length_o,
    output wire [7:0] receive_data_o,
    output wire receive_valid_o,
    input wire receive_ready_i,
    output wire receive_last_o,
    output wire [7:0] utmi_data_o,
    output wire utmi_txvalid_o,
    input wire utmi_txready_i,
    input wire tx_end_i,
    input wire [7:0] utmi_data_i,
    input wire utmi_rxvalid_i,
    input wire utmi_rxactive_i,
    input wire utmi_rxerror_i,
    input wire [1:0] linestate_i,
    input wire line_valid_i,
    output wire idle_o,
    output reg fatal_o,
    output reg [31:0] sof_count_o,
    output reg [15:0] missed_sof_o,
    output wire [10:0] frame_number_o,
    output wire [2:0] microframe_o,
    output wire [3:0] state_o
);
    localparam [3:0] IDLE = 0, SEND = 1, WAIT_END = 2, DATA_GAP = 3,
                     WAIT_RX = 4, RECEIVE = 5, ACK_GAP = 6, FAILED = 7;
    localparam [1:0] PACKET_SOF = 0, PACKET_TOKEN = 1, PACKET_DATA = 2, PACKET_ACK = 3;
    localparam [3:0] SUCCESS = 0, NAK = 1, STALL = 2, RESPONSE_TIMEOUT = 3,
                     PROTOCOL_ERROR = 4, DUPLICATE = 5, OVERFLOW = 6,
                     UPLOAD_TIMEOUT = 7, BAD_COMMAND = 8, NYET = 9;
    localparam integer UPLOAD_WIDTH = UPLOAD_TIMEOUT_CYCLES < 2 ? 1 : $clog2(UPLOAD_TIMEOUT_CYCLES);
    localparam integer WATCHDOG_WIDTH = PACKET_TIMEOUT_CYCLES < 2 ? 1 : $clog2(PACKET_TIMEOUT_CYCLES);
    reg [7:0] transmit_buffer [0:511];
    reg [7:0] receive_buffer [0:511];
    reg [7:0] transmit_read_q, receive_read_q;
    reg [8:0] transmit_read_address;
    reg occupied_q, upload_q, pending_q, drain_q;
    reg [7:0] command_pid_q;
    reg [10:0] token_q;
    reg command_toggle_q;
    reg [9:0] command_length_q, upload_count_q, drain_count_q;
    reg [15:0] transmit_crc_q;
    reg [UPLOAD_WIDTH-1:0] upload_elapsed_q;
    reg [3:0] state_q, previous_state_q;
    reg [1:0] packet_q;
    reg [9:0] transmit_index_q, transmit_length_q;
    reg [15:0] token_bits_q;
    reg [7:0] token_pid_q;
    reg [9:0] received_count_q;
    reg [15:0] receive_crc_q;
    reg [7:0] received_pid_q, tail_old_q, tail_new_q;
    reg receive_error_q, receive_overflow_q;
    reg finish_q;
    reg [3:0] finish_status_q;
    reg [7:0] finish_pid_q;
    reg [9:0] finish_length_q;
    reg [WATCHDOG_WIDTH-1:0] packet_elapsed_q;
    reg [9:0] high_speed_gap_q;
    reg [7:0] full_speed_gap_q;
    reg full_speed_eop_q;
    reg [1:0] previous_line_q;
    reg previous_rxactive_q, previous_txvalid_q;
    reg sof_enabled_q, sof_pending_q;
    reg [15:0] frame_elapsed_q;
    reg [10:0] frame_q;
    reg [2:0] microframe_q;
    reg [7:0] transmit_byte;
    wire [15:0] frame_period = high_speed_i ? 16'd7500 : 16'd60000;
    wire [15:0] transaction_budget = high_speed_i ? 16'd900 : 16'd5000;
    wire bus_gap_ready = high_speed_i ? high_speed_gap_q >= 10'd15 :
                                      full_speed_eop_q && full_speed_gap_q >= 8'd8;
    wire room_in_frame = !sof_enable_i || frame_elapsed_q < frame_period - transaction_budget;
    wire launch_sof = !fatal_o && state_q == IDLE && !utmi_rxactive_i && bus_gap_ready && sof_enable_i && sof_pending_q;
    wire launch_transaction = state_q == IDLE && !utmi_rxactive_i && bus_gap_ready && !launch_sof &&
                              !fatal_o && pending_q && traffic_enable_i && !sof_pending_q && room_in_frame;
    wire watchdog_expired = state_q != IDLE && state_q != FAILED &&
                            packet_elapsed_q == WATCHDOG_WIDTH'(PACKET_TIMEOUT_CYCLES - 1);
    wire full_speed_eop = line_valid_i && previous_line_q == 2'b00 && linestate_i == 2'b01;
    wire receive_end = previous_rxactive_q && !utmi_rxactive_i;
    wire [8:0] receive_read_address = !drain_q ? 9'd0 :
                                    receive_ready_i && !receive_last_o ? 9'(drain_count_q + 10'd1) : drain_count_q[8:0];
    wire [9:0] payload_length = received_count_q - 10'd3;
    wire command_supported = command_pid_i == 8'he1 || command_pid_i == 8'h69 ||
                             command_pid_i == 8'h2d || (high_speed_i && command_pid_i == 8'hb4);
    wire command_length_valid = command_length_i <= (high_speed_i ? 10'd512 : 10'd64) &&
                                (command_pid_i != 8'h2d || command_length_i == 10'd8) &&
                                (command_pid_i != 8'hb4 || command_length_i == 10'd0);

    function automatic [15:0] crc16_byte(input [15:0] previous_crc, input [7:0] data);
        reg [15:0] accumulator;
        integer bit_index;
        begin
            accumulator = previous_crc;
            for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1)
                accumulator = (accumulator[0] ^ data[bit_index]) ?
                              ((accumulator >> 1) ^ 16'ha001) : (accumulator >> 1);
            crc16_byte = accumulator;
        end
    endfunction

    function automatic [15:0] token_bits(input [10:0] token);
        reg [4:0] accumulator;
        integer bit_index;
        begin
            accumulator = 5'h1f;
            for (bit_index = 0; bit_index < 11; bit_index = bit_index + 1)
                accumulator = (accumulator[0] ^ token[bit_index]) ?
                              ((accumulator >> 1) ^ 5'h14) : (accumulator >> 1);
            token_bits = {~accumulator, token};
        end
    endfunction

    assign command_ready_o = reset_n && traffic_enable_i && !occupied_q && !fatal_o;
    assign transmit_ready_o = reset_n && upload_q && !fatal_o;
    assign receive_data_o = receive_read_q;
    assign receive_valid_o = reset_n && drain_q;
    assign receive_last_o = drain_count_q + 10'd1 == result_length_o;
    assign utmi_data_o = transmit_byte;
    assign utmi_txvalid_o = reset_n && state_q == SEND;
    assign idle_o = state_q == IDLE && bus_gap_ready && !utmi_rxactive_i;
    assign frame_number_o = frame_q;
    assign microframe_o = microframe_q;
    assign state_o = state_q;

    always @(posedge clk_ulpi or negedge fault_reset_n) begin
        if (!fault_reset_n) fatal_o <= 0;
        else if (watchdog_expired || state_q >= FAILED) fatal_o <= 1;
    end

    always @* begin
        transmit_read_address = 0;
        if (state_q == SEND && packet_q == PACKET_DATA && transmit_index_q != 0) begin
            if (utmi_txready_i && transmit_index_q < command_length_q)
                transmit_read_address = transmit_index_q[8:0];
            else transmit_read_address = 9'(transmit_index_q - 10'd1);
        end
    end

    always @(posedge clk_ulpi) begin
        transmit_read_q <= transmit_buffer[transmit_read_address];
        receive_read_q <= receive_buffer[receive_read_address];
        if (transmit_valid_i && transmit_ready_o)
            transmit_buffer[upload_count_q[8:0]] <= transmit_data_i;
        if ((state_q == WAIT_RX || state_q == RECEIVE) && utmi_rxvalid_i &&
            received_count_q >= 3 && received_count_q < 515)
            receive_buffer[9'(received_count_q - 10'd3)] <= tail_old_q;
    end

    always @* begin
        transmit_byte = 8'h00;
        case (packet_q)
            PACKET_SOF, PACKET_TOKEN: begin
                case (transmit_index_q)
                    10'd0: transmit_byte = token_pid_q;
                    10'd1: transmit_byte = token_bits_q[7:0];
                    default: transmit_byte = token_bits_q[15:8];
                endcase
            end
            PACKET_DATA: begin
                if (transmit_index_q == 0) transmit_byte = command_toggle_q ? 8'h4b : 8'hc3;
                else if (transmit_index_q <= command_length_q)
                    transmit_byte = transmit_read_q;
                else if (transmit_index_q == command_length_q + 10'd1) transmit_byte = ~transmit_crc_q[7:0];
                else transmit_byte = ~transmit_crc_q[15:8];
            end
            PACKET_ACK: transmit_byte = 8'hd2;
            default: begin end
        endcase
    end

    always @(posedge clk_ulpi or negedge reset_n) begin
        if (!reset_n) begin
            occupied_q <= 0; upload_q <= 0; pending_q <= 0; drain_q <= 0;
            command_pid_q <= 0; token_q <= 0; command_toggle_q <= 0; command_length_q <= 0;
            upload_count_q <= 0; drain_count_q <= 0; transmit_crc_q <= 16'hffff;
            upload_elapsed_q <= 0;
            result_valid_o <= 0; result_status_o <= 0; result_pid_o <= 0; result_length_o <= 0;
        end else begin
            if (command_valid_i && command_ready_o) begin
                occupied_q <= 1; command_pid_q <= command_pid_i;
                token_q <= {command_endpoint_i, command_device_i};
                command_toggle_q <= command_pid_i == 8'h2d ? 1'b0 : command_toggle_i;
                command_length_q <= command_length_i;
                upload_count_q <= 0; upload_elapsed_q <= 0; transmit_crc_q <= 16'hffff;
                if (!command_supported || !command_length_valid) begin
                    result_valid_o <= 1; result_status_o <= BAD_COMMAND; result_pid_o <= 0; result_length_o <= 0;
                end else if (command_pid_i != 8'h69 && command_length_i != 0) upload_q <= 1;
                else pending_q <= 1;
            end
            if (upload_q) begin
                if (transmit_valid_i && transmit_ready_o) begin
                    transmit_crc_q <= crc16_byte(transmit_crc_q, transmit_data_i);
                    upload_count_q <= upload_count_q + 10'd1;
                end
                if (transmit_valid_i && upload_count_q + 10'd1 == command_length_q) begin
                    upload_q <= 0; pending_q <= 1;
                end else if (upload_elapsed_q == UPLOAD_WIDTH'(UPLOAD_TIMEOUT_CYCLES - 1)) begin
                    upload_q <= 0;
                    result_valid_o <= 1; result_status_o <= UPLOAD_TIMEOUT; result_pid_o <= 0; result_length_o <= 0;
                end else upload_elapsed_q <= upload_elapsed_q + 1'b1;
            end
            if (launch_transaction) pending_q <= 0;
            if (finish_q) begin
                result_valid_o <= 1; result_status_o <= finish_status_q;
                result_pid_o <= finish_pid_q; result_length_o <= finish_length_q;
            end
            if (result_valid_o && result_ready_i) begin
                result_valid_o <= 0;
                if (result_length_o != 0) begin drain_q <= 1; drain_count_q <= 0; end
                else occupied_q <= 0;
            end
            if (receive_valid_o && receive_ready_i) begin
                if (receive_last_o) begin drain_q <= 0; occupied_q <= 0; end
                else drain_count_q <= drain_count_q + 10'd1;
            end
        end
    end

    always @(posedge clk_ulpi or negedge reset_n) begin
        if (!reset_n) begin
            sof_enabled_q <= 0; sof_pending_q <= 0; frame_elapsed_q <= 0;
            frame_q <= 0; microframe_q <= 0; missed_sof_o <= 0; sof_count_o <= 0;
        end else begin
            sof_enabled_q <= sof_enable_i;
            if (!sof_enable_i) begin
                sof_pending_q <= 0; frame_elapsed_q <= 0; frame_q <= 0; microframe_q <= 0;
            end else if (!sof_enabled_q) begin
                sof_pending_q <= 1; frame_elapsed_q <= 0;
            end else begin
                if (launch_sof) sof_pending_q <= 0;
                if (frame_elapsed_q == frame_period - 16'd1) begin
                    frame_elapsed_q <= 0; sof_pending_q <= 1;
                    if (sof_pending_q && !launch_sof && missed_sof_o != 16'hffff)
                        missed_sof_o <= missed_sof_o + 16'd1;
                    if (!high_speed_i || microframe_q == 3'd7) begin
                        frame_q <= frame_q + 11'd1; microframe_q <= 0;
                    end else microframe_q <= microframe_q + 3'd1;
                end else frame_elapsed_q <= frame_elapsed_q + 16'd1;
            end
            if (state_q == WAIT_END && tx_end_i && packet_q == PACKET_SOF)
                sof_count_o <= sof_count_o + 32'd1;
        end
    end

    always @(posedge clk_ulpi or negedge reset_n) begin
        if (!reset_n) begin
            high_speed_gap_q <= 10'h3ff; full_speed_gap_q <= 8'hff; full_speed_eop_q <= 1;
            previous_line_q <= 2'b01; previous_rxactive_q <= 0; previous_txvalid_q <= 0;
        end else begin
            previous_rxactive_q <= utmi_rxactive_i;
            previous_txvalid_q <= utmi_txvalid_o;
            if (line_valid_i) previous_line_q <= linestate_i;
            if (tx_end_i || receive_end) high_speed_gap_q <= 0;
            else if (high_speed_gap_q != 10'h3ff) high_speed_gap_q <= high_speed_gap_q + 10'd1;
            if ((utmi_txvalid_o && !previous_txvalid_q) || (utmi_rxactive_i && !previous_rxactive_q))
                full_speed_eop_q <= 0;
            if (full_speed_eop) begin full_speed_eop_q <= 1; full_speed_gap_q <= 0; end
            else if (full_speed_gap_q != 8'hff) full_speed_gap_q <= full_speed_gap_q + 8'd1;
        end
    end

    always @(posedge clk_ulpi or negedge reset_n) begin
        if (!reset_n) begin
            state_q <= IDLE; previous_state_q <= IDLE; packet_q <= PACKET_SOF;
            transmit_index_q <= 0; transmit_length_q <= 0; token_bits_q <= 0; token_pid_q <= 0;
            received_count_q <= 0; receive_crc_q <= 16'hffff; received_pid_q <= 0;
            tail_old_q <= 0; tail_new_q <= 0; receive_error_q <= 0; receive_overflow_q <= 0;
            finish_q <= 0; finish_status_q <= 0; finish_pid_q <= 0; finish_length_q <= 0;
            packet_elapsed_q <= 0;
        end else begin
            previous_state_q <= state_q;
            finish_q <= 0;
            if (state_q == IDLE || state_q != previous_state_q) packet_elapsed_q <= 0;
            else if (packet_elapsed_q != WATCHDOG_WIDTH'(PACKET_TIMEOUT_CYCLES - 1))
                packet_elapsed_q <= packet_elapsed_q + 1'b1;
            if ((state_q == WAIT_RX || state_q == RECEIVE) && utmi_rxvalid_i) begin
                if (!utmi_rxactive_i) receive_error_q <= 1;
                if (received_count_q == 0) received_pid_q <= utmi_data_i;
                else begin
                    receive_crc_q <= crc16_byte(receive_crc_q, utmi_data_i);
                    tail_old_q <= tail_new_q; tail_new_q <= utmi_data_i;
                end
                if (received_count_q != 10'h3ff) received_count_q <= received_count_q + 10'd1;
                if (received_count_q >= 515) receive_overflow_q <= 1;
            end
            if ((state_q == WAIT_RX || state_q == RECEIVE) && utmi_rxerror_i) receive_error_q <= 1;
            case (state_q)
                IDLE: begin
                    if (launch_sof || launch_transaction) begin
                        state_q <= SEND; transmit_index_q <= 0; transmit_length_q <= 3;
                        packet_q <= launch_sof ? PACKET_SOF : PACKET_TOKEN;
                        token_bits_q <= token_bits(launch_sof ? frame_q : token_q);
                        token_pid_q <= launch_sof ? 8'ha5 : command_pid_q;
                    end
                end
                SEND: if (utmi_txready_i) begin
                    if (transmit_index_q + 10'd1 == transmit_length_q) state_q <= WAIT_END;
                    else transmit_index_q <= transmit_index_q + 10'd1;
                end
                WAIT_END: if (tx_end_i) begin
                    case (packet_q)
                        PACKET_SOF: state_q <= IDLE;
                        PACKET_TOKEN: begin
                            if (command_pid_q == 8'h69 || command_pid_q == 8'hb4) state_q <= WAIT_RX;
                            else state_q <= DATA_GAP;
                            received_count_q <= 0; receive_crc_q <= 16'hffff;
                            receive_error_q <= 0; receive_overflow_q <= 0;
                        end
                        PACKET_DATA: begin
                            state_q <= WAIT_RX; received_count_q <= 0; receive_crc_q <= 16'hffff;
                            receive_error_q <= 0; receive_overflow_q <= 0;
                        end
                        PACKET_ACK: begin
                            state_q <= IDLE; finish_q <= 1;
                            finish_status_q <= received_pid_q == (command_toggle_q ? 8'h4b : 8'hc3) ? SUCCESS : DUPLICATE;
                            finish_pid_q <= received_pid_q;
                            finish_length_q <= received_pid_q == (command_toggle_q ? 8'h4b : 8'hc3) ? payload_length : 10'd0;
                        end
                        default: state_q <= FAILED;
                    endcase
                end
                DATA_GAP: if (bus_gap_ready) begin
                    state_q <= SEND; packet_q <= PACKET_DATA;
                    transmit_index_q <= 0; transmit_length_q <= command_length_q + 10'd3;
                end
                WAIT_RX: begin
                    if (utmi_rxactive_i) state_q <= RECEIVE;
                    else if (high_speed_i ? high_speed_gap_q >= 10'd91 :
                             full_speed_eop_q && full_speed_gap_q >= 8'd79) begin
                        state_q <= IDLE; finish_q <= 1; finish_status_q <= RESPONSE_TIMEOUT;
                        finish_pid_q <= 0; finish_length_q <= 0;
                    end
                end
                RECEIVE: if (!utmi_rxactive_i) begin
                    finish_pid_q <= received_pid_q; finish_length_q <= 0;
                    if (receive_error_q || utmi_rxerror_i || received_count_q == 0 ||
                        received_pid_q[7:4] != ~received_pid_q[3:0]) begin
                        state_q <= IDLE; finish_q <= 1; finish_status_q <= PROTOCOL_ERROR;
                    end else if (received_count_q == 1 && (received_pid_q == 8'h5a || received_pid_q == 8'h1e)) begin
                        state_q <= IDLE; finish_q <= 1; finish_status_q <= received_pid_q == 8'h5a ? NAK : STALL;
                    end else if (command_pid_q != 8'h69 && received_count_q == 1 &&
                                 (received_pid_q == 8'hd2 || (high_speed_i && command_pid_q == 8'he1 && received_pid_q == 8'h96))) begin
                        state_q <= IDLE; finish_q <= 1; finish_status_q <= received_pid_q == 8'hd2 ? SUCCESS : NYET;
                    end else if (command_pid_q == 8'h69 && received_count_q >= 3 &&
                                 (received_pid_q == 8'hc3 || received_pid_q == 8'h4b)) begin
                        if (receive_overflow_q || payload_length > command_length_q || payload_length > (high_speed_i ? 10'd512 : 10'd64)) begin
                            state_q <= IDLE; finish_q <= 1; finish_status_q <= OVERFLOW;
                        end else if (receive_crc_q != 16'hb001) begin
                            state_q <= IDLE; finish_q <= 1; finish_status_q <= PROTOCOL_ERROR;
                        end else state_q <= ACK_GAP;
                    end else begin
                        state_q <= IDLE; finish_q <= 1; finish_status_q <= PROTOCOL_ERROR;
                    end
                end
                ACK_GAP: begin
                    if (high_speed_i ? high_speed_gap_q >= 10'd1 : full_speed_eop_q && full_speed_gap_q >= 8'd8) begin
                        state_q <= SEND; packet_q <= PACKET_ACK; transmit_index_q <= 0; transmit_length_q <= 1;
                    end
                end
                FAILED: begin end
                default: state_q <= FAILED;
            endcase
            if (watchdog_expired) state_q <= FAILED;
        end
    end
endmodule
