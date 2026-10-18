// Asynchronous 8N1 receive adapter. Bytes are zero-extended on a 32-bit link.
module basic_pitch_uart_rx #(
    parameter integer CLK_HZ = 50000000,
    parameter integer BAUD = 115200
) (
    input wire clk, input wire rst_n, input wire serial_in,
    input wire [31:0] time_cycles,
    output reg [31:0] data, output reg valid, output reg framing_error,
    output reg [31:0] byte_start_time
);
    localparam integer BIT_CLKS = (CLK_HZ + BAUD/2) / BAUD;
    localparam [1:0] IDLE=0, START=1, DATA=2, STOP=3;
    reg rx_meta, rx_sync;
    reg [1:0] state;
    reg [31:0] timer;
    reg [2:0] bit_index;
    reg [7:0] shift;
    reg [31:0] candidate_start_time;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin rx_meta <= 1'b1; rx_sync <= 1'b1; end
        else begin rx_meta <= serial_in; rx_sync <= rx_meta; end
    end
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= IDLE; timer <= 0; bit_index <= 0; shift <= 0;
            data <= 0; valid <= 0; framing_error <= 0;
            candidate_start_time <= 0; byte_start_time <= 0;
        end else begin
            valid <= 0; framing_error <= 0;
            case (state)
                // Timestamp the synchronized start detection, but publish it
                // only with a fully validated byte. False starts cannot escape.
                IDLE: if (!rx_sync) begin
                    state <= START; timer <= BIT_CLKS/2-1;
                    candidate_start_time <= time_cycles;
                end
                START: if (timer != 0) timer <= timer-1;
                       else if (rx_sync) state <= IDLE;
                       else begin state <= DATA; timer <= BIT_CLKS-1; bit_index <= 0; end
                DATA: if (timer != 0) timer <= timer-1;
                      else begin
                          shift[bit_index] <= rx_sync; timer <= BIT_CLKS-1;
                          if (bit_index == 7) state <= STOP;
                          else bit_index <= bit_index+1'b1;
                      end
                STOP: if (timer != 0) timer <= timer-1;
                      else begin
                          state <= IDLE;
                          if (rx_sync) begin
                              data <= {24'b0,shift}; valid <= 1;
                              byte_start_time <= candidate_start_time;
                          end
                          else framing_error <= 1;
                      end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
