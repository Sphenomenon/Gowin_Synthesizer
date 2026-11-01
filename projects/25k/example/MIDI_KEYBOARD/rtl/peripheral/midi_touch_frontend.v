`timescale 1ns / 1ps

// Board mapping: I2C1/U1 = sixteen keys; I2C2/U2 = eight-electrode slider.
// Both devices have address 0x0d on electrically separate buses.
module midi_touch_frontend #(
    parameter integer CLK_HZ = 50_000_000,
    parameter integer STARTUP_CYCLES = CLK_HZ / 10,
    parameter integer CALIBRATION_CYCLES = CLK_HZ / 2,
    parameter integer POLL_CYCLES = CLK_HZ / 50,
    parameter integer MIN_SCAN_CYCLES = CLK_HZ / 1000 * 16,
    parameter integer HALF_CYCLES = CLK_HZ / 200_000,
    parameter integer BUS_FREE_CYCLES = CLK_HZ / 10_000,
    parameter integer TIMEOUT_CYCLES = CLK_HZ / 50,
    parameter integer KEY_NEGATIVE_THRESHOLD = 12,
    parameter integer KEY_DETECT_INTEGRATOR = 7,
    parameter integer KEY_BURST_LENGTH = 4,
    parameter integer SLIDER_NEGATIVE_THRESHOLD = 12,
    parameter integer SLIDER_DETECT_INTEGRATOR = 3,
    parameter integer SLIDER_BURST_LENGTH = 8
) (
    input wire clk, input wire reset, input wire change_n,
    inout wire touch1_scl, inout wire touch1_sda,
    inout wire touch2_scl, inout wire touch2_sda,
    output wire [15:0] key_bitmap, output wire key_update,
    output wire slider_valid, output wire [7:0] slider_position,
    output wire slider_touch, output wire keypad_ready, output wire slider_ready,
    output wire [15:0] errors,
    output wire [7:0] slider_raw_position, output wire [7:0] slider_general_status,
    output wire slider_overrun, output wire [7:0] slider_sample_count,
    output wire [799:0] touch_diagnostics
);
    wire k_scl_low, k_sda_low, s_scl_low, s_sda_low;
    wire [15:0] unused_slider_keys;
    wire [7:0] unused_key_position;
    wire unused_key_touch;
    wire raw_slider_valid, raw_slider_touch;
    wire [7:0] raw_slider_position;
    wire [511:0] key_levels;
    wire [31:0] key_status, key_detect, key_frame_count;
    wire key_overrun;
    localparam integer KEY_RELEASE_THRESHOLD = KEY_NEGATIVE_THRESHOLD > 2 ? KEY_NEGATIVE_THRESHOLD - 2 : 1;
    assign slider_raw_position = raw_slider_position;
    (* ASYNC_REG = "TRUE" *) reg change_meta = 1, change_sync = 1;
    always @(posedge clk) begin
        if (reset) begin change_meta <= 1; change_sync <= 1; end
        else begin change_meta <= change_n; change_sync <= change_meta; end
    end
    assign touch1_scl = k_scl_low ? 1'b0 : 1'bz;
    assign touch1_sda = k_sda_low ? 1'b0 : 1'bz;
    assign touch2_scl = s_scl_low ? 1'b0 : 1'bz;
    assign touch2_sda = s_sda_low ? 1'b0 : 1'bz;
    midi_qt2160_client #(.IS_SLIDER(0), .CLK_HZ(CLK_HZ),
        .NEGATIVE_THRESHOLD(KEY_NEGATIVE_THRESHOLD),
        .DETECT_INTEGRATOR(KEY_DETECT_INTEGRATOR), .BURST_LENGTH(KEY_BURST_LENGTH),
        .STARTUP_CYCLES(STARTUP_CYCLES), .CALIBRATION_CYCLES(CALIBRATION_CYCLES),
        .POLL_CYCLES(POLL_CYCLES), .MIN_SCAN_CYCLES(MIN_SCAN_CYCLES), .HALF_CYCLES(HALF_CYCLES),
        .BUS_FREE_CYCLES(BUS_FREE_CYCLES), .TIMEOUT_CYCLES(TIMEOUT_CYCLES)) keypad (
        .clk(clk), .reset(reset), .change_n(change_sync),
        .scl_in(touch1_scl), .sda_in(touch1_sda), .scl_low(k_scl_low), .sda_low(k_sda_low),
        .keys(key_bitmap), .position(unused_key_position), .touched(unused_key_touch),
        .update(key_update), .ready(keypad_ready), .error_code(errors[7:0]),
        .overrun_seen(key_overrun), .diagnostic_levels(key_levels),
        .diagnostic_status(key_status), .diagnostic_detect(key_detect), .frame_count(key_frame_count));
    midi_qt2160_client #(.IS_SLIDER(1), .CLK_HZ(CLK_HZ),
        .NEGATIVE_THRESHOLD(SLIDER_NEGATIVE_THRESHOLD),
        .DETECT_INTEGRATOR(SLIDER_DETECT_INTEGRATOR), .BURST_LENGTH(SLIDER_BURST_LENGTH),
        .STARTUP_CYCLES(STARTUP_CYCLES), .CALIBRATION_CYCLES(CALIBRATION_CYCLES),
        .POLL_CYCLES(POLL_CYCLES), .MIN_SCAN_CYCLES(MIN_SCAN_CYCLES), .HALF_CYCLES(HALF_CYCLES),
        .BUS_FREE_CYCLES(BUS_FREE_CYCLES), .TIMEOUT_CYCLES(TIMEOUT_CYCLES)) slider (
        .clk(clk), .reset(reset), .change_n(change_sync),
        .scl_in(touch2_scl), .sda_in(touch2_sda), .scl_low(s_scl_low), .sda_low(s_sda_low),
        .keys(unused_slider_keys), .position(raw_slider_position), .touched(raw_slider_touch),
        .update(raw_slider_valid), .ready(slider_ready), .error_code(errors[15:8]),
        .general_status(slider_general_status), .overrun_seen(slider_overrun),
        .sample_count(slider_sample_count));
    midi_slider_filter slider_filter (
        .clk(clk), .reset(reset), .sample_valid(raw_slider_valid),
        .raw_touch(raw_slider_touch), .raw_position(raw_slider_position),
        .valid(slider_valid), .touched(slider_touch), .position(slider_position));
    assign touch_diagnostics[31:0] = key_status;
    assign touch_diagnostics[63:32] = key_detect;
    assign touch_diagnostics[95:64] = key_levels[9*32+:32];
    assign touch_diagnostics[127:96] = key_levels[15*32+:32];
    assign touch_diagnostics[159:128] = {slider_sample_count,slider_general_status,slider_position,slider_raw_position};
    assign touch_diagnostics[191:160] = {8'd0,errors,1'b0,key_overrun,slider_overrun,2'd0,slider_touch,slider_ready,keypad_ready};
    assign touch_diagnostics[223:192] = key_frame_count;
    assign touch_diagnostics[255:224] = 32'h54430102;
    assign touch_diagnostics[767:256] = key_levels;
    assign touch_diagnostics[799:768] = {8'd0,SLIDER_NEGATIVE_THRESHOLD[7:0],KEY_RELEASE_THRESHOLD[7:0],KEY_NEGATIVE_THRESHOLD[7:0]};
endmodule

// Configuration and filtering are derived from the supplied reference readers.
// The original files are preserved in vendor/qt2160_reference.
module midi_qt2160_client #(
    parameter integer IS_SLIDER = 0,
    parameter integer CLK_HZ = 50_000_000,
    parameter integer STARTUP_CYCLES = CLK_HZ / 10,
    parameter integer CALIBRATION_CYCLES = CLK_HZ / 2,
    parameter integer POLL_CYCLES = CLK_HZ / 50,
    parameter integer MIN_SCAN_CYCLES = CLK_HZ / 1000 * 16,
    parameter integer HALF_CYCLES = CLK_HZ / 200_000,
    parameter integer BUS_FREE_CYCLES = CLK_HZ / 10_000,
    parameter integer TIMEOUT_CYCLES = CLK_HZ / 50,
    parameter integer NEGATIVE_THRESHOLD = 12,
    parameter integer BURST_LENGTH = 4,
    parameter integer DETECT_INTEGRATOR = 7
) (
    input wire clk, input wire reset, input wire change_n,
    input wire scl_in, input wire sda_in, output wire scl_low, output wire sda_low,
    output reg [15:0] keys = 0, output reg [7:0] position = 0,
    output reg touched = 0, output reg update = 0, output reg ready = 0,
    output reg [7:0] error_code = 0,
    output reg [7:0] general_status = 0, output reg overrun_seen = 0,
    output reg [7:0] sample_count = 0,
    output reg [511:0] diagnostic_levels = 0,
    output reg [31:0] diagnostic_status = 0, diagnostic_detect = 0, frame_count = 0
);
    localparam [3:0] STARTUP=0, IDENTIFY=1, CONFIGURE=2, CAL_WAIT=3,
        STATUS_BEFORE=4, SIGNAL_A=5, SIGNAL_B=6, REFERENCE_A=7,
        REFERENCE_B=8, STATUS_AFTER=9, IDLE=10, RETRY=11, RESET_BASELINE=12, FILTER_KEYS=13;
    localparam integer POLL_LIMIT = POLL_CYCLES > MIN_SCAN_CYCLES ? POLL_CYCLES : MIN_SCAN_CYCLES;
    localparam [127:0] SLIDER_CONFIG = 128'h00000000000001010101010101010028;
    localparam [127:0] SLIDER_BURST = {64'b0, {8{BURST_LENGTH[7:0]}}};
    localparam [127:0] SLIDER_THRESHOLD = {64'b0, {8{NEGATIVE_THRESHOLD[7:0]}}};
    reg [3:0] state = STARTUP, config_index = 0;
    reg waiting = 0;
    function integer counter_width;
        input integer maximum;
        integer remaining;
        begin
            remaining=maximum;counter_width=0;
            while(remaining>0)begin counter_width=counter_width+1;remaining=remaining>>1;end
            if(counter_width<1)counter_width=1;
        end
    endfunction
    localparam integer WAIT_LIMIT = STARTUP_CYCLES > CALIBRATION_CYCLES ?
        (STARTUP_CYCLES > POLL_CYCLES ? STARTUP_CYCLES : POLL_CYCLES) :
        (CALIBRATION_CYCLES > POLL_CYCLES ? CALIBRATION_CYCLES : POLL_CYCLES);
    reg [counter_width(WAIT_LIMIT)-1:0] wait_count = 0;
    reg [counter_width(POLL_LIMIT)-1:0] poll_count = 0;
    reg [15:0] keys_before = 0;
    reg [255:0] signals = 0, references = 0;
    reg request = 0, read_request = 0;
    reg [7:0] register_address = 0;
    reg [6:0] byte_count = 1;
    reg [127:0] write_data = 0;
    wire transaction_done, busy;
    wire [127:0] read_data;
    wire [7:0] bus_error;
    wire [2:0] ack_mask;
    reg [15:0] filtered_keys=0,keys_after=0;
    reg [3:0] filter_index=0;
    wire filtered_key;
    wire [15:0] completed_keys={filtered_key,filtered_keys[14:0]};
    integer k;
    wire mismatch = IS_SLIDER ?
        ((config_index == 5 && read_data[15:0] != 16'h0101) ||
         (config_index == 6 && read_data[7:0] != DETECT_INTEGRATOR[7:0]) ||
         (config_index == 7 && read_data[79:0] != SLIDER_CONFIG[79:0]) ||
         (config_index == 8 && read_data[63:0] != SLIDER_THRESHOLD[63:0]) ||
         (config_index == 9 && read_data != SLIDER_BURST)) :
        ((config_index == 6 && read_data[15:0] != 16'h0101) ||
         (config_index == 7 && read_data[7:0] != DETECT_INTEGRATOR[7:0]) ||
         (config_index == 8 && read_data[7:0] != 0) ||
         (config_index == 9 && read_data != 0) ||
         (config_index == 10 && read_data != {16{NEGATIVE_THRESHOLD[7:0]}}) ||
         (config_index == 11 && read_data != {16{BURST_LENGTH[7:0]}}));
    midi_touch_key_filter #(.NEGATIVE_THRESHOLD(NEGATIVE_THRESHOLD),.CHANNELS(1)) key_filter(
        .before_keys(keys_before[filter_index]),.after_keys(keys_after[filter_index]),.previous_keys(keys[filter_index]),
        .signals(signals[filter_index*16+:16]),.references(references[filter_index*16+:16]),.filtered_keys(filtered_key));
    midi_i2c_register_master #(.DEVICE_ADDRESS(7'h0d), .HALF_CYCLES(HALF_CYCLES),
        .BUS_FREE_CYCLES(BUS_FREE_CYCLES), .TIMEOUT_CYCLES(TIMEOUT_CYCLES)) bus (
        .clk(clk), .reset(reset), .scl_in(scl_in), .sda_in(sda_in), .request(request),
        .read_request(read_request), .register_address(register_address), .byte_count(byte_count),
        .write_data(write_data), .scl_low(scl_low), .sda_low(sda_low), .busy(busy),
        .done(transaction_done), .read_data(read_data), .error_code(bus_error), .ack_mask(ack_mask));
    always @(posedge clk) begin
        if (reset) begin
            state <= STARTUP; config_index <= 0; waiting <= 0;
            wait_count <= 0; poll_count <= 0; keys_before <= 0; signals <= 0; references <= 0;
            request <= 0; read_request <= 0; register_address <= 0; byte_count <= 1; write_data <= 0;
            keys <= 0; position <= 0; touched <= 0; update <= 0; ready <= 0; error_code <= 0;
            general_status <= 0; overrun_seen <= 0; sample_count <= 0;
            diagnostic_levels <= 0; diagnostic_status <= 0; diagnostic_detect <= 0; frame_count <= 0;
            filtered_keys <= 0; keys_after <= 0; filter_index <= 0;
        end else begin
            request <= 0; update <= 0;
            if (poll_count < POLL_LIMIT) poll_count <= poll_count + 1;
            // Keep the chip's actual status even when RESET invalidates the
            // snapshot. Bus errors retain the last successfully read status.
            if (waiting && transaction_done && bus_error == 0 &&
                (state == RESET_BASELINE || state == STATUS_BEFORE || state == STATUS_AFTER)) begin
                general_status <= read_data[7:0];
                if (read_data[6]) overrun_seen <= 1;
            end
            // A failed transaction invalidates the entire snapshot. Publish a
            // release so downstream MIDI never holds a note across a bus fault.
            if (waiting && transaction_done &&
                (bus_error != 0 || (state == IDENTIFY && read_data[7:0] != 8'h11) ||
                 (state == CONFIGURE && mismatch) ||
                 ((state == STATUS_BEFORE || state == STATUS_AFTER) && read_data[7]))) begin
                error_code <= bus_error != 0 ? bus_error :
                    (state == IDENTIFY ? 8'h04 : (state == CONFIGURE ? 8'h06 : 8'h07));
                ready <= 0; keys <= 0; touched <= 0; update <= 1;
                waiting <= 0; wait_count <= 0; state <= RETRY;
            end else case (state)
                STARTUP, RETRY: begin
                    if (wait_count >= (state == STARTUP ? STARTUP_CYCLES : POLL_CYCLES) - 1) begin
                        wait_count <= 0; waiting <= 0; state <= IDENTIFY;
                    end else wait_count <= wait_count + 1;
                end
                IDENTIFY: begin
                    if (!waiting) begin
                        register_address <= 0; byte_count <= 2; read_request <= 1;
                        request <= 1; waiting <= 1;
                    end else if (transaction_done) begin
                        waiting <= 0; config_index <= 0; state <= RESET_BASELINE;
                    end
                end
                RESET_BASELINE: begin
                    // RESET clears on a status read. Consume the old power-on
                    // flag before configuration so any later RESET is a fault.
                    if (!waiting) begin
                        register_address <= 2; byte_count <= 5; read_request <= 1;
                        request <= 1; waiting <= 1;
                    end else if (transaction_done) begin
                        waiting <= 0; state <= CONFIGURE;
                    end
                end
                CONFIGURE: begin
                    if (!waiting) begin
                        request <= 1; waiting <= 1;
                        if (IS_SLIDER) begin
                            read_request <= config_index >= 5 && config_index <= 9;
                            case (config_index)
                                0,5: begin register_address <= 12; byte_count <= 2; write_data <= 16'h0101; end
                                1,6: begin register_address <= 17; byte_count <= 1; write_data <= DETECT_INTEGRATOR; end
                                2,7: begin register_address <= 20; byte_count <= 10; write_data <= SLIDER_CONFIG; end
                                3,8: begin register_address <= 38; byte_count <= 8; write_data <= SLIDER_THRESHOLD; end
                                4,9: begin register_address <= 54; byte_count <= 16; write_data <= SLIDER_BURST; end
                                default: begin register_address <= 10; byte_count <= 1; write_data <= 1; end
                            endcase
                        end else begin
                            read_request <= config_index >= 6 && config_index <= 11;
                            case (config_index)
                                0,6: begin register_address <= 12; byte_count <= 2; write_data <= 16'h0101; end
                                1,7: begin register_address <= 17; byte_count <= 1; write_data <= DETECT_INTEGRATOR; end
                                2,8: begin register_address <= 20; byte_count <= 1; write_data <= 0; end
                                3,9: begin register_address <= 22; byte_count <= 16; write_data <= 0; end
                                4,10: begin register_address <= 38; byte_count <= 16; write_data <= {16{NEGATIVE_THRESHOLD[7:0]}}; end
                                5,11: begin register_address <= 54; byte_count <= 16; write_data <= {16{BURST_LENGTH[7:0]}}; end
                                default: begin register_address <= 10; byte_count <= 1; write_data <= 1; end
                            endcase
                        end
                    end else if (transaction_done) begin
                        waiting <= 0;
                        if (config_index == (IS_SLIDER ? 10 : 12)) begin
                            wait_count <= 0; state <= CAL_WAIT;
                        end else config_index <= config_index + 1;
                    end
                end
                CAL_WAIT: begin
                    if (wait_count >= CALIBRATION_CYCLES - 1) begin
                        wait_count <= 0; state <= STATUS_BEFORE;
                    end else wait_count <= wait_count + 1;
                end
                STATUS_BEFORE, SIGNAL_A, SIGNAL_B, REFERENCE_A, REFERENCE_B, STATUS_AFTER: begin
                    if (!waiting) begin
                        request <= 1; read_request <= 1; waiting <= 1;
                        // Start-to-start scheduling prevents a shared, held-low
                        // CHANGE from rereading the same matrix scan repeatedly.
                        if (state == STATUS_BEFORE) poll_count <= 0;
                        case (state)
                            SIGNAL_A: begin register_address <= 100; byte_count <= 16; end
                            SIGNAL_B: begin register_address <= 116; byte_count <= 16; end
                            REFERENCE_A: begin register_address <= 132; byte_count <= 16; end
                            REFERENCE_B: begin register_address <= 148; byte_count <= 16; end
                            default: begin register_address <= 2; byte_count <= 5; end
                        endcase
                    end else if (transaction_done) begin
                        waiting <= 0;
                        case (state)
                            STATUS_BEFORE: begin
                                if (IS_SLIDER) begin
                                    position <= read_data[31:24]; touched <= read_data[0];
                                    ready <= 1; update <= 1; error_code <= 0;
                                    sample_count <= sample_count + 1'b1; state <= IDLE;
                                end else begin keys_before <= read_data[23:8]; state <= SIGNAL_A; end
                            end
                            SIGNAL_A: begin signals[127:0] <= read_data; state <= SIGNAL_B; end
                            SIGNAL_B: begin signals[255:128] <= read_data; state <= REFERENCE_A; end
                            REFERENCE_A: begin references[127:0] <= read_data; state <= REFERENCE_B; end
                            REFERENCE_B: begin references[255:128] <= read_data; state <= STATUS_AFTER; end
                            default: begin
                                keys_after <= read_data[23:8];filter_index <= 0;filtered_keys <= 0;state <= FILTER_KEYS;
                            end
                        endcase
                    end
                end
                FILTER_KEYS: begin
                    filtered_keys[filter_index] <= filtered_key;
                    if(filter_index==15)begin
                        keys <= completed_keys;ready <= 1;update <= 1;error_code <= 0;
                        sample_count <= sample_count+1'b1;state <= IDLE;
                        diagnostic_status <= {general_status,sample_count+8'd1,completed_keys};
                        diagnostic_detect <= {keys_after,keys_before};
                        for(k=0;k<16;k=k+1)
                            diagnostic_levels[k*32+:32] <= {references[k*16+:16],signals[k*16+:16]};
                        frame_count <= frame_count+1'b1;
                    end else filter_index <= filter_index+1'b1;
                end
                // QT2160 section 5.5: polling faster than one matrix scan
                // provides no new information and can slow acquisition.
                IDLE: if (poll_count >= MIN_SCAN_CYCLES - 1 &&
                          (!change_n || poll_count >= POLL_CYCLES - 1)) state <= STATUS_BEFORE;
                default: begin
                    ready <= 0; keys <= 0; touched <= 0; update <= 1;
                    error_code <= 8'hff; waiting <= 0; wait_count <= 0; state <= RETRY;
                end
            endcase
        end
    end
endmodule
