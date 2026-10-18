`timescale 1ns / 1ps

module qt2160_slider_reader #(
    parameter integer CLK_HZ = 50_000_000,
    parameter integer STARTUP_CYCLES = CLK_HZ / 10,
    parameter integer REPORT_CYCLES = CLK_HZ / 5,
    parameter integer CALIBRATION_CYCLES = CLK_HZ / 5,
    parameter integer HALF_CYCLES = 250,
    parameter integer BUS_FREE_CYCLES = 5000,
    parameter integer TIMEOUT_CYCLES = 1_000_000
) (
    input wire clk, input wire scl_in, input wire sda_in, input wire change_n,
    output wire scl_low, output wire sda_low,
    output reg report = 0,
    output wire [7:0] slider_value, output wire touched, output wire sample_valid,
    output reg sample_done = 0, output wire [63:0] slider_result,
    output reg id_done = 0, output reg [63:0] id_result = 0
);
    localparam [4:0] STARTUP=0, IDENTIFY=1, CONFIGURE=2, CAL_WAIT=3,
        CLEAR_STATUS=4, READY=5, POLL=6, RETRY=7;
    // Register 20: hysteresis 2 + 8 keys; 21: 8-bit position;
    // registers 22..29: all eight Y0 keys in AKS group 1.
    localparam [127:0] SLIDER_CONFIG = 128'h00000000000001010101010101010028;
    // Y0 keys: burst length 8 (32 pulses); unused Y1 keys disabled.
    localparam [127:0] BURST_CONFIG = 128'h00000000000000000808080808080808;
    localparam [127:0] THRESHOLD_CONFIG = 128'h00000000000000000a0a0a0a0a0a0a0a;
    reg [4:0] state = STARTUP;
    reg [3:0] config_index = 0;
    reg waiting = 0, configured = 0, valid_sample = 0;
    reg [31:0] wait_count = 0, report_count = 0;
    reg [15:0] samples = 0, id_attempts = 0;
    reg [7:0] general_status = 0, key_status0 = 0, key_status1 = 0, position = 0, last_error = 0;
    (* ASYNC_REG = "TRUE" *) reg change_meta = 1, change_sync = 1;
    reg request = 0, read_request = 0;
    reg [7:0] register_address = 0;
    reg [4:0] byte_count = 1;
    reg [127:0] write_data = 0;
    wire busy, transaction_done;
    wire [127:0] read_data;
    wire [7:0] error_code;
    wire [2:0] ack_mask;
    wire tick = report_count == REPORT_CYCLES - 1;
    wire config_mismatch =
        (config_index == 4 && read_data[7:0] != 8'h01) ||
        (config_index == 5 && read_data[79:0] != SLIDER_CONFIG[79:0]) ||
        (config_index == 6 && read_data[63:0] != THRESHOLD_CONFIG[63:0]) ||
        (config_index == 7 && read_data != BURST_CONFIG);
    assign slider_value = position;
    assign touched = general_status[0];
    assign sample_valid = configured && valid_sample;
    assign slider_result = {samples, last_error, general_status, key_status0, key_status1,
                            position, configured, valid_sample, 4'b0, change_sync, touched};
    qt2160_i2c_master #(.HALF_CYCLES(HALF_CYCLES), .BUS_FREE_CYCLES(BUS_FREE_CYCLES),
        .TIMEOUT_CYCLES(TIMEOUT_CYCLES)) bus (.clk(clk), .scl_in(scl_in), .sda_in(sda_in),
        .request(request), .read_request(read_request), .register_address(register_address),
        .byte_count(byte_count), .write_data(write_data), .scl_low(scl_low), .sda_low(sda_low),
        .busy(busy), .done(transaction_done), .read_data(read_data), .error_code(error_code), .ack_mask(ack_mask));
    always @(posedge clk) begin
        change_meta <= change_n; change_sync <= change_meta;
        request <= 0; report <= 0; sample_done <= 0; id_done <= 0;
        if (tick) begin report_count <= 0; report <= 1; end
        else report_count <= report_count + 1;
        case (state)
            STARTUP, RETRY: begin
                if (wait_count == (state == STARTUP ? STARTUP_CYCLES : REPORT_CYCLES) - 1) begin
                    wait_count <= 0; waiting <= 0; state <= IDENTIFY;
                end else wait_count <= wait_count + 1;
            end
            IDENTIFY: begin
                if (!waiting) begin
                    read_request <= 1; register_address <= 0; byte_count <= 2;
                    request <= 1; waiting <= 1;
                end else if (transaction_done) begin
                    id_attempts <= id_attempts + 1; id_done <= 1; waiting <= 0;
                    id_result <= {id_attempts + 16'd1, 8'h0d,
                        error_code != 0 ? error_code : (read_data[7:0] == 8'h11 ? 8'h00 : 8'h04),
                        5'b0, ack_mask, read_data[15:8], read_data[7:0],
                        4'b0, (error_code == 0 && read_data[7:0] == 8'h11), change_sync, scl_in, sda_in};
                    if (error_code == 0 && read_data[7:0] == 8'h11) begin
                        config_index <= 0; state <= CONFIGURE; last_error <= 0;
                    end else begin
                        last_error <= error_code != 0 ? error_code : 8'h04;
                        wait_count <= 0; state <= RETRY;
                    end
                end
            end
            CONFIGURE: begin
                if (!waiting) begin
                    request <= 1; waiting <= 1; read_request <= config_index >= 4 && config_index <= 7;
                    case (config_index)
                        0,4: begin register_address <= 12; byte_count <= 1; write_data <= 1; end
                        1,5: begin register_address <= 20; byte_count <= 10; write_data <= SLIDER_CONFIG; end
                        2,6: begin register_address <= 38; byte_count <= 8; write_data <= THRESHOLD_CONFIG; end
                        3,7: begin register_address <= 54; byte_count <= 16; write_data <= BURST_CONFIG; end
                        default: begin register_address <= 10; byte_count <= 1; write_data <= 1; end
                    endcase
                end else if (transaction_done) begin
                    waiting <= 0;
                    if (error_code != 0 || config_mismatch) begin
                        last_error <= error_code != 0 ? error_code : 8'h06;
                        configured <= 0; valid_sample <= 0; wait_count <= 0; state <= RETRY;
                    end else if (config_index == 8) begin wait_count <= 0; state <= CAL_WAIT; end
                    else config_index <= config_index + 1;
                end
            end
            CAL_WAIT: begin
                if (wait_count == CALIBRATION_CYCLES - 1) begin
                    wait_count <= 0; state <= CLEAR_STATUS;
                end else wait_count <= wait_count + 1;
            end
            CLEAR_STATUS, POLL: begin
                if (!waiting) begin
                    read_request <= 1; register_address <= 2; byte_count <= 5;
                    request <= 1; waiting <= 1;
                end else if (transaction_done) begin
                    waiting <= 0; samples <= samples + 1; sample_done <= 1;
                    if (error_code != 0 || (state == POLL && read_data[7])) begin
                        last_error <= error_code != 0 ? error_code : 8'h07;
                        configured <= 0; valid_sample <= 0; wait_count <= 0; state <= RETRY;
                    end else begin
                        general_status <= read_data[7:0]; key_status0 <= read_data[15:8];
                        key_status1 <= read_data[23:16]; position <= read_data[31:24];
                        last_error <= 0; configured <= 1; valid_sample <= 1; state <= READY;
                    end
                end
            end
            // Start each poll 20 ms before the fixed 200 ms UART report tick.
            READY: if (report_count == REPORT_CYCLES * 9 / 10 - 1) begin waiting <= 0; state <= POLL; end
            default: begin configured <= 0; valid_sample <= 0; last_error <= 8'hff; state <= RETRY; wait_count <= 0; end
        endcase
    end
endmodule
