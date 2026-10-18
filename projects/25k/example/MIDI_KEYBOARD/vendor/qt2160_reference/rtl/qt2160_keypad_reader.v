`timescale 1ns / 1ps

// Second QT2160, 7-bit address 0x0d, Y0/Y1 x X0..X7.
// Read a complete frame before UART backpressure can delay further I2C reads.
module qt2160_keypad_reader #(
    parameter integer CLK_HZ = 50_000_000,
    parameter integer STARTUP_CYCLES = CLK_HZ / 10,
    parameter integer POLL_CYCLES = CLK_HZ / 5,
    parameter integer CALIBRATION_CYCLES = CLK_HZ / 2,
    parameter integer HALF_CYCLES = 250,
    parameter integer BUS_FREE_CYCLES = 5000,
    parameter integer TIMEOUT_CYCLES = 1_000_000,
    parameter integer NEGATIVE_THRESHOLD = 10,
    parameter integer BURST_LENGTH = 4,
    parameter integer BURST_REPETITIONS = 1,
    parameter integer DETECT_INTEGRATOR = 7
) (
    input wire clk, input wire scl_in, input wire sda_in,
    output wire scl_low, output wire sda_low,
    output reg event_valid = 0, input wire event_ready,
    output reg [3:0] key_index = 0,
    output reg [15:0] key_signal = 0, key_reference = 0,
    output reg sample_done = 0, output wire [63:0] result,
    output reg scan_done = 0, output reg [63:0] scan_result = 0
);
    localparam [3:0] STARTUP=0, IDENTIFY=1, CONFIGURE=2, CAL_WAIT=3,
        STATUS_BEFORE=4, SIGNAL_LOW=5, SIGNAL_HIGH=6, REFERENCE_LOW=7,
        REFERENCE_HIGH=8, STATUS_AFTER=9, ANALYZE=10, PUBLISH=11, READY=12, RETRY=13;
    localparam [15:0] LP_BREP = {BURST_REPETITIONS[7:0],8'h01};
    localparam integer RELEASE_LEVEL = NEGATIVE_THRESHOLD > 2 ? NEGATIVE_THRESHOLD - 2 : 1;
    reg [3:0] state = STARTUP, config_index = 0, cursor = 0;
    reg waiting = 0, configured = 0, first_status = 1;
    reg [31:0] wait_count = 0, poll_count = 0;
    reg [15:0] samples = 0, keys_before = 0, keys_after = 0, report_keys = 0;
    reg [255:0] signals = 0, references = 0;
    reg [7:0] general_status = 0, last_error = 0, chip_id = 0;
    reg request = 0, read_request = 0;
    reg [7:0] register_address = 0;
    reg [4:0] byte_count = 1;
    reg [127:0] write_data = 0;
    wire transaction_done, busy;
    wire [127:0] read_data;
    wire [7:0] error_code;
    wire [2:0] ack_mask;
    wire tick = poll_count == POLL_CYCLES - 1;
    wire mismatch = (config_index == 6 && read_data[15:0] != LP_BREP) ||
        (config_index == 7 && read_data[7:0] != DETECT_INTEGRATOR[7:0]) ||
        (config_index == 8 && read_data[7:0] != 0) ||
        (config_index == 9 && read_data != 0) ||
        (config_index == 10 && read_data != {16{NEGATIVE_THRESHOLD[7:0]}}) ||
        (config_index == 11 && read_data != {16{BURST_LENGTH[7:0]}});
    wire [15:0] signal_word = signals[cursor*16 +: 16];
    wire [15:0] reference_word = references[cursor*16 +: 16];
    wire [16:0] difference = {1'b0,reference_word} - {1'b0,signal_word};
    // Preserve chip hysteresis (NTHR-2), rather than imposing a new press threshold.
    wire allowed = keys_before[cursor] && keys_after[cursor] &&
        reference_word >= signal_word && difference >= RELEASE_LEVEL;
    assign result = {samples, last_error, general_status, keys_after,
                     configured, scl_in, sda_in, 5'b0, chip_id};
    qt2160_i2c_master #(.HALF_CYCLES(HALF_CYCLES), .BUS_FREE_CYCLES(BUS_FREE_CYCLES),
        .TIMEOUT_CYCLES(TIMEOUT_CYCLES)) bus (
        .clk(clk), .scl_in(scl_in), .sda_in(sda_in), .request(request),
        .read_request(read_request), .register_address(register_address),
        .byte_count(byte_count), .write_data(write_data), .scl_low(scl_low),
        .sda_low(sda_low), .busy(busy), .done(transaction_done),
        .read_data(read_data), .error_code(error_code), .ack_mask(ack_mask));

    always @(posedge clk) begin
        request <= 0; sample_done <= 0; scan_done <= 0;
        if (tick) poll_count <= 0;
        else poll_count <= poll_count + 1;
        case (state)
            STARTUP, RETRY: begin
                if (wait_count == (state == STARTUP ? STARTUP_CYCLES : POLL_CYCLES) - 1) begin
                    wait_count <= 0; waiting <= 0; state <= IDENTIFY;
                end else wait_count <= wait_count + 1;
            end
            IDENTIFY: begin
                if (!waiting) begin
                    register_address <= 0; byte_count <= 2; read_request <= 1;
                    request <= 1; waiting <= 1;
                end else if (transaction_done) begin
                    waiting <= 0; chip_id <= read_data[7:0]; sample_done <= 1;
                    if (error_code != 0 || read_data[7:0] != 8'h11) begin
                        last_error <= error_code != 0 ? error_code : 8'h04;
                        configured <= 0; wait_count <= 0; state <= RETRY;
                    end else begin config_index <= 0; last_error <= 0; state <= CONFIGURE; end
                end
            end
            CONFIGURE: begin
                if (!waiting) begin
                    request <= 1; waiting <= 1;
                    read_request <= config_index >= 6 && config_index <= 11;
                    case (config_index)
                        0,6: begin register_address <= 12; byte_count <= 2; write_data <= LP_BREP; end
                        1,7: begin register_address <= 17; byte_count <= 1; write_data <= DETECT_INTEGRATOR; end
                        2,8: begin register_address <= 20; byte_count <= 1; write_data <= 0; end
                        3,9: begin register_address <= 22; byte_count <= 16; write_data <= 0; end
                        4,10: begin register_address <= 38; byte_count <= 16; write_data <= {16{NEGATIVE_THRESHOLD[7:0]}}; end
                        5,11: begin register_address <= 54; byte_count <= 16; write_data <= {16{BURST_LENGTH[7:0]}}; end
                        default: begin register_address <= 10; byte_count <= 1; write_data <= 1; end
                    endcase
                end else if (transaction_done) begin
                    waiting <= 0;
                    if (error_code != 0 || mismatch) begin
                        last_error <= error_code != 0 ? error_code : 8'h06;
                        configured <= 0; wait_count <= 0; state <= RETRY; sample_done <= 1;
                    end else if (config_index == 12) begin
                        wait_count <= 0; first_status <= 1; state <= CAL_WAIT;
                    end else config_index <= config_index + 1;
                end
            end
            CAL_WAIT: begin
                if (wait_count == CALIBRATION_CYCLES - 1) begin wait_count <= 0; state <= STATUS_BEFORE; end
                else wait_count <= wait_count + 1;
            end
            STATUS_BEFORE, SIGNAL_LOW, SIGNAL_HIGH, REFERENCE_LOW, REFERENCE_HIGH, STATUS_AFTER: begin
                if (!waiting) begin
                    read_request <= 1; request <= 1; waiting <= 1;
                    case (state)
                        SIGNAL_LOW: begin register_address <= 100 + {cursor,1'b0}; byte_count <= 2; end
                        REFERENCE_LOW: begin register_address <= 132 + {cursor,1'b0}; byte_count <= 2; end
                        default: begin register_address <= 2; byte_count <= 5; end
                    endcase
                end else if (transaction_done) begin
                    waiting <= 0;
                    if (error_code != 0 || ((state == STATUS_AFTER || (state == STATUS_BEFORE && !first_status)) && read_data[7])) begin
                        last_error <= error_code != 0 ? error_code : 8'h07;
                        configured <= 0; event_valid <= 0; report_keys <= 0;
                        wait_count <= 0; state <= RETRY; sample_done <= 1;
                    end else case (state)
                        STATUS_BEFORE: begin
                            keys_before <= read_data[23:8]; first_status <= 0;
                            cursor <= 0; state <= SIGNAL_LOW;
                        end
                        SIGNAL_LOW: begin signals[cursor*16 +: 16] <= read_data[15:0]; state <= REFERENCE_LOW; end
                        REFERENCE_LOW: begin
                            references[cursor*16 +: 16] <= read_data[15:0];
                            if (cursor == 15) state <= STATUS_AFTER;
                            else begin cursor <= cursor + 1; state <= SIGNAL_LOW; end
                        end
                        default: begin
                            general_status <= read_data[7:0]; keys_after <= read_data[23:8];
                            last_error <= 0; configured <= 1; samples <= samples + 1;
                            sample_done <= 1; report_keys <= 0; cursor <= 0; state <= ANALYZE;
                        end
                    endcase
                end
            end
            ANALYZE: begin
                report_keys[cursor] <= allowed;
                scan_done <= 1;
                scan_result <= {samples, cursor, keys_before[cursor], keys_after[cursor],
                                allowed, configured, general_status, reference_word, signal_word};
                if (cursor == 15) begin cursor <= 0; state <= PUBLISH; end
                else cursor <= cursor + 1;
            end
            PUBLISH: begin
                if (event_valid) begin
                    if (event_ready) begin
                        event_valid <= 0;
                        if (cursor == 15) state <= READY;
                        else cursor <= cursor + 1;
                    end
                end else if (report_keys[cursor]) begin
                    key_signal <= signal_word; key_reference <= reference_word;
                    key_index <= cursor; event_valid <= 1;
                end else if (cursor == 15) state <= READY;
                else cursor <= cursor + 1;
            end
            READY: if (tick) state <= STATUS_BEFORE;
            default: begin
                event_valid <= 0; configured <= 0; last_error <= 8'hff;
                wait_count <= 0; state <= RETRY; sample_done <= 1;
            end
        endcase
    end
endmodule
