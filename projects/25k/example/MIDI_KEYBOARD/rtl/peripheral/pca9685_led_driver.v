`timescale 1ns / 1ps

// Sixteen LED anodes sourced by the PCA9685; LED cathodes are grounded.
// MODE2 OUTDRV=1, INVRT=0, OCH=0: all 16 channels latch together at STOP.
module pca9685_led_driver #(
    parameter integer CLK_HZ = 50_000_000,
    parameter integer HALF_CYCLES = CLK_HZ / 200_000,
    parameter integer BUS_FREE_CYCLES = CLK_HZ / 10_000,
    parameter integer TIMEOUT_CYCLES = CLK_HZ / 50,
    parameter integer STARTUP_CYCLES = CLK_HZ / 100,
    parameter integer OSC_SETTLE_CYCLES = CLK_HZ / 2000,
    parameter integer RETRY_CYCLES = CLK_HZ / 100,
    parameter integer REFRESH_CYCLES = CLK_HZ / 20,
    parameter integer PWM_HZ = 200,
    parameter [7:0] IDLE_BRIGHTNESS = 8'd0
) (
    input wire clk, input wire reset, inout wire scl, inout wire sda,
    input wire [15:0] led_bitmap, input wire [7:0] brightness,
    output reg ready = 0, output reg [15:0] errors = 0
);
    localparam integer PRESCALE_CALC = (25_000_000 + (4096*PWM_HZ)/2)/(4096*PWM_HZ) - 1;
    localparam [7:0] PRESCALE = PRESCALE_CALC < 3 ? 3 : (PRESCALE_CALC > 255 ? 255 : PRESCALE_CALC);
    localparam [2:0] STARTUP=0, CONFIGURE=1, OSC_WAIT=2, SNAPSHOT=3, UPDATE=4, IDLE=5, RETRY=6;
    reg [2:0] state = STARTUP, config_index = 0;
    reg waiting = 0, request = 0;
    reg [31:0] wait_count = 0, refresh_count = 0;
    reg [15:0] frame_leds = 0;
    reg [7:0] frame_brightness = 0, register_address = 0;
    reg [6:0] byte_count = 1;
    reg [511:0] write_data = 0;
    reg [511:0] pwm_payload;
    reg [7:0] channel_level;
    reg [11:0] duty;
    integer channel;
    wire scl_low, sda_low, done, busy;
    wire [7:0] bus_error;
    wire [2:0] ack_mask;
    wire [511:0] unused_read;
    assign scl = scl_low ? 1'b0 : 1'bz;
    assign sda = sda_low ? 1'b0 : 1'bz;
    always @* begin
        pwm_payload = 0;
        channel_level = 0; duty = 0;
        for (channel = 0; channel < 16; channel = channel + 1) begin
            channel_level = frame_leds[channel] ? frame_brightness : IDLE_BRIGHTNESS;
            duty = {channel_level,channel_level[7:4]};
            // ON=0; full-on/full-off flags avoid a narrow spurious PWM pulse.
            pwm_payload[channel*32 +: 32] = channel_level == 0 ? 32'h10000000 :
                (channel_level == 255 ? 32'h00001000 : {4'b0,duty,16'b0});
        end
    end
    midi_i2c_register_master #(.DEVICE_ADDRESS(7'h40), .MAX_BYTES(64),
        .HALF_CYCLES(HALF_CYCLES), .BUS_FREE_CYCLES(BUS_FREE_CYCLES),
        .TIMEOUT_CYCLES(TIMEOUT_CYCLES)) bus (
        .clk(clk), .reset(reset), .scl_in(scl), .sda_in(sda), .request(request), .read_request(1'b0),
        .register_address(register_address), .byte_count(byte_count), .write_data(write_data),
        .scl_low(scl_low), .sda_low(sda_low), .busy(busy), .done(done),
        .read_data(unused_read), .error_code(bus_error), .ack_mask(ack_mask));
    always @(posedge clk) begin
        if (reset) begin
            ready <= 0; errors <= 0; state <= STARTUP; config_index <= 0;
            waiting <= 0; request <= 0; wait_count <= 0; refresh_count <= 0;
            frame_leds <= 0; frame_brightness <= 0; register_address <= 0;
            byte_count <= 1; write_data <= 0;
        end else begin
            request <= 0;
            if (refresh_count < REFRESH_CYCLES) refresh_count <= refresh_count + 1;
            if (waiting && done && bus_error != 0) begin
                ready <= 0; errors <= {8'b0,bus_error}; waiting <= 0;
                wait_count <= 0; config_index <= 0; state <= RETRY;
            end else case (state)
                STARTUP, RETRY: begin
                    if (wait_count >= (state == STARTUP ? STARTUP_CYCLES : RETRY_CYCLES) - 1) begin
                        wait_count <= 0; config_index <= 0; state <= CONFIGURE;
                    end else wait_count <= wait_count + 1;
                end
                CONFIGURE: begin
                    if (!waiting) begin
                        request <= 1; waiting <= 1; byte_count <= 1;
                        case (config_index)
                            0: begin register_address <= 8'h00; write_data <= 8'h30; end // AI + SLEEP
                            1: begin register_address <= 8'h01; write_data <= 8'h04; end // push-pull, STOP latch
                            2: begin register_address <= 8'hfe; write_data <= PRESCALE; end
                            3: begin register_address <= 8'h00; write_data <= 8'h20; end // internal osc wake
                            default: begin register_address <= 8'h00; write_data <= 8'ha0; end // RESTART + AI
                        endcase
                    end else if (done) begin
                        waiting <= 0;
                        if (config_index == 3) begin wait_count <= 0; state <= OSC_WAIT; end
                        else if (config_index == 4) state <= SNAPSHOT;
                        else config_index <= config_index + 1;
                    end
                end
                OSC_WAIT: begin
                    if (wait_count >= OSC_SETTLE_CYCLES - 1) begin
                        config_index <= 4; state <= CONFIGURE; wait_count <= 0;
                    end else wait_count <= wait_count + 1;
                end
                SNAPSHOT: begin
                    frame_leds <= led_bitmap; frame_brightness <= brightness; state <= UPDATE;
                end
                UPDATE: begin
                    if (!waiting) begin
                        register_address <= 8'h06; byte_count <= 64;
                        write_data <= pwm_payload; request <= 1; waiting <= 1;
                    end else if (done) begin
                        waiting <= 0; ready <= 1; errors <= 0; refresh_count <= 0; state <= IDLE;
                    end
                end
                IDLE: if (frame_leds != led_bitmap || frame_brightness != brightness ||
                    refresh_count >= REFRESH_CYCLES - 1) state <= SNAPSHOT;
                default: begin ready <= 0; errors <= 16'h00ff; waiting <= 0; wait_count <= 0; state <= RETRY; end
            endcase
        end
    end
endmodule
