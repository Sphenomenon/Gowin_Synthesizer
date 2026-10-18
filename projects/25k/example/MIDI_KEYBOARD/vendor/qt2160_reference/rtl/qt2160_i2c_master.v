`timescale 1ns / 1ps

// Register transactions, up to 16 bytes, first byte in bits 7:0.
// All outputs are open-drain controls. QT2160 requires STOP before read START.
module qt2160_i2c_master #(
    parameter integer HALF_CYCLES = 250,
    parameter integer BUS_FREE_CYCLES = 5000,
    parameter integer TIMEOUT_CYCLES = 1_000_000
) (
    input wire clk, input wire scl_in, input wire sda_in,
    input wire request, input wire read_request,
    input wire [7:0] register_address,
    input wire [4:0] byte_count,
    input wire [127:0] write_data,
    output reg scl_low = 0, output reg sda_low = 0,
    output reg busy = 0, output reg done = 0,
    output reg [127:0] read_data = 0,
    output reg [7:0] error_code = 0,
    output reg [2:0] ack_mask = 0
);
    localparam [4:0] IDLE=0, START_FREE=1, START_HOLD=2,
        TX_LOW=3, TX_RISE=4, TX_HIGH=5, ACK_LOW=6, ACK_RISE=7, ACK_HIGH=8,
        STOP_LOW=9, STOP_RISE=10, STOP_HIGH=11, STOP_FREE=12,
        RX_LOW=13, RX_RISE=14, RX_HIGH=15, MACK_LOW=16, MACK_RISE=17,
        MACK_HIGH=18, FINISH=19;
    reg [4:0] state = IDLE;
    reg [2:0] phase = 0, bit_index = 7;
    reg [4:0] count = 1, byte_index = 0;
    reg reading = 0, read_stage = 0, stop_then_read = 0;
    reg [7:0] pointer = 0, tx_byte = 0, rx_byte = 0;
    reg [127:0] payload = 0;
    reg [31:0] timer = 0, timeout_count = 0;
    (* ASYNC_REG = "TRUE" *) reg scl_meta = 1, scl_sync = 1;
    (* ASYNC_REG = "TRUE" *) reg sda_meta = 1, sda_sync = 1;
    wire half_done = timer == HALF_CYCLES - 1;
    wire [31:0] timer_limit = state == START_FREE ? BUS_FREE_CYCLES : HALF_CYCLES;
    wire stretching = state == TX_RISE || state == ACK_RISE || state == RX_RISE ||
                      state == MACK_RISE || state == STOP_RISE;
    always @(posedge clk) begin
        scl_meta <= scl_in; scl_sync <= scl_meta;
        sda_meta <= sda_in; sda_sync <= sda_meta;
        done <= 0;
        if (timer < timer_limit - 1) timer <= timer + 1;
        if (stretching && !scl_sync) timeout_count <= timeout_count + 1;
        else timeout_count <= 0;
        if (stretching && !scl_sync && timeout_count >= TIMEOUT_CYCLES - 1) begin
            scl_low <= 0; sda_low <= 0;
            error_code <= 8'h80; state <= FINISH; timer <= 0;
        end else case (state)
            IDLE: begin
                scl_low <= 0; sda_low <= 0;
                if (request) begin
                    busy <= 1; error_code <= 0; ack_mask <= 0; read_data <= 0;
                    reading <= read_request; pointer <= register_address;
                    payload <= write_data; count <= byte_count;
                    byte_index <= 0; read_stage <= 0; stop_then_read <= 0;
                    timer <= 0; timeout_count <= 0;
                    if (byte_count == 0 || byte_count > 16) begin
                        error_code <= 8'hff; state <= FINISH;
                    end else state <= START_FREE;
                end
            end
            START_FREE: begin
                scl_low <= 0; sda_low <= 0;
                if (!scl_sync || !sda_sync) begin
                    timer <= 0; timeout_count <= timeout_count + 1;
                    if (timeout_count >= TIMEOUT_CYCLES - 1) begin
                        error_code <= 8'h40; state <= FINISH;
                    end
                end else if (timer == BUS_FREE_CYCLES - 1) begin
                    sda_low <= 1; state <= START_HOLD; timer <= 0;
                end
            end
            START_HOLD: if (half_done) begin
                scl_low <= 1; sda_low <= 1;
                tx_byte <= read_stage ? 8'h1b : 8'h1a;
                phase <= read_stage ? 3 : 0;
                bit_index <= 7; timer <= 0; state <= TX_LOW;
            end
            TX_LOW: if (half_done) begin
                scl_low <= 0; state <= TX_RISE; timer <= 0;
            end
            TX_RISE: begin timer <= 0; if (scl_sync) state <= TX_HIGH; end
            TX_HIGH: if (half_done) begin
                scl_low <= 1; timer <= 0;
                if (bit_index == 0) begin sda_low <= 0; state <= ACK_LOW; end
                else begin
                    bit_index <= bit_index - 1;
                    sda_low <= !tx_byte[bit_index - 1]; state <= TX_LOW;
                end
            end
            ACK_LOW: if (half_done) begin
                scl_low <= 0; state <= ACK_RISE; timer <= 0;
            end
            ACK_RISE: begin timer <= 0; if (scl_sync) state <= ACK_HIGH; end
            ACK_HIGH: if (half_done) begin
                scl_low <= 1; timer <= 0; bit_index <= 7;
                if (sda_sync) begin
                    error_code <= phase == 0 ? 1 : (phase == 1 ? 2 : (phase == 3 ? 3 : 5));
                    stop_then_read <= 0; sda_low <= 1; state <= STOP_LOW;
                end else case (phase)
                    0: begin
                        ack_mask[0] <= 1; tx_byte <= pointer; sda_low <= !pointer[7];
                        phase <= 1; state <= TX_LOW;
                    end
                    1: begin
                        ack_mask[1] <= 1;
                        if (reading) begin stop_then_read <= 1; sda_low <= 1; state <= STOP_LOW; end
                        else begin
                            tx_byte <= payload[7:0]; sda_low <= !payload[7];
                            phase <= 2; state <= TX_LOW;
                        end
                    end
                    2: begin
                        ack_mask[2] <= 1;
                        if (byte_index + 1 == count) begin sda_low <= 1; state <= STOP_LOW; end
                        else begin
                            byte_index <= byte_index + 1;
                            tx_byte <= payload[(byte_index + 1)*8 +: 8];
                            sda_low <= !payload[(byte_index + 1)*8 + 7]; state <= TX_LOW;
                        end
                    end
                    3: begin
                        ack_mask[2] <= 1; byte_index <= 0; rx_byte <= 0;
                        sda_low <= 0; state <= RX_LOW;
                    end
                endcase
            end
            STOP_LOW: if (half_done) begin
                scl_low <= 0; state <= STOP_RISE; timer <= 0;
            end
            STOP_RISE: begin timer <= 0; if (scl_sync) state <= STOP_HIGH; end
            STOP_HIGH: if (half_done) begin
                sda_low <= 0; state <= STOP_FREE; timer <= 0;
            end
            STOP_FREE: if (half_done) begin
                timer <= 0;
                if (stop_then_read && error_code == 0) begin
                    stop_then_read <= 0; read_stage <= 1; state <= START_FREE;
                end else state <= FINISH;
            end
            RX_LOW: if (half_done) begin scl_low <= 0; state <= RX_RISE; timer <= 0; end
            RX_RISE: begin timer <= 0; if (scl_sync) state <= RX_HIGH; end
            RX_HIGH: if (half_done) begin
                rx_byte[bit_index] <= sda_sync; scl_low <= 1; timer <= 0;
                if (bit_index == 0) begin
                    read_data[byte_index*8 +: 8] <= {rx_byte[7:1],sda_sync};
                    sda_low <= byte_index + 1 < count; state <= MACK_LOW;
                end else begin bit_index <= bit_index - 1; state <= RX_LOW; end
            end
            MACK_LOW: if (half_done) begin scl_low <= 0; state <= MACK_RISE; timer <= 0; end
            MACK_RISE: begin timer <= 0; if (scl_sync) state <= MACK_HIGH; end
            MACK_HIGH: if (half_done) begin
                scl_low <= 1; timer <= 0;
                if (byte_index + 1 == count) begin sda_low <= 1; state <= STOP_LOW; end
                else begin
                    byte_index <= byte_index + 1; bit_index <= 7; rx_byte <= 0;
                    sda_low <= 0; state <= RX_LOW;
                end
            end
            FINISH: begin
                scl_low <= 0; sda_low <= 0; busy <= 0; done <= 1; state <= IDLE;
            end
            default: begin error_code <= 8'hff; state <= FINISH; end
        endcase
    end
endmodule
